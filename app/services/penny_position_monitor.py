import asyncio
import logging
import time
from typing import Any, Dict, Set

from .penny_stock_monitor import penny_stock_monitor
from . import ibkr_service
from . import ibkr_service as ibkr_svc_module
from .penny_stock_watcher import penny_stock_watcher
from .penny_stock_watcher import PennyStockWatcher
from .penny_stock_watcher import logger as _pw_logger
from .pnl_pubsub import pnl_pubsub

logger = logging.getLogger(__name__)


class PennyPositionMonitor:
    """Monitors market-data for filled penny-stock parent orders and computes P/L."""

    def __init__(self, poll_interval: float = 1.0):
        self._task = None
        self._running = False
        self.poll_interval = poll_interval
        # tracked conids mapped to set of parent_order_ids
        self._tracked: Dict[int, Set[str]] = {}
        self._subscribed_conids: Set[int] = set()

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="penny_position_monitor")
        logger.info("PennyPositionMonitor started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # unsubscribe all tracked market-data
        try:
            if hasattr(ibkr_service, 'ws_client'):
                for conid in list(self._subscribed_conids):
                    try:
                        ibkr_service.ws_client.unsubscribe(ibkr_service.IbkrWsKey.MARKET_DATA)
                    except Exception:
                        pass
        except Exception:
            pass
        logger.info("PennyPositionMonitor stopped")

    def _gather_tracked_conids(self) -> Set[int]:
        """Return conids for penny storage records that are FILLED and have conid known."""
        conids = set()
        try:
            for rec in penny_stock_monitor.list_orders():
                try:
                    if str(rec.get('status', '')).upper() == 'FILLED':
                        # conid may be stored in last_update or top-level
                        lid = rec.get('last_update') or {}
                        conid = rec.get('conid') or lid.get('conid') or lid.get('contract', {}).get('conid')
                        if conid is not None:
                            try:
                                conids.add(int(conid))
                            except Exception:
                                continue
                except Exception:
                    continue
        except Exception:
            pass
        return conids

    async def _run_loop(self):
        # We'll use the ws client's MARKET_DATA channel via ibkr_service.ws_client queue accessor
        backoff = 1.0
        while self._running:
            try:
                tracked_conids = self._gather_tracked_conids()

                # Subscribe to new conids
                to_sub = tracked_conids - self._subscribed_conids
                to_unsub = self._subscribed_conids - tracked_conids

                # Unsubscribe conids no longer tracked
                for conid in list(to_unsub):
                    try:
                        # Unsubscribe request expects channel+conid payload; use ws_client directly
                        if hasattr(ibkr_service, 'ws_client'):
                            chan = ibkr_service.IbkrWsKey.MARKET_DATA.channel
                            ibkr_service.ws_client.unsubscribe(chan + f"+{conid}")
                    except Exception:
                        pass
                    self._subscribed_conids.discard(conid)

                # Subscribe to newly tracked conids
                for conid in list(to_sub):
                    try:
                        if hasattr(ibkr_service, 'ws_client'):
                            chan = ibkr_service.IbkrWsKey.MARKET_DATA.channel
                            req = {'channel': f"{chan}+{conid}", 'data': {'fields': ['31']}}
                            # Use ws_client.subscribe with constructed request
                            ibkr_service.ws_client.subscribe(channel=f"{chan}+{conid}")
                            self._subscribed_conids.add(conid)
                    except Exception:
                        logger.debug(f"Failed to subscribe market-data for conid {conid}")

                # Read any incoming market-data messages for subscribed conids
                try:
                    if hasattr(ibkr_service, 'ws_client'):
                        accessor = ibkr_service.ws_client.new_queue_accessor(ibkr_service.IbkrWsKey.MARKET_DATA)
                        # drain available messages
                        while not accessor.empty():
                            msg = accessor.get()
                            try:
                                # msg keyed by conid
                                if isinstance(msg, dict):
                                    for k, v in msg.items():
                                        try:
                                            conid = int(k)
                                        except Exception:
                                            continue
                                        if conid in self._subscribed_conids:
                                            self._process_market_update(conid, v)
                            except Exception:
                                logger.exception("Error processing market-data message")
                except Exception:
                    # No ws client or queue
                    pass

                backoff = 1.0
                await asyncio.sleep(self.poll_interval)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("PennyPositionMonitor loop error")
                await asyncio.sleep(min(30.0, backoff))
                backoff = min(30.0, backoff * 2)

    def _process_market_update(self, conid: int, payload: Dict[str, Any]):
        # payload is already preprocessed by ws client to readable keys (e.g., 'last')
        try:
            last = payload.get('last')
            if last == 'N/A' or last is None:
                return
            try:
                last_price = float(last)
            except Exception:
                return

            # For each tracked parent order referencing this conid, compute P/L
            for rec in penny_stock_monitor.list_orders():
                try:
                    status = str(rec.get('status', '')).upper()
                    if status != 'FILLED':
                        continue
                    lid = rec.get('last_update') or {}
                    rec_conid = rec.get('conid') or lid.get('conid') or lid.get('contract', {}).get('conid')
                    if rec_conid is None:
                        continue
                    try:
                        if int(rec_conid) != conid:
                            continue
                    except Exception:
                        continue

                    # Use position info from IBKR service if available
                    pos = None
                    try:
                        pos = ibkr_service.find_position_by_conid(int(conid))
                    except Exception:
                        pos = None

                    # Try to derive position_size and avg_cost
                    position_size = None
                    avg_cost = None
                    if pos and isinstance(pos, dict):
                        position_size = float(pos.get('position', 0) or 0)
                        avg_cost = float(pos.get('avgCost', pos.get('avgPrice', 0) or 0) or 0)
                    else:
                        # Fall back to last_update fields (if the fill details contain filled_qty and avg_price)
                        filled_qty = lid.get('filled_qty') or lid.get('filled')
                        avg_price = lid.get('avg_price') or lid.get('avgPrice')
                        try:
                            position_size = float(filled_qty) if filled_qty is not None else None
                        except Exception:
                            position_size = None
                        try:
                            avg_cost = float(avg_price) if avg_price is not None else None
                        except Exception:
                            avg_cost = None

                    if position_size is None or position_size == 0 or avg_cost is None:
                        # Not enough info to compute P/L
                        continue

                    # multiplier for common stock is 1
                    multiplier = 1

                    unrealized_pnl = (last_price - avg_cost) * position_size * multiplier
                    unrealized_pct = None
                    try:
                        if avg_cost != 0:
                            unrealized_pct = (last_price - avg_cost) / avg_cost * 100
                    except Exception:
                        unrealized_pct = None

                    # Persist into penny_stock_monitor under last_update->pnl
                    details = {
                        'last_price': last_price,
                        'unrealized_pnl': unrealized_pnl,
                        'unrealized_pnl_pct': unrealized_pct,
                        'pnl_updated_at': time.time(),
                    }
                    parent_id = rec.get('parent_order_id') or rec.get('parentOrderId') or rec.get('order_id')
                    penny_stock_monitor.update_order_status(parent_id, rec.get('status') or 'FILLED', details=details)

                    # Publish to any connected websocket clients subscribed to this parent order
                    try:
                        # schedule async publish (we're in sync context, use ensure_future)
                        payload = {
                            'type': 'penny_pnl',
                            'parent_order_id': parent_id,
                            'conid': conid,
                            **details,
                        }
                        try:
                            asyncio.get_event_loop().create_task(pnl_pubsub.publish(parent_id, payload))
                        except RuntimeError:
                            # If no running loop, fallback to ensure_future
                            asyncio.ensure_future(pnl_pubsub.publish(parent_id, payload))
                    except Exception:
                        logger.exception("Failed to publish P/L update via pnl_pubsub")

# inner record loop error handler
                except Exception:
                    logger.exception("Failed to compute P/L for a record")
        except Exception:
            logger.exception("PennyPositionMonitor _process_market_update failed")
# Global instance for import-time use
penny_position_monitor = PennyPositionMonitor()
