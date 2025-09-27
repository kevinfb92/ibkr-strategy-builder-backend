"""
Nyrleth alerter handler
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class NyrlethHandler:
    """Handler for Nyrleth notifications"""
    
    def __init__(self):
        self.alerter_name = "Nyrleth"
    
    def process_notification(self, title: str, message: str, subtext: str) -> Dict[str, Any]:
        """
        Process Nyrleth notification
        
        Args:
            title: The notification title
            message: The message/ticker info
            subtext: The main notification content
            
        Returns:
            Dict with processed notification data
        """
        try:
            logger.info(f"Processing {self.alerter_name} notification")
            
            # Nyrleth specific processing logic
            processed_data = {
                "alerter": self.alerter_name,
                "original_title": title,
                "original_message": message,
                "original_subtext": subtext,
                "processed": True
            }
            
            # TODO: Add specific parsing logic for Nyrleth format
            # Nyrleth might have different notification patterns
            processed_data.update({
                "ticker": self._extract_ticker(message, subtext),
                "signal_type": self._extract_signal_type(subtext),
                "confidence": self._extract_confidence(subtext),
                "timestamp": self._get_timestamp()
            })
            
            processed_data["order_result"] = None
            return {
                "success": True,
                "message": f"Successfully processed {self.alerter_name} notification",
                "data": processed_data
            }
            
        except Exception as e:
            logger.error(f"Error processing {self.alerter_name} notification: {e}")
            return {
                "success": False,
                "message": f"Failed to process {self.alerter_name} notification",
                "error": str(e)
            }
    
    def _extract_ticker(self, message: str, subtext: str) -> str:
        """Extract ticker symbol from the notification"""
        # Look in message first, then subtext
        text_to_search = f"{message} {subtext}".upper()
        
        import re
        ticker_patterns = [
            r'\b([A-Z]{1,5})\b',  # 1-5 uppercase letters
            r'\$([A-Z]{1,5})\b',  # $TICKER format
        ]
        
        for pattern in ticker_patterns:
            matches = re.findall(pattern, text_to_search)
            if matches:
                return matches[0]
        
        return message.upper() if message else "UNKNOWN"
    
    def _extract_signal_type(self, subtext: str) -> str:
        """Extract signal type from subtext"""
        if not subtext:
            return "UNKNOWN"
            
        subtext_lower = subtext.lower()
        
        if any(word in subtext_lower for word in ["breakout", "resistance", "support"]):
            return "TECHNICAL"
        elif any(word in subtext_lower for word in ["volume", "unusual"]):
            return "VOLUME"
        elif any(word in subtext_lower for word in ["news", "earnings", "announcement"]):
            return "FUNDAMENTAL"
        
        return "GENERAL"
    
    def _extract_confidence(self, subtext: str) -> str:
        """Extract confidence level from subtext"""
        if not subtext:
            return "MEDIUM"
            
        subtext_lower = subtext.lower()
        
        if any(word in subtext_lower for word in ["strong", "high", "confirmed"]):
            return "HIGH"
        elif any(word in subtext_lower for word in ["weak", "low", "uncertain"]):
            return "LOW"
        
        return "MEDIUM"
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()
