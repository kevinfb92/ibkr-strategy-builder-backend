"""
Lite Handlers for processing notifications with contract ID (CONID) integration
These handlers differentiate between BUY alerts (new positions) and UPDATE alerts (general updates)
"""

import json
import logging
import re
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from ..ibkr_service import ibkr_service
from ..telegram_service import telegram_service

logger = logging.getLogger(__name__)

# Path to alerts storage
ALERTS_FILE = os.path.join(os.path.dirname(__file__), "../../../data/alerts/alerts.json")

def _load_alerts() -> Dict:
    """Load alerts from JSON file"""
    try:
        if os.path.exists(ALERTS_FILE):
            with open(ALERTS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Error loading alerts: {e}")
        return {}

def _save_alerts(alerts: Dict) -> None:
    """Save alerts to JSON file"""
    try:
        os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
        with open(ALERTS_FILE, 'w') as f:
            json.dump(alerts, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving alerts: {e}")

async def _detect_buy_alert(message: str) -> Optional[Dict[str, Any]]:
    """
    Detect if message is a buy alert by finding strike+side and stock before it
    Returns: {ticker, strike, side, stock_conid} or None
    """
    # Find all strike+side patterns (e.g., "175P", "600C", "123.5C")
    strike_patterns = re.finditer(r'(\d+(?:\.\d+)?)([CP])', message.upper())
    
    for match in strike_patterns:
        strike = float(match.group(1))
        side = match.group(2)
        
        # Look for stock symbol immediately before the strike
        before_strike = message[:match.start()].strip()
        
        # Find the last word before the strike (should be the stock symbol)
        words_before = re.findall(r'\b([A-Z]{1,5})\b', before_strike.upper())
        
        if words_before:
            potential_ticker = words_before[-1]  # Last word before strike
            
            # Verify it's a real stock by getting CONID
            try:
                stock_conid = await ibkr_service.get_stock_conid(potential_ticker)
                if stock_conid:
                    return {
                        "ticker": potential_ticker,
                        "strike": strike,
                        "side": "CALL" if side == "C" else "PUT",
                        "stock_conid": stock_conid
                    }
            except Exception as e:
                logger.debug(f"Could not verify {potential_ticker} as stock: {e}")
                continue
    
    return None

def _format_expiry_for_display(expiry: str) -> str:
    """Format expiry for readable display in Telegram messages"""
    try:
        # If expiry is in MMDD format (like "0929", "1030")
        if len(expiry) == 4 and expiry.isdigit():
            month = int(expiry[:2])
            day = int(expiry[2:])
            # Create date object for current year
            current_year = datetime.now().year
            exp_date = datetime(current_year, month, day)
            return exp_date.strftime("%b %d")  # "Sep 29", "Oct 30"
        
        # If expiry is in MM/DD format
        elif "/" in expiry:
            parts = expiry.split("/")
            if len(parts) == 2:
                month = int(parts[0])
                day = int(parts[1])
                current_year = datetime.now().year
                exp_date = datetime(current_year, month, day)
                return exp_date.strftime("%b %d")
        
        # If expiry is 4 digits but not current year pattern, try as YYMM
        elif len(expiry) == 4 and expiry.isdigit():
            return expiry  # Return as-is if can't parse
            
        # Return as-is if can't parse
        return expiry
        
    except (ValueError, IndexError):
        # If any parsing fails, return the original expiry
        return expiry

def _extract_expiry(message: str, strike_position: int) -> str:
    """Extract expiry from message (must come after strike position)"""
    # Look for expiry patterns after the strike position
    message_after_strike = message[strike_position:]
    
    # Common expiry patterns: 10/25, OCT25, 1025, etc.
    expiry_patterns = [
        r'(\d{1,2})/(\d{1,2})',  # 10/25
        r'(\d{4})',              # 1025
        r'([A-Z]{3})(\d{2})'     # OCT25
    ]
    
    for pattern in expiry_patterns:
        match = re.search(pattern, message_after_strike.upper())
        if match:
            # Format as MM/DD for consistency
            if '/' in match.group(0):
                return match.group(0)
            # Convert other formats to MM/DD if needed
            # For now, return as is
            return match.group(0)
    
    # Default to current date (0DTE)
    return datetime.now().strftime("%m/%d")

class LiteRealDayTradingHandler:
    """Lite handler for Real Day Trading notifications"""
    
    def __init__(self):
        self.alerter_name = "real-day-trading"
        logger.info(f"Initialized {self.__class__.__name__}")
    
    async def process_notification_with_conid(self, notification_data: Dict[str, str]) -> Dict[str, Any]:
        """Process Real Day Trading notification - detect BUY vs UPDATE alerts"""
        try:
            title = notification_data.get('title', '')
            message = notification_data.get('message', '')
            subtext = notification_data.get('subtext', '')
            
            logger.info(f"Processing RDT notification: {title} - {message}")
            
            # Try to detect if this is a BUY alert using RDT-specific rules
            buy_alert_info = await self._detect_rdt_buy_alert(message)
            
            if buy_alert_info:
                # This is a BUY alert - process new position
                return await self._process_buy_alert(buy_alert_info, message, title)
            else:
                # This is an UPDATE alert - send update for all stored alerts
                return await self._process_update_alert(message, title)
            
        except Exception as e:
            logger.error(f"Error processing RDT notification: {e}")
            return {
                "alerter": self.alerter_name,
                "error": str(e),
                "processed_at": datetime.now().isoformat()
            }
    
    async def _detect_rdt_buy_alert(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect Real Day Trading buy alerts using specific rules:
        - Long indicates calls, Short indicates puts
        - Stock symbols are in $NAME format
        - Get closest ITM option with nearest expiry
        """
        try:
            message_upper = message.upper()
            
            # Check for Long (calls) or Short (puts) at the start
            side = None
            if message_upper.startswith('LONG'):
                side = "CALL"
            elif message_upper.startswith('SHORT'):
                side = "PUT"
            else:
                return None
            
            # Look for stock symbol in $NAME format
            stock_pattern = r'\$([A-Z]{1,5})'
            match = re.search(stock_pattern, message_upper)
            if not match:
                return None
            
            ticker = match.group(1)
            
            # Verify it's a real stock by getting CONID
            try:
                stock_conid = await ibkr_service.get_stock_conid(ticker)
                if not stock_conid:
                    return None
            except Exception as e:
                logger.debug(f"Could not verify {ticker} as stock: {e}")
                return None
            
            # Get current stock price to find closest ITM strike
            try:
                # For now, we'll use a default strike - we can enhance this later
                # to get the actual stock price and calculate closest ITM
                # This would require additional IBKR API calls
                current_price = 100.0  # Placeholder - should get actual price
                
                # Calculate closest ITM strike (simplified)
                if side == "CALL":
                    # For calls, ITM = strike below current price
                    strike = round(current_price * 0.95)  # 5% below current price
                else:
                    # For puts, ITM = strike above current price  
                    strike = round(current_price * 1.05)  # 5% above current price
                
                # Use nearest Friday expiry (simplified - assume weekly options)
                today = datetime.now()
                days_to_friday = (4 - today.weekday()) % 7  # Friday is weekday 4
                if days_to_friday == 0:  # If today is Friday, use next Friday
                    days_to_friday = 7
                
                expiry_date = today + timedelta(days=days_to_friday)
                expiry = expiry_date.strftime("%m%d")  # Format as MMDD
                
                return {
                    "ticker": ticker,
                    "strike": float(strike),
                    "side": side,
                    "stock_conid": stock_conid,
                    "expiry": expiry
                }
                
            except Exception as e:
                logger.error(f"Error calculating option details for {ticker}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error detecting RDT buy alert: {e}")
            return None
    
    async def _process_buy_alert(self, buy_info: Dict[str, Any], message: str, title: str) -> Dict[str, Any]:
        """Process a BUY alert - get CONIDs, store alert, send Telegram"""
        try:
            ticker = buy_info["ticker"]
            strike = buy_info["strike"]
            side = buy_info["side"]
            stock_conid = buy_info["stock_conid"]
            
            # Get expiry from buy_info (RDT specific) or extract from message (other alerters)
            if "expiry" in buy_info:
                expiry = buy_info["expiry"]
            else:
                # Extract expiry (default to today if not found) - for backward compatibility
                strike_match = re.search(rf'{strike}[CP]', message.upper())
                strike_pos = strike_match.end() if strike_match else len(message)
                expiry = _extract_expiry(message, strike_pos)
            
            # Get option contract CONID
            option_conid = None
            try:
                option_conid = await ibkr_service.get_option_conid(
                    ticker=ticker,
                    strike=strike,
                    side=side,
                    expiry=expiry
                )
            except Exception as e:
                logger.warning(f"Could not get option CONID: {e}")
            
            # Store the alert
            self._store_alert(ticker, strike, side, expiry, stock_conid, option_conid)
            
            # Send Telegram message
            telegram_result = await self._send_buy_telegram(
                ticker, strike, side, expiry, stock_conid, option_conid, message
            )
            
            return {
                "alerter": self.alerter_name,
                "alert_type": "BUY",
                "ticker": ticker,
                "strike": strike,
                "side": side,
                "expiry": expiry,
                "stock_conid": stock_conid,
                "option_conid": option_conid,
                "telegram_sent": telegram_result,
                "processed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing buy alert: {e}")
            return {"error": str(e)}
    
    async def _process_update_alert(self, message: str, title: str) -> Dict[str, Any]:
        """Process an UPDATE alert - send Telegram with all stored alerts"""
        try:
            # Send update Telegram with all stored alerts
            telegram_result = await self._send_update_telegram(message)
            
            return {
                "alerter": self.alerter_name,
                "alert_type": "UPDATE",
                "message": message,
                "telegram_sent": telegram_result,
                "processed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing update alert: {e}")
            return {"error": str(e)}
    
    def _store_alert(self, ticker: str, strike: float, side: str, expiry: str, 
                     stock_conid: int, option_conid: Optional[int]) -> None:
        """Store alert in alerts.json"""
        try:
            alerts = _load_alerts()
            
            if self.alerter_name not in alerts:
                alerts[self.alerter_name] = {}
            
            alerts[self.alerter_name][ticker] = {
                "open": True,
                "created_at": datetime.now().isoformat(),
                "option_conids": [option_conid] if option_conid else [],
                "option_conid": option_conid,
                "sentiment": "bullish" if side == "CALL" else "bearish",
                "conid": stock_conid,
                "alert_details": {
                    "ticker": ticker,
                    "strike": str(int(strike)) if strike.is_integer() else str(strike),
                    "side": "C" if side == "CALL" else "P",
                    "expiry": expiry,
                    "is_bullish": side == "CALL"
                }
            }
            
            _save_alerts(alerts)
            logger.info(f"Stored {ticker} {strike}{side[0]} alert for {self.alerter_name}")
            
        except Exception as e:
            logger.error(f"Error storing alert: {e}")
    
    async def _send_buy_telegram(self, ticker: str, strike: float, side: str, expiry: str,
                                stock_conid: int, option_conid: Optional[int], message: str) -> Dict[str, Any]:
        """Send BUY alert Telegram message"""
        try:
            # Format the message
            side_short = "C" if side == "CALL" else "P"
            emoji = "🔴 📉" if side == "PUT" else "🟢 📈"
            
            telegram_message = f"🚨 {self.alerter_name.upper()}\n{message}\n\n"
            formatted_expiry = _format_expiry_for_display(expiry)
            telegram_message += f"{emoji} {ticker} - {int(strike) if strike.is_integer() else strike}{side_short} - {formatted_expiry}"
            
            # Add links if CONIDs available
            if stock_conid:
                chain_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{stock_conid}/option/option.chain?source=onebar&u=false"
                telegram_message += f"  <a href='{chain_link}'>Option Chain</a>"
            
            if option_conid:
                quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                telegram_message += f" | <a href='{quote_link}'>🔗 Option Quote</a>"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending buy telegram: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_update_telegram(self, message: str) -> Dict[str, Any]:
        """Send UPDATE alert Telegram message with all stored alerts"""
        try:
            alerts = _load_alerts()
            alerter_alerts = alerts.get(self.alerter_name, {})
            
            telegram_message = f"🟡 {self.alerter_name.upper()}\n{message}\n\n"
            
            # Add all stored alerts with option quote links
            for ticker, alert_data in alerter_alerts.items():
                if alert_data.get("open") and alert_data.get("option_conid"):
                    details = alert_data["alert_details"]
                    emoji = "🔴" if details["side"] == "P" else "🟢"
                    
                    option_conid = alert_data["option_conid"]
                    quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                    
                    # Format expiry date for readability
                    formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{emoji} {ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\n"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending update telegram: {e}")
            return {"success": False, "error": str(e)}


class LiteDemslayerHandler:
    """Lite handler for Demslayer SPX notifications"""
    
    def __init__(self):
        self.alerter_name = "demslayer"
        logger.info(f"Initialized {self.__class__.__name__}")
    
    async def process_notification_with_conid(self, notification_data: Dict[str, str]) -> Dict[str, Any]:
        """Process Demslayer notification - detect BUY vs UPDATE alerts"""
        try:
            title = notification_data.get('title', '')
            message = notification_data.get('message', '')
            subtext = notification_data.get('subtext', '')
            
            logger.info(f"Processing Demslayer notification: {title} - {message}")
            
            # Try to detect if this is a BUY alert (SPX-specific)
            buy_alert_info = await self._detect_spx_buy_alert(message)
            
            if buy_alert_info:
                # This is a BUY alert - process new position
                return await self._process_buy_alert(buy_alert_info, message, title)
            else:
                # This is an UPDATE alert - send update for all stored alerts
                return await self._process_update_alert(message, title)
            
        except Exception as e:
            logger.error(f"Error processing Demslayer notification: {e}")
            return {
                "alerter": self.alerter_name,
                "error": str(e),
                "processed_at": datetime.now().isoformat()
            }
    
    async def _detect_spx_buy_alert(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect if message is a SPX buy alert by finding any strike + side pattern
        Since Demslayer only alerts SPX option trades, any strike+side = BUY alert
        Returns: {ticker, strike, side, stock_conid, expiry} or None
        """
        # Look for any strike+side patterns (e.g., "5950C", "6000P", "123.5C")
        # Since Demslayer only does SPX, any strike+side pattern is a BUY alert
        strike_match = re.search(r'(\d+(?:\.\d+)?)([CP])', message.upper())
        
        if strike_match:
            strike = float(strike_match.group(1))
            side = "CALL" if strike_match.group(2) == "C" else "PUT"
            
            # Get SPX CONID (no need to verify since Demslayer only does SPX)
            try:
                spx_conid = await ibkr_service.get_index_conid("SPX")
                if spx_conid:
                    # Look for explicit expiry after strike+side (avoid matching the strike itself)
                    strike_side_pattern = strike_match.group(0)  # e.g., "6000C"
                    message_after_strike = message[strike_match.end():]  # Everything after "6000C"
                    
                    # Look for valid expiry patterns in the remaining message
                    # Valid formats: MMDD (like 0930, 1003, 1025), MM/DD, MM-DD
                    expiry_patterns = [
                        r'(\d{2}/\d{2})',           # MM/DD format (10/03)
                        r'(\d{2}-\d{2})',           # MM-DD format (10-03)
                        r'(0\d[0-3]\d)',            # 0DTE format starting with 0 (0930, 1003, etc.)
                        r'(1[0-2][0-3]\d)',         # Month 10-12 format (1003, 1025, 1201, etc.)
                    ]
                    
                    expiry = None
                    for pattern in expiry_patterns:
                        expiry_match = re.search(pattern, message_after_strike)
                        if expiry_match:
                            raw_expiry = expiry_match.group(1)
                            # Normalize to MMDD format
                            if '/' in raw_expiry:
                                expiry = raw_expiry.replace('/', '')
                            elif '-' in raw_expiry:
                                expiry = raw_expiry.replace('-', '')
                            else:
                                expiry = raw_expiry
                            break
                    
                    # If no valid expiry found, default to 0DTE (current day)
                    if not expiry:
                        # For testing: if weekend, use Monday's date
                        today = datetime.now()
                        if today.weekday() >= 5:  # Saturday (5) or Sunday (6)
                            # Find next Monday
                            if today.weekday() == 5:  # Saturday
                                days_until_monday = 2
                            else:  # Sunday (weekday == 6)
                                days_until_monday = 1
                            trading_date = today + timedelta(days=days_until_monday)
                        else:
                            trading_date = today
                        
                        expiry = trading_date.strftime("%m%d")
                        logger.info(f"No valid expiry found in message, defaulting to 0DTE: {expiry}")
                    else:
                        logger.info(f"Found valid expiry: {expiry}")
                    
                    return {
                        "ticker": "SPX",
                        "strike": strike,
                        "side": side,
                        "stock_conid": spx_conid,
                        "expiry": expiry
                    }
            except Exception as e:
                logger.debug(f"Could not get SPX CONID: {e}")
        
        return None
    
    async def _process_buy_alert(self, buy_info: Dict[str, Any], message: str, title: str) -> Dict[str, Any]:
        """Process a BUY alert - get CONIDs, store alert, send Telegram"""
        try:
            ticker = buy_info["ticker"]
            strike = buy_info["strike"]
            side = buy_info["side"]
            stock_conid = buy_info["stock_conid"]
            expiry = buy_info.get("expiry")
            
            # Demslayer provides expiry in the buy_info, no need to extract again
            # (expiry is already handled in _detect_spx_buy_alert method)
            
            # Get option contract CONID
            option_conid = None
            try:
                option_conid = await ibkr_service.get_option_conid(
                    ticker=ticker,
                    strike=strike,
                    side=side,
                    expiry=expiry
                )
            except Exception as e:
                logger.warning(f"Could not get option CONID: {e}")
            
            # Store the alert
            self._store_alert(ticker, strike, side, expiry, stock_conid, option_conid)
            
            # Send Telegram message
            telegram_result = await self._send_buy_telegram(
                ticker, strike, side, expiry, stock_conid, option_conid, message
            )
            
            return {
                "alerter": self.alerter_name,
                "alert_type": "BUY",
                "ticker": ticker,
                "strike": strike,
                "side": side,
                "expiry": expiry,
                "stock_conid": stock_conid,
                "option_conid": option_conid,
                "telegram_sent": telegram_result,
                "processed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing buy alert: {e}")
            return {"error": str(e)}
    
    async def _process_update_alert(self, message: str, title: str) -> Dict[str, Any]:
        """Process an UPDATE alert - send Telegram with all stored alerts"""
        try:
            # Send update Telegram with all stored alerts
            telegram_result = await self._send_update_telegram(message)
            
            return {
                "alerter": self.alerter_name,
                "alert_type": "UPDATE",
                "message": message,
                "telegram_sent": telegram_result,
                "processed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing update alert: {e}")
            return {"error": str(e)}
    
    def _store_alert(self, ticker: str, strike: float, side: str, expiry: str, 
                     stock_conid: int, option_conid: Optional[int]) -> None:
        """Store alert in alerts.json"""
        try:
            alerts = _load_alerts()
            
            if self.alerter_name not in alerts:
                alerts[self.alerter_name] = {}
            
            alerts[self.alerter_name][ticker] = {
                "open": True,
                "created_at": datetime.now().isoformat(),
                "option_conids": [option_conid] if option_conid else [],
                "option_conid": option_conid,
                "sentiment": "bullish" if side == "CALL" else "bearish",
                "conid": stock_conid,
                "alert_details": {
                    "ticker": ticker,
                    "strike": str(int(strike)) if strike.is_integer() else str(strike),
                    "side": "C" if side == "CALL" else "P",
                    "expiry": expiry,
                    "is_bullish": side == "CALL"
                }
            }
            
            _save_alerts(alerts)
            logger.info(f"Stored {ticker} {strike}{side[0]} alert for {self.alerter_name}")
            
        except Exception as e:
            logger.error(f"Error storing alert: {e}")
    
    async def _send_buy_telegram(self, ticker: str, strike: float, side: str, expiry: str,
                                stock_conid: int, option_conid: Optional[int], message: str) -> Dict[str, Any]:
        """Send BUY alert Telegram message"""
        try:
            # Format the message
            side_short = "C" if side == "CALL" else "P"
            emoji = "🔴 📉" if side == "PUT" else "🟢 📈"
            
            telegram_message = f"🚨 {self.alerter_name.upper()}\n{message}\n\n"
            formatted_expiry = _format_expiry_for_display(expiry)
            telegram_message += f"{emoji} {ticker} - {int(strike) if strike.is_integer() else strike}{side_short} - {formatted_expiry}"
            
            # Add links if CONIDs available
            if stock_conid:
                chain_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{stock_conid}/option/option.chain?source=onebar&u=false"
                telegram_message += f"  <a href='{chain_link}'>Option Chain</a>"
            
            if option_conid:
                quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                telegram_message += f" | <a href='{quote_link}'>🔗 Option Quote</a>"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending buy telegram: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_update_telegram(self, message: str) -> Dict[str, Any]:
        """Send UPDATE alert Telegram message with all stored alerts"""
        try:
            alerts = _load_alerts()
            alerter_alerts = alerts.get(self.alerter_name, {})
            
            telegram_message = f"🟡 {self.alerter_name.upper()}\n{message}\n\n"
            
            # Add all stored alerts with option quote links
            for ticker, alert_data in alerter_alerts.items():
                if alert_data.get("open") and alert_data.get("option_conid"):
                    details = alert_data["alert_details"]
                    emoji = "🔴" if details["side"] == "P" else "🟢"
                    
                    option_conid = alert_data["option_conid"]
                    quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                    
                    # Format expiry date for readability
                    formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{emoji} {ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\n"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending update telegram: {e}")
            return {"success": False, "error": str(e)}


class LiteProfAndKianHandler:
    """Lite handler for Prof & Kian notifications"""
    
    def __init__(self):
        self.alerter_name = "prof-and-kian-alerts"
        logger.info(f"Initialized {self.__class__.__name__}")
    
    async def process_notification_with_conid(self, notification_data: Dict[str, str]) -> Dict[str, Any]:
        """Process Prof & Kian notification - detect BUY vs UPDATE alerts"""
        try:
            title = notification_data.get('title', '')
            message = notification_data.get('message', '')
            subtext = notification_data.get('subtext', '')
            
            logger.info(f"Processing Prof & Kian notification: {title} - {message}")
            
            # Try to detect if this is a BUY alert
            buy_alert_info = await _detect_buy_alert(message)
            
            if buy_alert_info:
                # This is a BUY alert - process new position
                return await self._process_buy_alert(buy_alert_info, message, title)
            else:
                # This is an UPDATE alert - send update for all stored alerts
                return await self._process_update_alert(message, title)
            
        except Exception as e:
            logger.error(f"Error processing Prof & Kian notification: {e}")
            return {
                "alerter": self.alerter_name,
                "error": str(e),
                "processed_at": datetime.now().isoformat()
            }
    
    async def _process_buy_alert(self, buy_info: Dict[str, Any], message: str, title: str) -> Dict[str, Any]:
        """Process a BUY alert - get CONIDs, store alert, send Telegram"""
        try:
            ticker = buy_info["ticker"]
            strike = buy_info["strike"]
            side = buy_info["side"]
            stock_conid = buy_info["stock_conid"]
            
            # Extract expiry (default to today if not found)
            strike_match = re.search(rf'{strike}[CP]', message.upper())
            strike_pos = strike_match.end() if strike_match else len(message)
            expiry = _extract_expiry(message, strike_pos)
            
            # Get option contract CONID
            option_conid = None
            try:
                option_conid = await ibkr_service.get_option_conid(
                    ticker=ticker,
                    strike=strike,
                    side=side,
                    expiry=expiry
                )
            except Exception as e:
                logger.warning(f"Could not get option CONID: {e}")
            
            # Store the alert
            self._store_alert(ticker, strike, side, expiry, stock_conid, option_conid)
            
            # Send Telegram message
            telegram_result = await self._send_buy_telegram(
                ticker, strike, side, expiry, stock_conid, option_conid, message
            )
            
            return {
                "alerter": self.alerter_name,
                "alert_type": "BUY",
                "ticker": ticker,
                "strike": strike,
                "side": side,
                "expiry": expiry,
                "stock_conid": stock_conid,
                "option_conid": option_conid,
                "telegram_sent": telegram_result,
                "processed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing buy alert: {e}")
            return {"error": str(e)}
    
    async def _process_update_alert(self, message: str, title: str) -> Dict[str, Any]:
        """Process an UPDATE alert - send Telegram with all stored alerts"""
        try:
            # Send update Telegram with all stored alerts
            telegram_result = await self._send_update_telegram(message)
            
            return {
                "alerter": self.alerter_name,
                "alert_type": "UPDATE",
                "message": message,
                "telegram_sent": telegram_result,
                "processed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing update alert: {e}")
            return {"error": str(e)}
    
    def _store_alert(self, ticker: str, strike: float, side: str, expiry: str, 
                     stock_conid: int, option_conid: Optional[int]) -> None:
        """Store alert in alerts.json"""
        try:
            alerts = _load_alerts()
            
            if self.alerter_name not in alerts:
                alerts[self.alerter_name] = {}
            
            alerts[self.alerter_name][ticker] = {
                "open": True,
                "created_at": datetime.now().isoformat(),
                "option_conids": [option_conid] if option_conid else [],
                "option_conid": option_conid,
                "sentiment": "bullish" if side == "CALL" else "bearish",
                "conid": stock_conid,
                "alert_details": {
                    "ticker": ticker,
                    "strike": str(int(strike)) if strike.is_integer() else str(strike),
                    "side": "C" if side == "CALL" else "P",
                    "expiry": expiry,
                    "is_bullish": side == "CALL"
                }
            }
            
            _save_alerts(alerts)
            logger.info(f"Stored {ticker} {strike}{side[0]} alert for {self.alerter_name}")
            
        except Exception as e:
            logger.error(f"Error storing alert: {e}")
    
    async def _send_buy_telegram(self, ticker: str, strike: float, side: str, expiry: str,
                                stock_conid: int, option_conid: Optional[int], message: str) -> Dict[str, Any]:
        """Send BUY alert Telegram message"""
        try:
            # Format the message
            side_short = "C" if side == "CALL" else "P"
            emoji = "🔴 📉" if side == "PUT" else "🟢 📈"
            
            telegram_message = f"🚨 {self.alerter_name.upper()}\n{message}\n\n"
            formatted_expiry = _format_expiry_for_display(expiry)
            telegram_message += f"{emoji} {ticker} - {int(strike) if strike.is_integer() else strike}{side_short} - {formatted_expiry}"
            
            # Add links if CONIDs available
            if stock_conid:
                chain_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{stock_conid}/option/option.chain?source=onebar&u=false"
                telegram_message += f"  <a href='{chain_link}'>Option Chain</a>"
            
            if option_conid:
                quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                telegram_message += f" | <a href='{quote_link}'>🔗 Option Quote</a>"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending buy telegram: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_update_telegram(self, message: str) -> Dict[str, Any]:
        """Send UPDATE alert Telegram message with all stored alerts"""
        try:
            alerts = _load_alerts()
            alerter_alerts = alerts.get(self.alerter_name, {})
            
            telegram_message = f"🟡 {self.alerter_name.upper()}\n{message}\n\n"
            
            # Add all stored alerts with option quote links
            for ticker, alert_data in alerter_alerts.items():
                if alert_data.get("open") and alert_data.get("option_conid"):
                    details = alert_data["alert_details"]
                    emoji = "🔴" if details["side"] == "P" else "🟢"
                    
                    option_conid = alert_data["option_conid"]
                    quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                    
                    # Format expiry date for readability
                    formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{emoji} {ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\n"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending update telegram: {e}")
            return {"success": False, "error": str(e)}


class LiteRobinDaHoodHandler:
    """Lite handler for RobinDaHood notifications"""
    
    def __init__(self):
        self.alerter_name = "robindahood-alerts"
        logger.info(f"Initialized {self.__class__.__name__}")
    
    async def process_notification_with_conid(self, notification_data: Dict[str, str]) -> Dict[str, Any]:
        """Process RobinDaHood notification - detect BUY vs UPDATE alerts"""
        try:
            title = notification_data.get('title', '')
            message = notification_data.get('message', '')
            subtext = notification_data.get('subtext', '')
            
            logger.info(f"Processing RobinDaHood notification: {title} - {message}")
            
            # Try to detect if this is a BUY alert
            buy_alert_info = await _detect_buy_alert(message)
            
            if buy_alert_info:
                # This is a BUY alert - process new position
                return await self._process_buy_alert(buy_alert_info, message, title)
            else:
                # This is an UPDATE alert - send update for all stored alerts
                return await self._process_update_alert(message, title)
            
        except Exception as e:
            logger.error(f"Error processing RobinDaHood notification: {e}")
            return {
                "alerter": self.alerter_name,
                "error": str(e),
                "processed_at": datetime.now().isoformat()
            }
    
    async def _process_buy_alert(self, buy_info: Dict[str, Any], message: str, title: str) -> Dict[str, Any]:
        """Process a BUY alert - get CONIDs, store alert, send Telegram"""
        try:
            ticker = buy_info["ticker"]
            strike = buy_info["strike"]
            side = buy_info["side"]
            stock_conid = buy_info["stock_conid"]
            
            # Extract expiry (default to today if not found)
            strike_match = re.search(rf'{strike}[CP]', message.upper())
            strike_pos = strike_match.end() if strike_match else len(message)
            expiry = _extract_expiry(message, strike_pos)
            
            # Get option contract CONID
            option_conid = None
            try:
                option_conid = await ibkr_service.get_option_conid(
                    ticker=ticker,
                    strike=strike,
                    side=side,
                    expiry=expiry
                )
            except Exception as e:
                logger.warning(f"Could not get option CONID: {e}")
            
            # Store the alert
            self._store_alert(ticker, strike, side, expiry, stock_conid, option_conid)
            
            # Send Telegram message
            telegram_result = await self._send_buy_telegram(
                ticker, strike, side, expiry, stock_conid, option_conid, message
            )
            
            return {
                "alerter": self.alerter_name,
                "alert_type": "BUY",
                "ticker": ticker,
                "strike": strike,
                "side": side,
                "expiry": expiry,
                "stock_conid": stock_conid,
                "option_conid": option_conid,
                "telegram_sent": telegram_result,
                "processed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing buy alert: {e}")
            return {"error": str(e)}
    
    async def _process_update_alert(self, message: str, title: str) -> Dict[str, Any]:
        """Process an UPDATE alert - send Telegram with all stored alerts"""
        try:
            # Send update Telegram with all stored alerts
            telegram_result = await self._send_update_telegram(message)
            
            return {
                "alerter": self.alerter_name,
                "alert_type": "UPDATE",
                "message": message,
                "telegram_sent": telegram_result,
                "processed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing update alert: {e}")
            return {"error": str(e)}
    
    def _store_alert(self, ticker: str, strike: float, side: str, expiry: str, 
                     stock_conid: int, option_conid: Optional[int]) -> None:
        """Store alert in alerts.json"""
        try:
            alerts = _load_alerts()
            
            if self.alerter_name not in alerts:
                alerts[self.alerter_name] = {}
            
            alerts[self.alerter_name][ticker] = {
                "open": True,
                "created_at": datetime.now().isoformat(),
                "option_conids": [option_conid] if option_conid else [],
                "option_conid": option_conid,
                "sentiment": "bullish" if side == "CALL" else "bearish",
                "conid": stock_conid,
                "alert_details": {
                    "ticker": ticker,
                    "strike": str(int(strike)) if strike.is_integer() else str(strike),
                    "side": "C" if side == "CALL" else "P",
                    "expiry": expiry,
                    "is_bullish": side == "CALL"
                }
            }
            
            _save_alerts(alerts)
            logger.info(f"Stored {ticker} {strike}{side[0]} alert for {self.alerter_name}")
            
        except Exception as e:
            logger.error(f"Error storing alert: {e}")
    
    async def _send_buy_telegram(self, ticker: str, strike: float, side: str, expiry: str,
                                stock_conid: int, option_conid: Optional[int], message: str) -> Dict[str, Any]:
        """Send BUY alert Telegram message"""
        try:
            # Format the message
            side_short = "C" if side == "CALL" else "P"
            emoji = "🔴 📉" if side == "PUT" else "🟢 📈"
            
            telegram_message = f"🚨 {self.alerter_name.upper()}\n{message}\n\n"
            formatted_expiry = _format_expiry_for_display(expiry)
            telegram_message += f"{emoji} {ticker} - {int(strike) if strike.is_integer() else strike}{side_short} - {formatted_expiry}"
            
            # Add links if CONIDs available
            if stock_conid:
                chain_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{stock_conid}/option/option.chain?source=onebar&u=false"
                telegram_message += f"  <a href='{chain_link}'>Option Chain</a>"
            
            if option_conid:
                quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                telegram_message += f" | <a href='{quote_link}'>🔗 Option Quote</a>"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending buy telegram: {e}")
            return {"success": False, "error": str(e)}
    
    async def _send_update_telegram(self, message: str) -> Dict[str, Any]:
        """Send UPDATE alert Telegram message with all stored alerts"""
        try:
            alerts = _load_alerts()
            alerter_alerts = alerts.get(self.alerter_name, {})
            
            telegram_message = f"🟡 {self.alerter_name.upper()}\n{message}\n\n"
            
            # Add all stored alerts with option quote links
            for ticker, alert_data in alerter_alerts.items():
                if alert_data.get("open") and alert_data.get("option_conid"):
                    details = alert_data["alert_details"]
                    emoji = "🔴" if details["side"] == "P" else "🟢"
                    
                    option_conid = alert_data["option_conid"]
                    quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                    
                    # Format expiry date for readability
                    formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{emoji} {ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\n"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending update telegram: {e}")
            return {"success": False, "error": str(e)}