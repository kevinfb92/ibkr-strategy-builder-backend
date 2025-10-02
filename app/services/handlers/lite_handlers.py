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

def _normalize_strike_for_regex(strike: float) -> str:
    """Convert float strike to appropriate string format for regex matching"""
    return str(int(strike)) if strike == int(strike) else str(strike)

def _load_alerts() -> Dict:
    """Load alerts from JSON file and perform periodic cleanup"""
    try:
        # Perform cleanup of stale alerts every time we load (throttled to avoid excessive cleanup)
        # Only cleanup if it's been a while since last cleanup to avoid performance impact
        import random
        if random.random() < 0.1:  # 10% chance to run cleanup on each load (roughly every 10 loads)
            _cleanup_stale_alerts()
        
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

def _clear_all_alerts() -> Dict[str, Any]:
    """
    Clear ALL stored alerts completely
    
    WARNING: This removes all alerts regardless of their status.
    Use with caution - intended for testing and maintenance only.
    
    Returns:
        Dict with summary of cleared alerts
    """
    try:
        # Load current alerts to get count before clearing
        current_alerts = _load_alerts()
        
        # Count alerts by alerter before clearing
        counts = {}
        total_alerts = 0
        
        for alerter_name, alerter_data in current_alerts.items():
            alert_count = len(alerter_data)
            counts[alerter_name] = alert_count
            total_alerts += alert_count
        
        # Clear all alerts by saving empty dict
        empty_alerts = {}
        _save_alerts(empty_alerts)
        
        logger.warning(f"CLEARED ALL ALERTS: {total_alerts} total alerts removed across {len(counts)} alerters")
        
        return {
            "status": "success",
            "total_alerts_cleared": total_alerts,
            "alerters_cleared": len(counts),
            "breakdown_by_alerter": counts,
            "message": f"Successfully cleared {total_alerts} alerts from {len(counts)} alerters"
        }
        
    except Exception as e:
        logger.error(f"Error clearing all alerts: {e}")
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to clear alerts"
        }

def _cleanup_stale_alerts(hours_old: int = 24) -> None:
    """
    Clean up alerts that haven't been marked as open after a configurable timespan
    This prevents storage bloat from alerts that were created but never acted upon
    
    IMPORTANT: Only removes alerts with open=false or missing open field
    Never removes alerts with open=true (those are only removed by order updates)
    
    Args:
        hours_old: Remove non-open alerts older than this many hours (default: 24)
    """
    try:
        alerts = _load_alerts()
        if not alerts:
            return
        
        from datetime import datetime, timedelta
        cutoff_time = datetime.now() - timedelta(hours=hours_old)
        removed_count = 0
        
        for alerter_name in list(alerts.keys()):
            if alerter_name not in alerts:
                continue
                
            for ticker in list(alerts[alerter_name].keys()):
                alert_data = alerts[alerter_name][ticker]
                
                # Only clean up alerts that are NOT marked as open
                # - open=false (explicitly not open)  
                # - missing open field (never marked as open)
                # NEVER remove open=true alerts (those are live positions)
                is_open = alert_data.get("open", False)
                if not is_open:  # Only remove if open=false or missing
                    created_at_str = alert_data.get("created_at")
                    if created_at_str:
                        try:
                            # Parse ISO format timestamp
                            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                            if created_at < cutoff_time:
                                # Remove the stale non-open alert
                                del alerts[alerter_name][ticker]
                                removed_count += 1
                                logger.info(f"Removed stale non-open alert: {alerter_name}/{ticker} (created {created_at_str}, open={is_open})")
                                
                                # Clean up empty alerter sections
                                if not alerts[alerter_name]:
                                    del alerts[alerter_name]
                                    
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Could not parse created_at for {alerter_name}/{ticker}: {e}")
                            continue
        
        if removed_count > 0:
            _save_alerts(alerts)
            logger.info(f"Cleaned up {removed_count} stale non-open alerts older than {hours_old} hours")
        else:
            logger.debug(f"No stale non-open alerts found (older than {hours_old} hours)")
            
    except Exception as e:
        logger.error(f"Error during stale alert cleanup: {e}")

async def _detect_buy_alert(message: str) -> Optional[Dict[str, Any]]:
    """
    Detect if message is a buy alert by finding strike+side and stock IMMEDIATELY before it
    Returns: {ticker, strike, side, stock_conid} or None
    """
    # Find all strike+side patterns (e.g., "175P", "600C", "123.5C")
    strike_patterns = re.finditer(r'(\d+(?:\.\d+)?)([CP])', message.upper())
    
    for match in strike_patterns:
        strike = float(match.group(1))
        side = match.group(2)
        
        # Look for stock symbol IMMEDIATELY before the strike (within the same word or separated by whitespace)
        before_strike = message[:match.start()].strip()
        
        # Find the last word before the strike - must be all caps and at least 2 characters
        # Look for pattern: [WORD][WHITESPACE][STRIKE] or [WORD][STRIKE] (no space)
        immediate_before_match = re.search(r'\b([A-Z]{2,5})\s*$', before_strike)
        
        if immediate_before_match:
            potential_ticker = immediate_before_match.group(1)
            
            # Additional validation: ensure ticker is at least 2 characters
            if len(potential_ticker) < 2:
                continue
            
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

def _extract_expiry(message: str, strike_position: int, ticker: str = None) -> str:
    """Extract expiry from message (must come after strike position) - STRICT date format only"""
    # Look for expiry patterns after the strike position
    message_after_strike = message[strike_position:]
    
    # Remove URLs to avoid false matches from Discord IDs, etc.
    cleaned_message = re.sub(r'https?://[^\s]+', '', message_after_strike)
    
    # STRICT: Only accept MM/DD or M/D format with forward slash
    # NO other formats like 0314, OCT25, etc. - these are NOT dates
    expiry_pattern = r'\b(\d{1,2})/(\d{1,2})\b'
    
    match = re.search(expiry_pattern, cleaned_message)
    if match:
        try:
            month, day = int(match.group(1)), int(match.group(2))
            # Validate it's a reasonable date (month 1-12, day 1-31)
            if 1 <= month <= 12 and 1 <= day <= 31:
                from datetime import datetime
                current_year = datetime.now().year
                current_month = datetime.now().month
                current_day = datetime.now().day
                
                # Check if this might be a historical date (in a recap/summary)
                message_upper = message.upper()
                is_historical = 'RECAP' in message_upper
                
                if is_historical:
                    # For historical messages, default to current year
                    return f"{month:02d}/{day:02d}/{current_year}"
                else:
                    # For regular trading alerts, if date has passed, assume next year
                    if (month, day) < (current_month, current_day):
                        return f"{month:02d}/{day:02d}/{current_year + 1}"
                    else:
                        return f"{month:02d}/{day:02d}/{current_year}"
        except (ValueError, IndexError):
            pass
    
    # NO MATCH FOUND - Use defaults
    from datetime import datetime
    
    if ticker and ticker.upper() in ['SPY', 'SPX']:
        # SPY/SPX: Default to 0DTE (same day expiry)
        current_date = datetime.now().strftime("%m/%d/%Y")
        logger.debug(f"No expiry found for {ticker}, defaulting to 0DTE: {current_date}")
        return current_date
    else:
        # Other tickers: Default to closest Friday (standard options expiry)
        current_date = datetime.now()
        days_ahead = 4 - current_date.weekday()  # Friday is weekday 4
        if days_ahead <= 0:  # If today is Friday or weekend, next Friday
            days_ahead += 7
        
        from datetime import timedelta
        next_friday = current_date + timedelta(days=days_ahead)
        default_expiry = next_friday.strftime("%m/%d/%Y")
        
        logger.debug(f"No expiry found for {ticker or 'unknown'}, defaulting to next Friday: {default_expiry}")
        return default_expiry

def _compact_discord_links(message: str) -> str:
    """
    Replace long Discord links with compact versions
    Converts: https://discord.com/channels/123/456/789
    To: <a href='https://discord.com/channels/123/456/789'>🔗 Discord</a>
    """
    # Pattern to match Discord links
    discord_pattern = r'https://discord\.com/channels/\d+/\d+/\d+'
    
    def replace_link(match):
        url = match.group(0)
        return f"<a href='{url}'>🔗 Discord</a>"
    
    # Replace Discord links with compact versions
    compacted = re.sub(discord_pattern, replace_link, message)
    
    # Also handle "See it here:" prefix that often appears before Discord links
    compacted = re.sub(r'See it here:\s*<a href=', '<a href=', compacted)
    
    return compacted

def _is_recap_message(message: str) -> bool:
    """Check if message contains recap keyword - used by all alerters"""
    return 'RECAP' in message.upper()

def _count_strikes_in_message(message: str) -> int:
    """Count the number of option strikes in the message - used by all alerters"""
    # Find all strike+side patterns (e.g., "175P", "600C", "123.5C")
    strike_patterns = re.findall(r'\d+(?:\.\d+)?[CP]', message.upper())
    return len(strike_patterns)

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
        - Long indicates calls, Short indicates puts (can appear anywhere in message)
        - Stock symbols are in $NAME format and must come IMMEDIATELY after Long/Short
        - Get closest ITM option with nearest expiry
        """
        try:
            message_upper = message.upper()
            
            # Look for "Long $TICKER" or "Short $TICKER" patterns anywhere in the message
            # The stock ticker must come IMMEDIATELY after Long/Short and be at least 2 characters
            long_pattern = r'\bLONG\s+\$([A-Z]{2,5})\b'
            short_pattern = r'\bSHORT\s+\$([A-Z]{2,5})\b'
            
            side = None
            ticker = None
            
            # Check for Long pattern first
            long_match = re.search(long_pattern, message_upper)
            if long_match:
                side = "CALL"
                ticker = long_match.group(1)
            else:
                # Check for Short pattern
                short_match = re.search(short_pattern, message_upper)
                if short_match:
                    side = "PUT"
                    ticker = short_match.group(1)
            
            # If no valid Long/Short + $TICKER pattern found, return None
            if not side or not ticker or len(ticker) < 2:
                return None
            
            # Verify it's a real stock by getting CONID
            try:
                stock_conid = await ibkr_service.get_stock_conid(ticker)
                if not stock_conid:
                    return None
            except Exception as e:
                logger.debug(f"Could not verify {ticker} as stock: {e}")
                return None
            
            # Get current stock price and find closest ITM strike efficiently
            try:
                # stock_conid already available from above
                
                current_price = ibkr_service.get_current_stock_price(ticker)
                if not current_price:
                    logger.error(f"Could not get current price for {ticker}")
                    return None
                
                logger.debug(f"Current price for {ticker}: ${current_price}")
                
                # Use nearest Friday expiry (simplified - assume weekly options)
                today = datetime.now()
                days_to_friday = (4 - today.weekday()) % 7  # Friday is weekday 4
                if days_to_friday == 0:  # If today is Friday, use next Friday
                    days_to_friday = 7
                
                expiry_date = today + timedelta(days=days_to_friday)
                expiry_mmdd = expiry_date.strftime("%m%d")  # Format as MMDD for display
                expiry_yyyymmdd = expiry_date.strftime("%Y%m%d")  # Format as YYYYMMDD for IBKR API
                
                # Get closest ITM strike from actual available strikes
                # Pass stock_conid to avoid redundant lookups
                strike = await self._get_closest_itm_strike_efficient(
                    ticker=ticker,
                    stock_conid=stock_conid,
                    current_price=current_price,
                    side=side,
                    expiry_yyyymmdd=expiry_yyyymmdd
                )
                
                if not strike:
                    logger.error(f"Could not find available ITM {side} strike for {ticker}")
                    return None
                
                logger.debug(f"Found closest ITM {side} strike for {ticker}: ${strike} (current: ${current_price})")
                
                return {
                    "ticker": ticker,
                    "strike": float(strike),
                    "side": side,
                    "stock_conid": stock_conid,
                    "expiry": expiry_mmdd
                }
                
            except Exception as e:
                logger.error(f"Error calculating option details for {ticker}: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error detecting RDT buy alert: {e}")
            return None
    
    async def _get_closest_itm_strike_efficient(self, ticker: str, stock_conid: int, current_price: float, side: str, expiry_yyyymmdd: str) -> Optional[float]:
        """
        Efficiently get closest ITM strike by reusing stock_conid to avoid redundant API calls
        """
        try:
            logger.debug(f"Finding closest ITM {side} strike for {ticker} @ ${current_price}, expiry {expiry_yyyymmdd}")
            
            # Use the existing stock_conid instead of looking it up again
            # Convert YYYYMMDD to MMMYY format for IBKR API
            from datetime import datetime
            expiry_date = datetime.strptime(expiry_yyyymmdd, "%Y%m%d")
            month_abbr = expiry_date.strftime("%b").upper()  # OCT
            year_abbr = expiry_date.strftime("%y")  # 25
            month_year = f"{month_abbr}{year_abbr}"  # OCT25
            
            logger.debug(f"Converted expiry {expiry_yyyymmdd} to month format {month_year}")
            
            # Get available strikes using the existing stock_conid
            strikes_result = ibkr_service.client.search_strikes_by_conid(
                conid=str(stock_conid),
                sec_type="OPT",
                month=month_year
            )
            
            if not strikes_result or not hasattr(strikes_result, 'data') or not strikes_result.data:
                logger.warning(f"No strikes data found for {ticker}")
                return None
            
            # Extract and process strikes
            strikes = []
            strikes_data = strikes_result.data
            
            if isinstance(strikes_data, dict):
                # Handle the case where data is a dict with 'call' and 'put' keys
                if 'call' in strikes_data:
                    strikes.extend(strikes_data['call'])
                if 'put' in strikes_data:
                    strikes.extend(strikes_data['put'])
            
            strikes = sorted(list(set(strikes)))  # Remove duplicates and sort
            logger.debug(f"Available strikes: {strikes[:10]}...{strikes[-10:]} (showing first/last 10)")
            
            if side == "CALL":
                # For calls, ITM = strike below current price
                itm_strikes = [s for s in strikes if s < current_price]
                if itm_strikes:
                    closest_strike = max(itm_strikes)
                    logger.debug(f"Closest ITM call strike: ${closest_strike}")
                    return closest_strike
                else:
                    logger.warning(f"No ITM call strikes found below ${current_price}")
                    return None
            else:  # PUT
                # For puts, ITM = strike above current price
                itm_strikes = [s for s in strikes if s > current_price]
                if itm_strikes:
                    closest_strike = min(itm_strikes)
                    logger.debug(f"Closest ITM put strike: ${closest_strike}")
                    return closest_strike
                else:
                    logger.warning(f"No ITM put strikes found above ${current_price}")
                    return None
                    
        except Exception as e:
            logger.error(f"Could not find closest ITM strike for {ticker}: {e}")
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
                strike_match = re.search(rf'{_normalize_strike_for_regex(strike)}[CP]', message.upper())
                strike_pos = strike_match.end() if strike_match else len(message)
                expiry = _extract_expiry(message, strike_pos, ticker)
            
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
                "open": False,  # Always start as closed - only order tracking sets this to True
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
            
            telegram_message = f"🚨 {self.alerter_name.upper()}\n{_compact_discord_links(message)}\n\n"
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
            
            telegram_message = f"🟡 {self.alerter_name.upper()}\n{_compact_discord_links(message)}\n\n"
            
            # Add all stored alerts with option quote links
            for ticker, alert_data in alerter_alerts.items():
                if alert_data.get("option_conid"):  # Show any alert with valid option_conid
                    details = alert_data["alert_details"]
                    
                    option_conid = alert_data["option_conid"]
                    quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                    
                    # Format expiry date for readability
                    formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\n"
            
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
                # Check if this is a RECAP message with many strikes (should be treated as UPDATE)
                is_recap = _is_recap_message(message)
                strike_count = _count_strikes_in_message(message)
                
                if is_recap and strike_count > 3:
                    logger.info(f"Detected RECAP message with {strike_count} strikes - treating as UPDATE alert instead of BUY")
                    return await self._process_update_alert(message, title)
                
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
                    # Valid formats: MMDD (like 1002, 1003, 1025), MM/DD, MM-DD
                    expiry_patterns = [
                        r'(\d{2}/\d{2})',           # MM/DD format (10/03)
                        r'(\d{2}-\d{2})',           # MM-DD format (10-03)
                        r'(\d{4})',                 # MMDD format (1002, 0930, 1225, etc.)
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
                            
                            # Validate MMDD format (if 4 digits, ensure it's a valid date)
                            if len(expiry) == 4 and expiry.isdigit():
                                month = int(expiry[:2])
                                day = int(expiry[2:])
                                # Only accept valid months (01-12) and days (01-31)
                                if 1 <= month <= 12 and 1 <= day <= 31:
                                    break
                                else:
                                    expiry = None  # Invalid date, continue searching
                            else:
                                break  # Non-MMDD format, assume it's valid
                    
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
                "open": False,  # Always start as closed - only order tracking sets this to True
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
            
            telegram_message = f"🚨 {self.alerter_name.upper()}\n{_compact_discord_links(message)}\n\n"
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
            
            telegram_message = f"🟡 {self.alerter_name.upper()}\n{_compact_discord_links(message)}\n\n"
            
            # Add all stored alerts with option quote links
            for ticker, alert_data in alerter_alerts.items():
                if alert_data.get("option_conid"):  # Show any alert with valid option_conid
                    details = alert_data["alert_details"]
                    
                    option_conid = alert_data["option_conid"]
                    quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                    
                    # Format expiry date for readability
                    formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\n"
            
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
            
            # Try to detect if this is a BUY alert using Prof & Kian specific logic
            buy_alert_info = await self._detect_prof_kian_buy_alert(message)
            
            if buy_alert_info:
                # Check if this is a RECAP message with many strikes (should be treated as UPDATE)
                is_recap = _is_recap_message(message)
                strike_count = _count_strikes_in_message(message)
                
                if is_recap and strike_count > 3:
                    logger.info(f"Detected RECAP message with {strike_count} strikes - treating as UPDATE alert instead of BUY")
                    return await self._process_update_alert(message, title)
                
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
            
            # Extract expiry based on format
            if buy_info.get("format") == "detailed":
                # Use detailed format expiry extraction
                expiry = self._extract_detailed_expiry(message, ticker)
            else:
                # Use compact format expiry extraction (original logic)
                strike_match = re.search(rf'{_normalize_strike_for_regex(strike)}[CP]', message.upper())
                strike_pos = strike_match.end() if strike_match else len(message)
                expiry = _extract_expiry(message, strike_pos, ticker)
            
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
                "open": False,  # Always start as closed - only order tracking sets this to True
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
            
            telegram_message = f"🚨 {self.alerter_name.upper()}\n{_compact_discord_links(message)}\n\n"
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
            
            telegram_message = f"🟡 {self.alerter_name.upper()}\n{_compact_discord_links(message)}\n\n"
            
            # Add all stored alerts with option quote links
            for ticker, alert_data in alerter_alerts.items():
                if alert_data.get("option_conid"):  # Show any alert with valid option_conid
                    details = alert_data["alert_details"]
                    
                    option_conid = alert_data["option_conid"]
                    quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                    
                    # Format expiry date for readability
                    formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\n"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending update telegram: {e}")
            return {"success": False, "error": str(e)}
    
    async def _detect_prof_kian_buy_alert(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect Prof & Kian buy alerts in both formats:
        1. Detailed format: TICKER: UEC\nSTRIKE: 25C\nEXP: 05/15/2025
        2. Compact format: TSLA 600C 10/3
        """
        # First, try to detect detailed format
        detailed_alert = await self._detect_detailed_format(message)
        if detailed_alert:
            return detailed_alert
        
        # Fallback to compact format detection
        return await _detect_buy_alert(message)
    
    async def _detect_detailed_format(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Detect detailed format alerts:
        TICKER: UEC
        STRIKE: 25C
        PRICE: 1.35
        EXP: 05/15/2025
        """
        # Look for TICKER: pattern - must be at least 2 characters
        ticker_match = re.search(r'TICKER:\s*([A-Z]{2,5})', message.upper())
        if not ticker_match:
            return None
        
        ticker = ticker_match.group(1)
        
        # Additional validation: ensure ticker is at least 2 characters
        if len(ticker) < 2:
            return None
        
        # Look for STRIKE: pattern with side (C/P)
        strike_match = re.search(r'STRIKE:\s*(\d+(?:\.\d+)?)([CP])', message.upper())
        if not strike_match:
            return None
        
        strike = float(strike_match.group(1))
        side = "CALL" if strike_match.group(2) == "C" else "PUT"
        
        # Verify it's a real stock by getting CONID
        try:
            stock_conid = await ibkr_service.get_stock_conid(ticker)
            if not stock_conid:
                return None
        except Exception as e:
            logger.debug(f"Could not verify {ticker} as stock: {e}")
            return None
        
        return {
            "ticker": ticker,
            "strike": strike,
            "side": side,
            "stock_conid": stock_conid,
            "format": "detailed"
        }
    
    def _extract_detailed_expiry(self, message: str, ticker: str = None) -> str:
        """
        Extract expiry from detailed format message.
        Supports:
        - EXP: 05/15/2025 (full date with year)
        - EXP: 10/3 (month/day, current year assumed)
        - EXP: 1/2027exp (monthly options like January 2027)
        """
        from datetime import datetime, timedelta
        
        # Look for EXP: pattern
        exp_match = re.search(r'EXP:\s*([^\s\n]+)', message.upper())
        if not exp_match:
            # No EXP found, use default logic
            return self._get_default_expiry(ticker)
        
        exp_text = exp_match.group(1)
        
        # Handle different expiry formats
        
        # Full date: 05/15/2025
        full_date_match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', exp_text)
        if full_date_match:
            month, day, year = full_date_match.groups()
            return f"{int(month):02d}/{int(day):02d}/{year}"
        
        # Month/day without year: 10/3
        md_match = re.match(r'(\d{1,2})/(\d{1,2})$', exp_text)
        if md_match:
            month, day = int(md_match.group(1)), int(md_match.group(2))
            if 1 <= month <= 12 and 1 <= day <= 31:
                current_year = datetime.now().year
                current_month = datetime.now().month
                current_day = datetime.now().day
                
                # If date has passed this year, assume next year
                if (month, day) < (current_month, current_day):
                    return f"{month:02d}/{day:02d}/{current_year + 1}"
                else:
                    return f"{month:02d}/{day:02d}/{current_year}"
        
        # Monthly options: 1/2027exp
        monthly_match = re.match(r'(\d{1,2})/(\d{4})EXP?', exp_text)
        if monthly_match:
            month, year = int(monthly_match.group(1)), int(monthly_match.group(2))
            if 1 <= month <= 12:
                # For monthly options, use the third Friday of the month
                from calendar import monthrange
                
                # Get first day of the month
                first_day = datetime(year, month, 1)
                
                # Find first Friday (weekday 4)
                days_to_friday = (4 - first_day.weekday()) % 7
                first_friday = first_day + timedelta(days=days_to_friday)
                
                # Third Friday is 14 days later
                third_friday = first_friday + timedelta(days=14)
                
                return third_friday.strftime("%m/%d/%Y")
        
        # If nothing matches, use default
        return self._get_default_expiry(ticker)
    
    def _get_default_expiry(self, ticker: str = None) -> str:
        """Get default expiry based on ticker"""
        from datetime import datetime, timedelta
        
        if ticker and ticker.upper() in ['SPY', 'SPX']:
            # SPY/SPX: Default to 0DTE (same day expiry)
            current_date = datetime.now().strftime("%m/%d/%Y")
            logger.debug(f"No expiry found for {ticker}, defaulting to 0DTE: {current_date}")
            return current_date
        else:
            # Other tickers: Default to closest Friday (standard options expiry)
            current_date = datetime.now()
            days_ahead = 4 - current_date.weekday()  # Friday is weekday 4
            if days_ahead <= 0:  # If today is Friday or weekend, next Friday
                days_ahead += 7
            
            next_friday = current_date + timedelta(days=days_ahead)
            default_expiry = next_friday.strftime("%m/%d/%Y")
            
            logger.debug(f"No expiry found for {ticker or 'unknown'}, defaulting to next Friday: {default_expiry}")
            return default_expiry


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
                # Check if this is a RECAP message with many strikes (should be treated as UPDATE)
                is_recap = _is_recap_message(message)
                strike_count = _count_strikes_in_message(message)
                
                if is_recap and strike_count > 3:
                    logger.info(f"Detected RECAP message with {strike_count} strikes - treating as UPDATE alert instead of BUY")
                    return await self._process_update_alert(message, title)
                
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
            strike_match = re.search(rf'{_normalize_strike_for_regex(strike)}[CP]', message.upper())
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
                "open": False,  # Always start as closed - only order tracking sets this to True
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
            
            telegram_message = f"🚨 {self.alerter_name.upper()}\n{_compact_discord_links(message)}\n\n"
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
            
            telegram_message = f"🟡 {self.alerter_name.upper()}\n{_compact_discord_links(message)}\n\n"
            
            # Add all stored alerts with option quote links
            for ticker, alert_data in alerter_alerts.items():
                if alert_data.get("option_conid"):  # Show any alert with valid option_conid
                    details = alert_data["alert_details"]
                    
                    option_conid = alert_data["option_conid"]
                    quote_link = f"https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/{option_conid}?source=onebar&u=false"
                    
                    # Format expiry date for readability
                    formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\n"
            
            # Send via telegram service
            result = await telegram_service.send_lite_alert(telegram_message)
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending update telegram: {e}")
            return {"success": False, "error": str(e)}
