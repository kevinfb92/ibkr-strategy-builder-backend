import asyncio
import logging
import time
import json
from typing import Any, Dict, Optional

from .penny_stock_monitor import penny_stock_monitor
from .penny_stock_notification_service import penny_stock_notification_service
from . import ibkr_service

logger = logging.getLogger(__name__)
# Fallback: ensure at least a console handler so INFO logs from this module are visible
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    ch.setFormatter(fmt)
    logger.addHandler(ch)


class PennyStockWatcher:
    """Background watcher that listens for IBKR order updates and updates stored parent orders.

    Behavior:
    - Periodically polls the IBKR WebSocket order queue (via ibkr_service.get_orders_data())
    - For each incoming order-update message, attempts to match the message's orderId or clientOrderId
      against stored parent_order_id keys in penny_stock_monitor.
    - When a match is found and the message indicates the order is filled (status contains 'FILLED' or
      filled quantity equals original quantity), the watcher updates the stored order status and
      attaches basic fill details.
    """

    def __init__(self, poll_interval: float = 1.0):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.poll_interval = poll_interval
        # When no pending orders exist, sleep this many seconds before re-checking
        self.idle_sleep = 5.0
        # diagnostics
        self.last_polled_at: Optional[float] = None
        # whether we are currently subscribed to IBKR orders channel
        self.subscribed: bool = False

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="penny_stock_watcher")
        logger.info("PennyStockWatcher started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PennyStockWatcher stopped")

    async def _run_loop(self):
        backoff = 1.0
        subscribed = False
        while self._running:
            try:
                # Only subscribe/listen if we have pending OPEN parent orders stored
                try:
                    stored_orders = penny_stock_monitor.list_orders()

                    # An order is considered 'open' unless its status string contains 'fill', 'cancel', or 'close'
                    def is_open(rec: Dict[str, Any]) -> bool:
                        st = str(rec.get('status', '')).lower()
                        if any(k in st for k in ('fill', 'filled', 'cancel', 'cancelled', 'close', 'closed')):
                            return False
                        return True

                    has_open = any(is_open(o) for o in stored_orders)
                except Exception:
                    has_open = False

                if not has_open:
                    # Nothing pending — ensure we are unsubscribed and sleep longer
                    if subscribed:
                        try:
                            logger.info("PennyStockWatcher: initiating unsubscribe from IBKR orders channel")
                            ibkr_service.unsubscribe_orders()
                            logger.info("PennyStockWatcher: unsubscribed from IBKR orders channel")
                        except Exception:
                            logger.exception("PennyStockWatcher: failed to unsubscribe cleanly")
                        subscribed = False
                        self.subscribed = False

                    # avoid tight-looping when nothing to watch
                    await asyncio.sleep(self.idle_sleep)
                    continue

                # If we reach here there are pending orders; subscribe if not already
                if not subscribed:
                    try:
                        logger.info("PennyStockWatcher: attempting to subscribe to IBKR orders channel")
                        ibkr_service.subscribe_orders()
                        subscribed = True
                        logger.info("PennyStockWatcher: subscribed to IBKR orders channel")
                        self.subscribed = True
                        # After subscribing, reconcile with REST to catch any missed updates
                        try:
                            self.reconcile_with_rest()
                        except Exception:
                            logger.debug("Reconcile on subscribe failed; will continue")
                    except Exception:
                        # subscribe may fail if ws not ready; ignore and retry later
                        logger.debug("Initial subscribe to IBKR orders channel failed; will retry")

                orders_data = None
                try:
                    orders_data = ibkr_service.get_orders_data()
                except Exception as e:
                    logger.debug(f"Failed to get orders data: {e}")
                    orders_data = None

                # record last polled timestamp for diagnostics
                try:
                    self.last_polled_at = time.time()
                except Exception:
                    self.last_polled_at = None

                if orders_data:
                    # ibind's ws client may return a list of messages or a single dict
                    items = orders_data if isinstance(orders_data, list) else [orders_data]
                    for msg in items:
                        try:
                            # Log the raw incoming message before handling so it's visible in server logs
                            try:
                                logger.info("WS_PROCESSED_MSG: %s", json.dumps(msg, default=str))
                            except Exception:
                                logger.info("WS_PROCESSED_MSG (repr): %s", repr(msg))
                            await self._handle_order_message(msg)
                        except Exception:
                            logger.exception("Error handling order message")

                # reset backoff on success
                backoff = 1.0
                await asyncio.sleep(self.poll_interval)

                # small health check: if ws_client reports not ready, mark unsubscribed so subscribe() is retried
                try:
                    if hasattr(ibkr_service, 'ws_client') and hasattr(ibkr_service.ws_client, 'ready'):
                        try:
                            if not ibkr_service.ws_client.ready():
                                subscribed = False
                                self.subscribed = False
                        except Exception:
                            # ignore readiness probe errors
                            pass
                except Exception:
                    pass

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"PennyStockWatcher loop error: {exc}")
                # exponential backoff on repeated failures
                await asyncio.sleep(min(30.0, backoff))
                backoff = min(30.0, backoff * 2)

    def get_status(self) -> Dict[str, Any]:
        """Return a small status dict for monitoring and diagnostics."""
        return {
            'running': bool(self._running),
            'last_polled_at': self.last_polled_at,
            'subscribed': bool(getattr(self, 'subscribed', False)),
            'poll_interval': self.poll_interval,
        }

    def reconcile_with_rest(self) -> Dict[str, Any]:
        """Fetch current orders from IBKR (prefer REST) and reconcile stored parent orders.

        Strategy:
        - Attempt to call IBKR REST get_orders() if available; otherwise fall back to the
          websocket cached orders via ibkr_service.get_orders_data().
        - Iterate orders returned by IBKR and for each message try to match parent/ord ids
          against the stored parent_order_id in penny_stock_monitor. If a match is found
          and the remote order status indicates FILLED/CANCELLED, update the stored status.
        - Return a small summary of counts updated.
        """
        updated = 0
        examined = 0
        try:
            # Prefer REST
            rest_orders = None
            try:
                # IBKRService exposes a client that may have get_orders()
                ib = ibkr_service
                if hasattr(ib.client, 'get_orders'):
                    resp = ib.client.get_orders()
                    rest_orders = resp.data if resp and hasattr(resp, 'data') else resp
            except Exception:
                rest_orders = None

            orders = rest_orders if rest_orders else ibkr_service.get_orders_data()

            if not orders:
                return {'examined': 0, 'updated': 0}

            items = orders if isinstance(orders, list) else [orders]
            for msg in items:
                examined += 1
                try:
                    payload = msg
                    if isinstance(msg, dict) and 'data' in msg:
                        payload = msg['data']
                    if isinstance(payload, list):
                        payload = payload[0] if payload else {}
                    if not isinstance(payload, dict):
                        continue

                    # Identify parent ref or order ids
                    parent_ref = payload.get('parentOrderId') or payload.get('parent_order_id') or payload.get('origOrderId') or payload.get('orig_order_id')
                    order_id = payload.get('orderId') or payload.get('order_id') or payload.get('id')
                    client_order_id = payload.get('clientOrderId') or payload.get('client_order_id') or payload.get('cOID') or payload.get('clientId')
                    status = payload.get('status') or payload.get('orderStatus') or payload.get('state')

                    matched_key = None
                    if parent_ref and penny_stock_monitor.get_order(str(parent_ref)):
                        matched_key = str(parent_ref)
                    elif order_id and penny_stock_monitor.get_order(str(order_id)):
                        matched_key = str(order_id)
                    elif client_order_id and penny_stock_monitor.get_order(str(client_order_id)):
                        matched_key = str(client_order_id)

                    if not matched_key:
                        continue

                    # Consider filled or cancelled
                    s = str(status).upper() if status else ''
                    if 'FILLED' in s or 'CANCEL' in s or 'CLOSED' in s:
                        details = {'raw_message': payload}
                        if penny_stock_monitor.update_order_status(matched_key, s or 'UNKNOWN', details=details):
                            updated += 1
                except Exception:
                    logger.exception("Error reconciling single order message")

        except Exception:
            logger.exception("Reconcile with REST failed")

        return {'examined': examined, 'updated': updated}

    async def _handle_order_message(self, msg: Dict[str, Any]):
        """Process a single order update message and update penny monitor if matches.

        Expected message shapes vary; we attempt to extract these fields safely:
        - orderId (server-assigned id)
        - clientOrderId / cOID (client-specified)
        - status (string)
        - filled (numeric filled quantity)
        - remaining (numeric)
        - avgPrice (average fill price)
        """
        if not isinstance(msg, dict):
            return

        # Normalize keys - support nested 'data' layers
        payload = msg
        if 'data' in msg and isinstance(msg['data'], (dict, list)):
            payload = msg['data'] if not isinstance(msg['data'], list) else (msg['data'][0] if msg['data'] else msg['data'])

        if isinstance(payload, list):
            # pick first dict if list
            payload = payload[0] if payload else {}

        if not isinstance(payload, dict):
            return

        order_id = None
        client_order_id = None
        status = None
        filled = None
        avg_price = None

        # Common fields
        order_id = payload.get('orderId') or payload.get('order_id') or payload.get('id')
        client_order_id = payload.get('clientOrderId') or payload.get('client_order_id') or payload.get('cOID') or payload.get('clientId')
        status = payload.get('status') or payload.get('orderStatus') or payload.get('state')
        filled = payload.get('filled') or payload.get('filled_qty') or payload.get('filledQuantity')
        avg_price = payload.get('avgPrice') or payload.get('avg_price') or payload.get('avg_fill_price')

        # Matching strategy:
        # 1) If the payload includes a parentOrderId / origOrderId (IBKR indicates child referencing parent),
        #    try to match that to a stored parent key first. This aligns with IBKR semantics: a child order
        #    will reference the parent when it's activated/triggered.
        # 2) Otherwise, fall back to matching by orderId or clientOrderId (direct matches).
        matched_key = None

        # Parent reference fields that IBKR may include when child orders are processed
        parent_ref = payload.get('parentOrderId') or payload.get('parent_order_id') or payload.get('origOrderId') or payload.get('orig_order_id')
        try:
            if parent_ref is not None:
                parent_ref = str(parent_ref)
                if penny_stock_monitor.get_order(parent_ref):
                    matched_key = parent_ref
        except Exception:
            # keep going to try other matches
            matched_key = None

        # Try matching by order_id or client_order_id if no parent_ref match
        if not matched_key:
            if order_id is not None and penny_stock_monitor.get_order(str(order_id)):
                matched_key = str(order_id)
            elif client_order_id is not None and penny_stock_monitor.get_order(str(client_order_id)):
                matched_key = str(client_order_id)

        # Diagnostic logging for missed matches
        if not matched_key:
            try:
                logger.debug(f"Order message received (no match yet): order_id={order_id} client_order_id={client_order_id} parent_ref={parent_ref} status={status}")
            except Exception:
                pass

        if not matched_key:
            # nothing to do
            return

        # Determine if this message indicates a fill
        is_filled = False
        try:
            if status and isinstance(status, str) and 'FILLED' in status.upper():
                is_filled = True
        except Exception:
            pass

        # Also consider numeric filled value
        try:
            if not is_filled and filled is not None:
                try:
                    if float(filled) > 0:
                        # mark filled when remaining is zero or filled is non-zero and status looks like filled
                        remaining = payload.get('remaining') or payload.get('remaining_qty') or payload.get('remainingQuantity')
                        if remaining is None or float(remaining) == 0:
                            is_filled = True
                except Exception:
                    pass
        except Exception:
            pass

        details = {
            'raw_message': payload,
        }
        if filled is not None:
            details['filled_qty'] = filled
        if avg_price is not None:
            details['avg_price'] = avg_price

        if is_filled:
            # Update order status
            penny_stock_monitor.update_order_status(matched_key, 'FILLED', details=details)
            logger.info(f"Marked penny order {matched_key} as FILLED")
            
            # Send Telegram notification
            try:
                await self._send_fill_notification(matched_key, payload, details)
            except Exception as e:
                logger.error(f"Failed to send fill notification for {matched_key}: {e}")
        else:
            # If not filled, still update last known status for traceability
            if status:
                penny_stock_monitor.update_order_status(matched_key, status, details=details)

    async def _send_fill_notification(self, order_key: str, payload: Dict[str, Any], details: Dict[str, Any]):
        """Send Telegram notification when an order is filled"""
        try:
            # Get the stored order data
            stored_order = penny_stock_monitor.get_order(order_key)
            if not stored_order:
                logger.warning(f"Cannot find stored order for key {order_key}")
                return
                
            ticker = stored_order.get('ticker', 'Unknown')
            
            # Get the strategy data for this ticker
            strategy_data = penny_stock_monitor._data.get(ticker, {})
            
            # Determine if this is a buy (parent) or sell (child) order
            is_parent_order = order_key == stored_order.get('parent_order_id')
            
            # Extract order details from payload and details
            order_data = {
                'parent_order_id': stored_order.get('parent_order_id', order_key),
                'filled_qty': details.get('filled_qty', payload.get('filled', 'Unknown')),
                'avg_price': details.get('avg_price', payload.get('avgPrice', 'Unknown'))
            }
            
            if is_parent_order:
                # Parent order filled = buy order filled = position opened
                await penny_stock_notification_service.send_buy_order_filled(
                    ticker, order_data, strategy_data
                )
            else:
                # Child order filled = sell order filled = position closed/partial
                await penny_stock_notification_service.send_sell_order_filled(
                    ticker, order_data, strategy_data
                )
                
        except Exception as e:
            logger.error(f"Error sending fill notification for {order_key}: {e}")


# Global instance
penny_stock_watcher = PennyStockWatcher()
