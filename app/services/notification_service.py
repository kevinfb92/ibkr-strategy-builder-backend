#!/usr/bin/env python3
"""
Notification Service for handling incoming notifications
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import logging

from .alerter_manager import alerter_manager
from .handlers.lite_handlers import (
    LiteRealDayTradingHandler, 
    LiteDemslayerHandler, 
    LiteProfAndKianHandler,
    LiteRobinDaHoodHandler
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """Data class for notification structure"""
    not_title: str
    not_ticker: str
    notification: str
    timestamp: datetime
    
    def __post_init__(self):
        """Validate notification data after initialization"""
        if not self.not_title or not self.not_title.strip():
            raise ValueError("not_title cannot be empty")
        if not self.not_ticker or not self.not_ticker.strip():
            raise ValueError("not_ticker cannot be empty")
        if not self.notification or not self.notification.strip():
            raise ValueError("notification cannot be empty")


class NotificationService:
    """Service for handling and processing notifications"""
    
    def __init__(self):
        self.notifications: List[Notification] = []
        # Initialize lite handlers
        self.lite_handlers = {
            'real-day-trading': LiteRealDayTradingHandler(),
            'demslayer-spx-alerts': LiteDemslayerHandler(),
            'prof-and-kian-alerts': LiteProfAndKianHandler(),
            'robindahood-alerts': LiteRobinDaHoodHandler()
        }
        logger.info("NotificationService initialized")
    
    async def process_notification(self, not_title: str, not_ticker: str, notification: str) -> dict:
        """
        Process an incoming notification using the alerter management system
        
        Args:
            not_title: Title of the notification
            not_ticker: Ticker symbol related to the notification
            notification: Main notification message
            
        Returns:
            dict: Processing result with status and notification data
        """
        try:
            # Clean and validate input
            title = not_title.strip() if not_title else ""
            ticker = not_ticker.strip() if not_ticker else ""
            message = notification.strip() if notification else ""
            
            if not title and not ticker and not message:
                raise ValueError("All fields cannot be empty")
            
            # Create notification object for storage
            new_notification = Notification(
                not_title=title or "Unknown",
                not_ticker=ticker.upper() or "UNKNOWN",
                notification=message or "No message",
                timestamp=datetime.now()
            )
            
            # Store the notification
            self.notifications.append(new_notification)
            
            # Print notification details for monitoring
            # print("=" * 60)
            # print("🔔 NEW NOTIFICATION RECEIVED")
            # print("=" * 60)
            # print(f"📋 Title: {new_notification.not_title}")
            # print(f"📊 Ticker: {new_notification.not_ticker}")
            # print(f"💬 Message: {new_notification.notification}")
            # print(f"⏰ Timestamp: {new_notification.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            # print("=" * 60)
            
            # Try lite handlers first, then fall back to old alerter manager
            # print("🔄 Processing with lite handlers system...")
            alerter_result = await self._try_lite_handlers_first(title, ticker, message)
            
            if not alerter_result:
                # Fall back to old alerter manager if no lite handler found
                # print("🔄 Falling back to old alerter management system...")
                alerter_result = await alerter_manager.process_notification(
                    title=title,        # The alerter name (from title field: "Real Day Trading")
                    message=ticker,     # The ticker/message field (from message field: "Long $AAPL") 
                    subtext=message     # The main content (from notification field: "Going long on Apple...")
                )
            
            # Print alerter processing result
            if alerter_result.get("success"):
                alerter_data = alerter_result.get("data", {})
                detected_alerter = alerter_data.get("alerter", "UNKNOWN")
                handler_used = alerter_data.get("handler_used", "Unknown")
                
                # print("✅ ALERTER PROCESSING SUCCESSFUL")
                # print(f"🎯 Detected Alerter: {detected_alerter}")
                # print(f"⚙️  Handler Used: {handler_used}")
                
                if "routed_to" in alerter_data:
                    pass
                    # print(f"📡 Routed To: {alerter_data['routed_to']}")
            else:
                pass
                # print("❌ ALERTER PROCESSING FAILED")
                # print(f"🚨 Error: {alerter_result.get('message', 'Unknown error')}")
            
            # print("=" * 60)
            
            # Log the notification
            logger.info(f"Processed notification for {new_notification.not_ticker}: {new_notification.not_title}")
            
            # Extract Telegram message content if available
            telegram_message = None
            if alerter_result.get("success") and alerter_result.get("data"):
                telegram_sent = alerter_result["data"].get("telegram_sent", {})
                if telegram_sent.get("success"):
                    telegram_message = telegram_sent.get("formatted_message")
            
            return {
                "success": True,
                "message": "Notification processed successfully",
                "data": {
                    "id": len(self.notifications),  # Simple ID based on count
                    "title": new_notification.not_title,  # Changed from not_title
                    "message": new_notification.not_ticker,  # Changed from not_ticker  
                    "subtext": new_notification.notification,  # Changed from notification
                    "timestamp": new_notification.timestamp.isoformat(),
                    "alerter_processing": alerter_result,  # Include full alerter result
                    "telegram_message": telegram_message,  # Include formatted Telegram message
                    "total_notifications": len(self.notifications)
                }
            }
            
        except ValueError as e:
            error_msg = f"Invalid notification data: {str(e)}"
            logger.error(error_msg)
            # print(f"❌ ERROR: {error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "data": None
            }
        except Exception as e:
            error_msg = f"Error processing notification: {str(e)}"
            logger.error(error_msg)
            # print(f"❌ UNEXPECTED ERROR: {error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "data": None
            }
    
    def get_notifications(self, limit: Optional[int] = None) -> List[dict]:
        """
        Get stored notifications
        
        Args:
            limit: Maximum number of notifications to return (newest first)
            
        Returns:
            List of notification dictionaries
        """
        notifications = self.notifications.copy()
        notifications.reverse()  # Show newest first
        
        if limit:
            notifications = notifications[:limit]
        
        return [
            {
                "id": len(self.notifications) - self.notifications.index(notif),
                "title": notif.not_title,  # Changed from not_title
                "message": notif.not_ticker,  # Changed from not_ticker
                "subtext": notif.notification,  # Changed from notification
                "timestamp": notif.timestamp.isoformat()
            }
            for notif in notifications
        ]
    
    def get_notification_count(self) -> int:
        """Get total number of notifications received"""
        return len(self.notifications)
    
    def clear_notifications(self) -> dict:
        """Clear all stored notifications"""
        count = len(self.notifications)
        self.notifications.clear()
        logger.info(f"Cleared {count} notifications")
        # print(f"🧹 Cleared {count} notifications")
        return {
            "success": True,
            "message": f"Cleared {count} notifications",
            "cleared_count": count
        }


    async def _try_lite_handlers_first(self, title: str, ticker: str, message: str) -> Optional[dict]:
        """Try to route to lite handlers first"""
        try:
            # Detect alerter from title or message
            detected_alerter = None
            
            # Check title first for direct alerter name
            title_lower = title.lower() if title else ""
            for alerter_name in self.lite_handlers.keys():
                # More flexible matching for demslayer
                if alerter_name == 'demslayer-spx-alerts':
                    if 'demslayer' in title_lower or 'demspx' in title_lower:
                        detected_alerter = alerter_name
                        break
                # Special matching for real-day-trading
                elif alerter_name == 'real-day-trading':
                    if 'real day trading' in title_lower or 'realdaytrading' in title_lower:
                        detected_alerter = alerter_name
                        break
                # Special matching for robindahood-alerts
                elif alerter_name == 'robindahood-alerts':
                    if 'robin da hood' in title_lower or 'robindahood' in title_lower or 'robin hood' in title_lower:
                        detected_alerter = alerter_name
                        break
                # Standard matching for others
                elif alerter_name.replace('-', '').replace('_', '') in title_lower.replace('-', '').replace('_', '').replace(' ', ''):
                    detected_alerter = alerter_name
                    break
            
            # Check message for alerter prefix pattern
            if not detected_alerter and ticker:
                ticker_lower = ticker.lower()
                for alerter_name in self.lite_handlers.keys():
                    # More flexible matching for demslayer
                    if alerter_name == 'demslayer-spx-alerts':
                        if 'demslayer' in ticker_lower or 'demspx' in ticker_lower:
                            detected_alerter = alerter_name
                            break
                    # Special matching for real-day-trading
                    elif alerter_name == 'real-day-trading':
                        if 'real day trading' in ticker_lower or 'realdaytrading' in ticker_lower:
                            detected_alerter = alerter_name
                            break
                    # Standard matching for others
                    elif ticker_lower.startswith(alerter_name) or alerter_name.replace('-', '') in ticker_lower:
                        detected_alerter = alerter_name
                        break
            
            # Check message content for alerter patterns
            if not detected_alerter and message:
                message_lower = message.lower()
                for alerter_name in self.lite_handlers.keys():
                    # More flexible matching for demslayer
                    if alerter_name == 'demslayer-spx-alerts':
                        if 'demslayer' in message_lower or 'demspx' in message_lower:
                            detected_alerter = alerter_name
                            break
                    # Special matching for real-day-trading
                    elif alerter_name == 'real-day-trading':
                        if 'real day trading' in message_lower or 'realdaytrading' in message_lower:
                            detected_alerter = alerter_name
                            break
                    # Standard matching for others
                    elif alerter_name in message_lower or alerter_name.replace('-', '') in message_lower:
                        detected_alerter = alerter_name
                        break
            
            if detected_alerter and detected_alerter in self.lite_handlers:
                logger.info(f"Routing notification to {detected_alerter} lite handler")
                handler = self.lite_handlers[detected_alerter]
                
                # Process with lite handler
                result = await handler.process_notification_with_conid({
                    'title': title,
                    'message': ticker,   # The actual alert content is in ticker field
                    'subtext': message   # The notification field content
                })
                
                return {
                    "success": True,
                    "message": f"Processed with {detected_alerter} lite handler",
                    "data": {
                        "alerter": detected_alerter,
                        "handler_used": f"Lite{handler.__class__.__name__}",
                        "lite_mode": True,
                        **result
                    }
                }
            else:
                logger.info(f"No lite handler found for alerter: {detected_alerter or 'UNKNOWN'} - using generic")
                return None
                
        except Exception as e:
            logger.error(f"Error in lite handler routing: {e}")
            return None


# Create global notification service instance
notification_service = NotificationService()
