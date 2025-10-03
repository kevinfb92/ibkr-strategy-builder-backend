"""
Penny stock notification service for Telegram alerts
"""
import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PennyStockNotificationService:
    """Service for sending penny stock-related notifications via Telegram"""
    
    def __init__(self):
        self.telegram_service = None
        self._initialize_telegram()
        self._setup_notification_logger()
    
    def _initialize_telegram(self):
        """Initialize telegram service reference"""
        try:
            from .telegram_service import telegram_service
            self.telegram_service = telegram_service
        except Exception as e:
            logger.warning(f"Failed to initialize telegram service: {e}")
    
    def _setup_notification_logger(self):
        """Setup dedicated logger for penny stock notifications"""
        try:
            # Create logs directory if it doesn't exist
            logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
            os.makedirs(logs_dir, exist_ok=True)
            
            # Setup dedicated notification logger
            self.notification_logger = logging.getLogger('penny_stock_notifications')
            self.notification_logger.setLevel(logging.INFO)
            
            # Remove existing handlers to avoid duplicates
            for handler in self.notification_logger.handlers[:]:
                self.notification_logger.removeHandler(handler)
            
            # Create file handler for penny stock notifications
            log_file = os.path.join(logs_dir, 'penny_stock_notifications.log')
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            
            # Create formatter for notifications
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            
            # Add handler to logger
            self.notification_logger.addHandler(file_handler)
            
            # Prevent propagation to root logger to avoid duplicate logs
            self.notification_logger.propagate = False
            
            logger.info(f"Penny stock notification logging setup complete: {log_file}")
            
        except Exception as e:
            logger.error(f"Failed to setup notification logger: {e}")
            self.notification_logger = None
    
    def _log_notification(self, notification_type: str, ticker: str, message: str):
        """Log notification message to file"""
        try:
            if self.notification_logger:
                log_entry = f"[{notification_type}] {ticker} | {message.replace(chr(10), ' | ')}"
                self.notification_logger.info(log_entry)
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")
    
    async def send_buy_order_filled(self, ticker: str, order_data: Dict[str, Any], strategy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send notification when a buy order is filled (position opened)"""
        try:
            # Extract order details
            parent_order_id = order_data.get('parent_order_id', 'Unknown')
            filled_qty = order_data.get('filled_qty', 'Unknown')
            avg_price = order_data.get('avg_price', 'Unknown')
            entry_price = strategy_data.get('entry_price', 'N/A')
            price_targets = strategy_data.get('price_targets', [])
            free_runner = strategy_data.get('freeRunner', False)
            
            # Format price targets display
            targets_text = ", ".join([f"${target:.4f}" for target in price_targets]) if price_targets else "None"
            
            # Build message
            message = f"🚀 <b>PENNYSTOCK - Position Opened</b>\n\n"
            message += f"📊 <b>Ticker:</b> <code>{ticker}</code>\n"
            message += f"🆔 <b>Order ID:</b> <code>{parent_order_id}</code>\n"
            message += f"📈 <b>Filled Qty:</b> {filled_qty} shares\n"
            message += f"💰 <b>Avg Fill Price:</b> ${avg_price}\n\n"
            
            message += f"🎯 <b>Strategy Info:</b>\n"
            message += f"   • Entry Price: ${entry_price}\n"
            message += f"   • Price Targets: {targets_text}\n"
            message += f"   • Free Runner: {'Yes' if free_runner else 'No'}\n\n"
            
            message += f"⏰ <i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
            
            # Log the notification
            self._log_notification("BUY_ORDER_FILLED", ticker, message)
            
            # Send via telegram
            if self.telegram_service:
                result = await self.telegram_service.send_lite_alert(message)
                logger.info(f"Sent penny stock buy notification for {ticker}: {result.get('success', False)}")
                return result
            else:
                logger.warning("Telegram service not available for penny stock notification")
                return {"success": False, "message": "Telegram service not available"}
                
        except Exception as e:
            logger.error(f"Error sending buy order notification for {ticker}: {e}")
            return {"success": False, "message": str(e)}
    
    async def send_sell_order_filled(self, ticker: str, order_data: Dict[str, Any], strategy_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send notification when a sell order is filled (position closed/partial)"""
        try:
            # Extract order details
            parent_order_id = order_data.get('parent_order_id', 'Unknown')
            filled_qty = order_data.get('filled_qty', 'Unknown')
            avg_price = order_data.get('avg_price', 'Unknown')
            entry_price = strategy_data.get('entry_price', 'N/A')
            
            # Calculate P&L if possible
            pnl_text = "N/A"
            pnl_emoji = "💰"
            try:
                if avg_price != 'Unknown' and entry_price != 'N/A' and filled_qty != 'Unknown':
                    sell_price = float(avg_price)
                    buy_price = float(entry_price)
                    qty = float(filled_qty)
                    pnl = (sell_price - buy_price) * qty
                    pnl_text = f"${pnl:.2f}"
                    pnl_emoji = "📈" if pnl >= 0 else "📉"
            except Exception:
                pass
            
            # Build message
            message = f"💸 <b>PENNYSTOCK - Position Closed</b>\n\n"
            message += f"📊 <b>Ticker:</b> <code>{ticker}</code>\n"
            message += f"🆔 <b>Order ID:</b> <code>{parent_order_id}</code>\n"
            message += f"📉 <b>Sold Qty:</b> {filled_qty} shares\n"
            message += f"💰 <b>Avg Sale Price:</b> ${avg_price}\n"
            message += f"🏷️ <b>Entry Price:</b> ${entry_price}\n"
            message += f"{pnl_emoji} <b>P&L:</b> {pnl_text}\n\n"
            
            message += f"⏰ <i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
            
            # Log the notification
            self._log_notification("SELL_ORDER_FILLED", ticker, message)
            
            # Send via telegram
            if self.telegram_service:
                result = await self.telegram_service.send_lite_alert(message)
                logger.info(f"Sent penny stock sell notification for {ticker}: {result.get('success', False)}")
                return result
            else:
                logger.warning("Telegram service not available for penny stock notification")
                return {"success": False, "message": "Telegram service not available"}
                
        except Exception as e:
            logger.error(f"Error sending sell order notification for {ticker}: {e}")
            return {"success": False, "message": str(e)}
    
    async def send_price_target_reached(self, ticker: str, target_price: float, current_price: float, 
                                      strategy_data: Dict[str, Any], action_taken: str) -> Dict[str, Any]:
        """Send notification when a price target is reached"""
        try:
            entry_price = strategy_data.get('entry_price', 'N/A')
            price_targets = strategy_data.get('price_targets', [])
            free_runner = strategy_data.get('freeRunner', False)
            
            # Determine which target was hit
            target_position = "Unknown"
            if price_targets:
                sorted_targets = sorted(price_targets)
                if target_price in sorted_targets:
                    target_position = f"{sorted_targets.index(target_price) + 1} of {len(sorted_targets)}"
            
            # Build message
            message = f"🎯 <b>PENNYSTOCK - Price Target Reached</b>\n\n"
            message += f"📊 <b>Ticker:</b> <code>{ticker}</code>\n"
            message += f"🎯 <b>Target Hit:</b> ${target_price:.4f} (Target {target_position})\n"
            message += f"📈 <b>Current Price:</b> ${current_price:.4f}\n"
            message += f"🏷️ <b>Entry Price:</b> ${entry_price}\n\n"
            
            message += f"⚙️ <b>Action Taken:</b>\n"
            message += f"   {action_taken}\n\n"
            
            if free_runner and len(price_targets) > 1 and target_price == max(price_targets):
                message += f"🚀 <b>Free Runner Activated!</b>\n"
            
            message += f"⏰ <i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
            
            # Log the notification
            self._log_notification("PRICE_TARGET_REACHED", ticker, message)
            
            # Send via telegram
            if self.telegram_service:
                result = await self.telegram_service.send_lite_alert(message)
                logger.info(f"Sent penny stock target notification for {ticker}: {result.get('success', False)}")
                return result
            else:
                logger.warning("Telegram service not available for penny stock notification")
                return {"success": False, "message": "Telegram service not available"}
                
        except Exception as e:
            logger.error(f"Error sending price target notification for {ticker}: {e}")
            return {"success": False, "message": str(e)}


# Global instance
penny_stock_notification_service = PennyStockNotificationService()