import asyncio
import logging
import time
from typing import Dict, List, Any, Optional

from .penny_stock_monitor import penny_stock_monitor
from .penny_stock_notification_service import penny_stock_notification_service
from . import ibkr_service

logger = logging.getLogger(__name__)


class PennyStockPriceMonitor:
    """Monitor penny stock prices and trigger stop loss adjustments and free runner logic."""
    
    def __init__(self, poll_interval: float = 5.0):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.poll_interval = poll_interval
        self.trailing_stop_percent = 5.0  # Default 5% trailing stop for free runners
        
    async def start(self):
        """Start the price monitoring loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop(), name="penny_stock_price_monitor")
        logger.info("PennyStockPriceMonitor started")
        
    async def stop(self):
        """Stop the price monitoring loop."""
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PennyStockPriceMonitor stopped")
        
    async def _monitor_loop(self):
        """Main monitoring loop that checks prices and triggers actions."""
        while self._running:
            try:
                await self._check_all_strategies()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in price monitoring loop: {e}")
                await asyncio.sleep(self.poll_interval)
                
    async def _check_all_strategies(self):
        """Check all stored strategies for price target achievements."""
        try:
            # Get all stored strategies grouped by ticker
            strategies = penny_stock_monitor._data
            
            for ticker, strategy_data in strategies.items():
                try:
                    await self._check_strategy(ticker, strategy_data)
                except Exception as e:
                    logger.error(f"Error checking strategy for {ticker}: {e}")
                    
        except Exception as e:
            logger.error(f"Error getting strategies: {e}")
            
    async def _check_strategy(self, ticker: str, strategy_data: Dict[str, Any]):
        """Check a single strategy for price target achievements."""
        price_targets = strategy_data.get('price_targets', [])
        entry_price = strategy_data.get('entry_price')
        free_runner = strategy_data.get('freeRunner', False)
        orders = strategy_data.get('orders', [])
        minimum_variation = strategy_data.get('minimum_variation', 0.01)
        
        if not price_targets or not entry_price or not orders:
            return
            
        # Get current stock price
        try:
            current_price = ibkr_service.get_current_stock_price(ticker)
            if not current_price:
                logger.debug(f"Cannot get current price for {ticker}")
                return
                
            logger.debug(f"Checking {ticker}: current=${current_price}, targets={price_targets}, entry=${entry_price}")
            
            # Sort targets to identify first (closest) and last (furthest)
            sorted_targets = sorted(price_targets)
            first_target = sorted_targets[0] if sorted_targets else None
            last_target = sorted_targets[-1] if len(sorted_targets) > 1 else None
            
            # Check if first target is reached
            if first_target and current_price >= first_target:
                await self._handle_first_target_reached(ticker, strategy_data, current_price, entry_price, minimum_variation)
                
            # Check if last target is reached (only if there are multiple targets and free runner is enabled)
            if last_target and len(sorted_targets) > 1 and free_runner and current_price >= last_target:
                await self._handle_last_target_reached(ticker, strategy_data, current_price, last_target, minimum_variation)
                
        except Exception as e:
            logger.error(f"Error checking price for {ticker}: {e}")
            
    async def _handle_first_target_reached(self, ticker: str, strategy_data: Dict[str, Any], 
                                         current_price: float, entry_price: float, minimum_variation: float):
        """Handle when the first (closest) price target is reached - move stop losses to breakeven."""
        price_targets = strategy_data.get('price_targets', [])
        sorted_targets = sorted(price_targets)
        first_target = sorted_targets[0] if sorted_targets else None
        
        logger.info(f"First target reached for {ticker}: current=${current_price}, moving stops to entry=${entry_price}")
        
        # Send Telegram notification
        try:
            action_text = f"Moved all stop losses to breakeven (${entry_price})"
            await penny_stock_notification_service.send_price_target_reached(
                ticker, first_target, current_price, strategy_data, action_text
            )
        except Exception as e:
            logger.error(f"Failed to send price target notification for {ticker}: {e}")
        
        orders = strategy_data.get('orders', [])
        for order in orders:
            stop_loss_info = order.get('stop_loss')
            if stop_loss_info and isinstance(stop_loss_info, dict):
                stop_loss_order_id = stop_loss_info.get('order_id')
                if stop_loss_order_id:
                    try:
                        # Modify stop loss order to entry price
                        new_stop_price = entry_price
                        new_limit_price = entry_price - minimum_variation
                        
                        result = await self._modify_stop_loss_order(
                            stop_loss_order_id, 
                            new_stop_price, 
                            new_limit_price
                        )
                        
                        if result:
                            logger.info(f"Updated stop loss {stop_loss_order_id} to breakeven: stop=${new_stop_price}, limit=${new_limit_price}")
                        else:
                            logger.warning(f"Failed to update stop loss {stop_loss_order_id}")
                            
                    except Exception as e:
                        logger.error(f"Error updating stop loss {stop_loss_order_id}: {e}")
                        
    async def _handle_last_target_reached(self, ticker: str, strategy_data: Dict[str, Any], 
                                        current_price: float, last_target: float, minimum_variation: float):
        """Handle when the last (furthest) target is reached - create trailing stop for free runner."""
        logger.info(f"Last target reached for {ticker}: current=${current_price}, target=${last_target}, creating trailing stop")
        
        # Send Telegram notification
        try:
            action_text = f"Activated free runner: cancelled limit/stop orders, created trailing stop with {self.trailing_stop_percent}% trail"
            await penny_stock_notification_service.send_price_target_reached(
                ticker, last_target, current_price, strategy_data, action_text
            )
        except Exception as e:
            logger.error(f"Failed to send price target notification for {ticker}: {e}")
        
        orders = strategy_data.get('orders', [])
        # Find the order corresponding to the last target
        last_target_order = None
        for order in orders:
            # For now, assume last order corresponds to last target (this could be improved with better mapping)
            last_target_order = order
            
        if not last_target_order:
            logger.warning(f"Cannot find order for last target of {ticker}")
            return
            
        try:
            # Cancel existing limit sell and stop loss orders for this bracket
            limit_sell_info = last_target_order.get('limit_sell')
            stop_loss_info = last_target_order.get('stop_loss')
            
            cancelled_orders = []
            if limit_sell_info and isinstance(limit_sell_info, dict):
                limit_sell_id = limit_sell_info.get('order_id')
                if limit_sell_id:
                    cancel_result = await self._cancel_order(limit_sell_id)
                    if cancel_result:
                        cancelled_orders.append(f"limit_sell:{limit_sell_id}")
                        
            if stop_loss_info and isinstance(stop_loss_info, dict):
                stop_loss_id = stop_loss_info.get('order_id')
                if stop_loss_id:
                    cancel_result = await self._cancel_order(stop_loss_id)
                    if cancel_result:
                        cancelled_orders.append(f"stop_loss:{stop_loss_id}")
                        
            # Create trailing stop limit order
            trailing_amount = last_target * (self.trailing_stop_percent / 100)
            
            # Get stock conid and shares for the trailing stop order
            stock_conid = await self._get_stock_conid_for_ticker(ticker)
            parent_order_id = last_target_order.get('parent_order_id')
            shares = await self._get_order_shares(parent_order_id)
            
            if stock_conid and shares:
                trailing_order_result = await self._create_trailing_stop_order(
                    stock_conid, shares, trailing_amount
                )
                
                if trailing_order_result:
                    logger.info(f"Created trailing stop for {ticker}: cancelled={cancelled_orders}, "
                              f"trailing_amount=${trailing_amount}")
                else:
                    logger.warning(f"Failed to create trailing stop for {ticker}")
                    
        except Exception as e:
            logger.error(f"Error creating trailing stop for {ticker}: {e}")
            
    async def _get_stock_conid_for_ticker(self, ticker: str) -> Optional[int]:
        """Get stock conid for a ticker symbol."""
        try:
            # Use IBKR service to search for the stock
            search_result = ibkr_service.search_contract_by_symbol(ticker, sec_type="STK")
            if search_result and hasattr(search_result, 'data') and search_result.data:
                # Find stock contract (not options)
                for result in search_result.data:
                    if result.get('secType') == 'STK':
                        return int(result.get('conid'))
            return None
        except Exception as e:
            logger.error(f"Error getting conid for {ticker}: {e}")
            return None
            
    async def _get_order_shares(self, order_id: str) -> Optional[int]:
        """Get the number of shares for an order."""
        try:
            # Get orders from IBKR - need to search through orders data
            orders_data = ibkr_service.get_orders_data()
            if orders_data:
                for order in orders_data:
                    if str(order.get('orderId')) == str(order_id):
                        return int(order.get('totalSize', 0))
            return None
        except Exception as e:
            logger.error(f"Error getting shares for order {order_id}: {e}")
            return None
            
    async def _modify_stop_loss_order(self, order_id: str, stop_price: float, limit_price: float) -> bool:
        """Modify an existing stop loss order."""
        try:
            client = ibkr_service.client
            
            # IBKR modify order payload (following pattern from stop_loss_service.py)
            modify_payload = {
                "orderId": order_id,
                "auxPrice": stop_price,  # Stop price
                "price": limit_price     # Limit price
            }
            
            result = client.modify_order(order_id, **modify_payload)
            return result is not None
        except Exception as e:
            logger.error(f"Error modifying stop loss order {order_id}: {e}")
            return False
            
    async def _cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            client = ibkr_service.client
            # Use the delete_order method if available, or fall back to direct HTTP call
            if hasattr(client, 'delete_order'):
                result = client.delete_order(order_id)
            else:
                # Create a simple API call to cancel order
                # This follows the pattern seen in frontend: DELETE /iserver/account/{accountId}/order/{orderId}
                account_id = ibkr_service._current_account_id
                if not account_id:
                    ibkr_service.switch_account()
                    account_id = ibkr_service._current_account_id
                
                # Note: This is a placeholder - we may need to implement a proper cancel method
                # in ibkr_service if the client doesn't have delete_order
                logger.warning(f"No delete_order method found on client, order {order_id} not cancelled")
                return False
                
            return result is not None
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
            
    async def _create_trailing_stop_order(self, conid: int, shares: int, 
                                        trailing_amount: float, limit_offset: float = None) -> bool:
        """Create a trailing stop order."""
        try:
            # Use the existing trailing stop order method from ibkr_service
            result = ibkr_service.place_trailing_stop_order(conid, shares, trailing_amount)
            return result is not None and 'error' not in str(result)
        except Exception as e:
            logger.error(f"Error creating trailing stop order: {e}")
            return False


# Global instance
penny_stock_price_monitor = PennyStockPriceMonitor()