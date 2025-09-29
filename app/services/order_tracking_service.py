"""
General Order Tracking Service

This service bridges the gap between IBKR order updates and alert status management.
It listens for order fill events and automatically updates alert status to "open": true
when corresponding orders are filled or partially filled.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

from . import ibkr_service
from .alerter_stock_storage import alerter_stock_storage
from .handlers.lite_handlers import _load_alerts, _save_alerts

logger = logging.getLogger(__name__)


class OrderTrackingService:
    """
    General order tracking service that:
    1. Monitors IBKR order updates via WebSocket
    2. Maps filled orders to their originating alerts
    3. Updates alert status to "open": true when orders are filled
    4. Handles all alert types (not just penny stocks)
    """

    def __init__(self, poll_interval: float = 1.0):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.poll_interval = poll_interval
        self.idle_sleep = 5.0
        self.last_polled_at: Optional[float] = None
        self.subscribed: bool = False
        
        # Track processed order IDs to avoid duplicate processing
        self._processed_orders: set = set()
        
        # Statistics
        self.stats = {
            'orders_processed': 0,
            'alerts_updated': 0,
            'alerts_removed': 0,
            'last_update': None
        }

    async def start(self):
        """Start the order tracking service"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="order_tracking_service")
        logger.info("OrderTrackingService started")

    async def stop(self):
        """Stop the order tracking service"""
        if not self._running:
            return
        self._running = False
        
        if self._task:
            try:
                if self.subscribed:
                    logger.info("OrderTrackingService: unsubscribing from IBKR orders channel")
                    ibkr_service.unsubscribe_orders()
                    self.subscribed = False
                    logger.info("OrderTrackingService: unsubscribed from IBKR orders channel")
            except Exception as e:
                logger.warning(f"OrderTrackingService: error during unsubscribe: {e}")
            
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            
        logger.info("OrderTrackingService stopped")

    async def _run_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                self.last_polled_at = asyncio.get_event_loop().time()
                
                # Ensure we're subscribed to order updates
                if not self.subscribed:
                    try:
                        logger.info("OrderTrackingService: attempting to subscribe to IBKR orders channel")
                        ibkr_service.subscribe_orders()
                        self.subscribed = True
                        logger.info("OrderTrackingService: subscribed to IBKR orders channel")
                    except Exception as e:
                        logger.warning(f"OrderTrackingService: failed to subscribe to orders: {e}")
                        await asyncio.sleep(self.idle_sleep)
                        continue

                # Get order updates from IBKR
                order_messages = ibkr_service.get_orders_data()
                
                if order_messages:
                    for message in order_messages:
                        try:
                            await self._process_order_message(message)
                        except Exception as e:
                            logger.exception(f"Error processing order message: {e}")
                    
                    await asyncio.sleep(self.poll_interval)
                else:
                    # No messages, sleep longer
                    await asyncio.sleep(self.idle_sleep)
                    
            except Exception as e:
                logger.exception(f"OrderTrackingService: error in run loop: {e}")
                await asyncio.sleep(self.idle_sleep)

    async def _process_order_message(self, message: Dict[str, Any]):
        """Process a single order update message"""
        if not isinstance(message, dict):
            return

        # Extract order details
        order_info = self._extract_order_info(message)
        if not order_info:
            return

        order_id = order_info.get('order_id')
        if not order_id or order_id in self._processed_orders:
            return

        # Check if this is a fill event
        if not self._is_fill_event(order_info):
            return

        logger.info(f"Processing fill event for order {order_id}: {order_info.get('status')}")
        
        # Try to match this order to stored alerts
        matched_alerts = await self._find_matching_alerts(order_info)
        
        if matched_alerts:
            for alert_info in matched_alerts:
                # Check if this is a position closure
                if self._is_closure_event(order_info, alert_info):
                    success = await self._remove_closed_alert(alert_info, order_info)
                    if success:
                        self.stats['alerts_removed'] += 1
                        logger.info(f"Removed closed alert for {alert_info['alerter']}: {alert_info['ticker']}")
                else:
                    # Regular fill - update status to open
                    success = await self._update_alert_status(alert_info, order_info)
                    if success:
                        self.stats['alerts_updated'] += 1
                        logger.info(f"Updated alert status for {alert_info['alerter']}: {alert_info['ticker']}")

        # Mark as processed
        self._processed_orders.add(order_id)
        self.stats['orders_processed'] += 1
        self.stats['last_update'] = datetime.utcnow().isoformat()

    def _extract_order_info(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract standardized order information from IBKR message"""
        # Handle nested data structures
        payload = message
        if 'data' in message and isinstance(message['data'], dict):
            payload = message['data']
        elif 'data' in message and isinstance(message['data'], list) and message['data']:
            payload = message['data'][0]

        if not isinstance(payload, dict):
            return None

        # Extract key fields
        order_id = (payload.get('orderId') or 
                   payload.get('order_id') or 
                   payload.get('id') or
                   payload.get('clientOrderId') or
                   payload.get('client_order_id'))
        
        if not order_id:
            return None

        status = (payload.get('status') or 
                 payload.get('orderStatus') or 
                 payload.get('state') or '').upper()

        filled_qty = payload.get('filled') or payload.get('filled_qty') or payload.get('filledQuantity')
        total_qty = payload.get('totalSize') or payload.get('total_qty') or payload.get('quantity')
        
        # Extract contract details
        symbol = payload.get('ticker') or payload.get('symbol') or payload.get('underlying')
        strike = payload.get('strike')
        expiry = payload.get('expiry') or payload.get('expiration')
        right = payload.get('right') or payload.get('option_type')
        
        return {
            'order_id': str(order_id),
            'status': status,
            'filled_qty': filled_qty,
            'total_qty': total_qty,
            'symbol': symbol,
            'strike': strike,
            'expiry': expiry,
            'right': right,
            'raw_message': payload
        }

    def _is_fill_event(self, order_info: Dict[str, Any]) -> bool:
        """Check if this order update represents a fill event"""
        status = order_info.get('status', '')
        filled_qty = order_info.get('filled_qty')
        
        # Check status indicators
        if any(keyword in status for keyword in ['FILLED', 'PARTIAL']):
            return True
            
        # Check if filled quantity > 0
        if filled_qty:
            try:
                return float(filled_qty) > 0
            except (ValueError, TypeError):
                pass
                
        return False

    def _is_closure_event(self, order_info: Dict[str, Any], alert_info: Dict[str, Any]) -> bool:
        """Check if this order represents a position closure (sell to close)"""
        status = order_info.get('status', '')
        raw_message = order_info.get('raw_message', {})
        
        # Check for explicit closure indicators
        closure_indicators = [
            'CLOSE', 'CLOSING', 'STC', 'SELL_TO_CLOSE', 
            'BTC', 'BUY_TO_CLOSE', 'LIQUIDATE', 'EXIT'
        ]
        
        # Check status for closure keywords
        if any(indicator in status.upper() for indicator in closure_indicators):
            logger.info(f"Detected closure via status: {status}")
            return True
            
        # Check raw message for closure indicators
        raw_str = str(raw_message).upper()
        if any(indicator in raw_str for indicator in closure_indicators):
            logger.info(f"Detected closure via raw message: {raw_str[:100]}...")
            return True
            
        # Check for side/action indicators suggesting closure
        side = (raw_message.get('side') or 
               raw_message.get('action') or 
               raw_message.get('orderType') or '').upper()
        
        if any(indicator in side for indicator in ['SELL', 'CLOSE', 'EXIT']):
            # Additional validation: ensure this is actually closing a position
            # For options, selling when we had a long position indicates closure
            alert_data = alert_info.get('alert_data', {})
            alert_side = alert_data.get('alert_details', {}).get('side', '')
            
            if alert_side and 'SELL' in side:
                logger.info(f"Detected closure: SELL order for {alert_side} position")
                return True
                
        return False

    async def _remove_closed_alert(self, alert_info: Dict[str, Any], order_info: Dict[str, Any]) -> bool:
        """Remove alert from storage when position is completely closed"""
        try:
            alerter = alert_info['alerter']
            alert_key = alert_info['key']
            
            # Load current alerts
            alerts = _load_alerts()
            
            # Check if the alert still exists
            if alert_key not in alerts:
                logger.warning(f"Alert {alert_key} not found for removal")
                return False
                
            # Remove the specific ticker alert
            if alerter in alerts and isinstance(alerts[alerter], dict):
                # Extract ticker from alert key (assuming format like "alerter-ticker" or just "ticker")
                ticker = alert_info.get('ticker') or order_info.get('symbol')
                
                if ticker and ticker in alerts[alerter]:
                    # Log the removal with order details
                    removed_alert = alerts[alerter][ticker].copy()
                    removed_alert['removal_details'] = {
                        'order_id': order_info['order_id'],
                        'closure_status': order_info['status'],
                        'removed_at': datetime.utcnow().isoformat(),
                        'reason': 'position_closed'
                    }
                    
                    # Remove the alert
                    del alerts[alerter][ticker]
                    
                    # If this was the last alert for this alerter, we could optionally clean up
                    # the alerter entry entirely, but keeping it for historical purposes
                    
                    # Save updated alerts
                    _save_alerts(alerts)
                    
                    logger.info(f"Removed closed position alert: {alerter} -> {ticker}")
                    logger.info(f"Closure order: {order_info['order_id']} ({order_info['status']})")
                    
                    # Also remove from alerter stock storage if applicable
                    try:
                        stored_contract = alerter_stock_storage.get_contract(alerter)
                        if stored_contract and stored_contract.get('symbol') == ticker:
                            # We could remove the contract, but for now just log it
                            logger.info(f"Note: Contract storage for {alerter}:{ticker} may need cleanup")
                    except Exception as e:
                        logger.warning(f"Error checking contract storage: {e}")
                    
                    return True
                else:
                    logger.warning(f"Ticker {ticker} not found in {alerter} alerts")
                    
            return False
            
        except Exception as e:
            logger.error(f"Failed to remove closed alert: {e}")
            return False

    async def _find_matching_alerts(self, order_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find alerts that match this order"""
        matched_alerts = []
        
        symbol = order_info.get('symbol')
        if not symbol:
            return matched_alerts

        # Load alerts and search through all alerters
        alerts = _load_alerts()
        alerter_keys = ['real-day-trading', 'demslayer', 'prof-and-kian-alerts', 'robindahood-alerts']
        
        for alerter_key in alerter_keys:
            try:
                if alerter_key not in alerts:
                    continue
                    
                alerter_data = alerts[alerter_key]
                if not isinstance(alerter_data, dict):
                    continue
                    
                # Check if this symbol exists in this alerter's alerts
                if symbol in alerter_data:
                    ticker_alert = alerter_data[symbol]
                    
                    # For options, also check strike if available
                    if order_info.get('strike') and ticker_alert.get('alert_details', {}).get('strike'):
                        try:
                            order_strike = float(order_info['strike'])
                            alert_strike = float(ticker_alert['alert_details']['strike'])
                            if abs(order_strike - alert_strike) > 0.01:
                                continue
                        except (ValueError, TypeError):
                            # If we can't compare strikes, still match by symbol
                            pass
                            
                    matched_alerts.append({
                        'alerter': alerter_key,
                        'ticker': symbol,
                        'key': f"{alerter_key}-{symbol}",  # Construct a logical key
                        'alert_data': ticker_alert
                    })
                    
            except Exception as e:
                logger.warning(f"Error checking alerter {alerter_key}: {e}")
                
        return matched_alerts

    async def _update_alert_status(self, alert_info: Dict[str, Any], order_info: Dict[str, Any]) -> bool:
        """Update alert status to open=true"""
        try:
            alerter = alert_info['alerter']
            ticker = alert_info['ticker'] 
            alert_data = alert_info['alert_data'].copy()
            
            # Set alert as open
            alert_data['open'] = True
            alert_data['last_order_update'] = {
                'order_id': order_info['order_id'],
                'status': order_info['status'],
                'filled_qty': order_info.get('filled_qty'),
                'updated_at': datetime.utcnow().isoformat()
            }
            
            # Update the alert in the nested structure
            alerts = _load_alerts()
            if alerter not in alerts:
                alerts[alerter] = {}
            alerts[alerter][ticker] = alert_data
            _save_alerts(alerts)
            
            logger.info(f"Set alert {alerter}:{ticker} to open=true (order {order_info['order_id']} filled)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update alert status: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get service status and statistics"""
        return {
            'running': self._running,
            'subscribed': self.subscribed,
            'last_polled_at': self.last_polled_at,
            'poll_interval': self.poll_interval,
            'stats': self.stats.copy(),
            'processed_orders_count': len(self._processed_orders)
        }

    def force_reconcile(self) -> Dict[str, Any]:
        """Force reconciliation of current orders with alerts"""
        try:
            # Get current orders from IBKR
            orders = ibkr_service.get_orders_data()
            processed = 0
            updated = 0
            
            for order in orders or []:
                order_info = self._extract_order_info(order)
                if order_info and self._is_fill_event(order_info):
                    # Process this order (bypass the processed_orders check)
                    asyncio.create_task(self._process_order_message(order))
                    processed += 1
                    
            return {
                'orders_examined': len(orders or []),
                'fill_events_processed': processed,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.exception("Error during force reconcile")
            return {'error': str(e)}


# Global instance
order_tracking_service = OrderTrackingService()
