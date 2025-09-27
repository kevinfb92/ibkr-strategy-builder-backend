"""
Telegram bot service for sending trading alerts with Buy/Sell buttons
"""
import asyncio
import logging
import uuid
import re
from typing import Optional, Dict, Any
from datetime import datetime

# telegram objects used by this module
try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
except Exception:
    # In test/static analysis environments telegram may not be installed.
    InlineKeyboardButton = InlineKeyboardMarkup = object

logger = logging.getLogger(__name__)

# Quiet noisy third-party loggers that flood the console (getUpdates/httpx/urllib3)
try:
    logging.getLogger('httpx').setLevel(logging.WARNING)
except Exception:
    pass
try:
    logging.getLogger('urllib3').setLevel(logging.WARNING)
except Exception:
    pass
try:
    logging.getLogger('websocket').setLevel(logging.WARNING)
except Exception:
    pass


class TelegramService:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.bot = None
        self.application = None
        self.pending_messages: Dict[str, Dict[str, Any]] = {}
        self.chat_id: Optional[str] = None

    async def get_chat_id(self, username: str = "Kevchan") -> Optional[str]:
        """Get chat ID for a specific username (if possible)"""
        # Note: Telegram bots cannot directly get chat IDs by username
        # The chat ID will be determined when the user first interacts with the bot
        # For now, we'll need to get it through the /start command or first message
        
        if self.chat_id:
            return self.chat_id
        
        logger.warning(f"Chat ID not set. User '{username}' needs to send /start to the bot first.")
        return None
    
    def _format_contract_display(self, ticker: str, additional_info: str = "", alerter_name: str = "", processed_data: dict = None) -> tuple[str, str]:
        """
        Format contract display with a unified contract-name formatter used across all alerters.

        The canonical display is: "SYMBOL - 6000C - M/D" when possible. Any trailing
        market-data suffix like "@ 38.5x39.0" is removed from the contract line so
        market prices are shown only in the IBKR Market Data block.
        """
        formatted_ticker = ticker or ""
        enhanced_info = additional_info or ""

        def _format_contract_name(proc: dict, raw_ticker: str) -> str:
            # Prefer explicit IBKR contract details when present
            cd = None
            if proc:
                cd = proc.get('contract_details') or proc.get('contract_to_use') or proc.get('stored_contract')

            symbol = None
            strike = None
            right = None
            expiry = None

            if isinstance(cd, dict):
                symbol = cd.get('symbol')
                strike = cd.get('strike')
                right = (cd.get('right') or cd.get('side') or '')
                expiry = cd.get('expiry')
            else:
                # Parse raw_ticker after stripping any market-data suffix
                if raw_ticker:
                    rt = str(raw_ticker)
                    if '@' in rt:
                        rt = rt.split('@', 1)[0].strip()
                    rt = rt.strip(' ,;')
                    parts = rt.split()
                    if len(parts) >= 2:
                        symbol = parts[0]
                        for p in parts[1:4]:
                            if p and any(ch.isdigit() for ch in p):
                                m = p.replace('$', '')
                                if m and m[-1].upper() in ('C', 'P'):
                                    right = m[-1].upper()
                                    try:
                                        strike = float(m[:-1])
                                    except Exception:
                                        strike = m[:-1]
                                    break
                                else:
                                    try:
                                        strike = float(m)
                                        break
                                    except Exception:
                                        pass
                    for p in parts:
                        if p.isdigit() and len(p) == 8:
                            expiry = p
                            break

            if symbol and strike is not None:
                try:
                    strike_disp = str(int(float(strike))) if float(strike).is_integer() else str(strike)
                except Exception:
                    strike_disp = str(strike)

                right_disp = (right[0].upper() if right else '')
                date_disp = ''
                if expiry and isinstance(expiry, str) and len(expiry) == 8:
                    try:
                        month = int(expiry[4:6])
                        day = int(expiry[6:8])
                        date_disp = f"{month}/{day}"
                    except Exception:
                        date_disp = expiry

                parts = [str(symbol).upper(), f"{strike_disp}{right_disp}"]
                if date_disp:
                    parts.append(date_disp)
                return ' - '.join(parts)

            # Fallback: sanitized raw ticker without market-data
            if raw_ticker:
                rt = str(raw_ticker)
                if '@' in rt:
                    rt = rt.split('@', 1)[0].strip()
                return rt.strip()
            return ''

        # Prefer unified name
        unified_name = ''
        try:
            unified_name = _format_contract_name(processed_data, ticker)
        except Exception:
            unified_name = ''

        if unified_name:
            formatted_ticker = unified_name

        # Special-case alerters for their enhanced info blocks
        if self._is_demspxslayer(alerter_name, processed_data) and processed_data:
            enhanced_info = self._format_demslayer_position_info(processed_data) or ''
        elif alerter_name == 'Real Day Trading' and processed_data:
            enhanced_info = self._format_real_day_trading_details(processed_data, additional_info) or additional_info

        # Strip any remaining market-data suffix in the final displayed ticker
        try:
            if isinstance(formatted_ticker, str) and '@' in formatted_ticker:
                formatted_ticker = formatted_ticker.split('@', 1)[0].strip()
        except Exception:
            pass

        return formatted_ticker, enhanced_info
    
    def _format_demslayer_position_info(self, processed_data: dict) -> str:
        """
        Format demslayer-specific position or contract value information
        
        Args:
            processed_data: Processed data from demslayer handler
            
        Returns:
            Formatted position/value info string
        """
        try:
            info_parts = []
            
            # Check if we have an SPX position
            if processed_data.get('has_spx_position') and processed_data.get('spx_position'):
                spx_position = processed_data.get('spx_position')
                
                # Extract position information
                symbol = spx_position.get('symbol', 'SPX')
                position_size = spx_position.get('position', 0)
                unrealized_pnl = spx_position.get('unrealizedPnl', 0)
                realized_pnl = spx_position.get('realizedPnl', 0)
                current_price = spx_position.get('currentPrice', 'N/A')
                avg_price = spx_position.get('avgPrice', 'N/A')
                market_value = spx_position.get('marketValue', 'N/A')
                daily_pnl = spx_position.get('dailyPnl', 'N/A')
                
                # Format position header
                position_type = "Long" if position_size > 0 else "Short"
                info_parts.append(f"📊 {position_type} Position: {abs(position_size)} contracts")

                # Add symbol/type info (simplified)
                if " P " in symbol:
                    info_parts.append(f"🔴 Type: PUT")
                elif " C " in symbol:
                    info_parts.append(f"🟢 Type: CALL")

                # Current price and average
                if current_price != 'N/A':
                    price_line = f"💰 Current: ${current_price}"
                    if avg_price != 'N/A' and avg_price != current_price:
                        price_line += f" | Avg: ${avg_price}"
                    info_parts.append(price_line)

                # Market value
                if market_value != 'N/A' and market_value != 0:
                    info_parts.append(f"📈 Market Value: ${abs(market_value):,.2f}")

                # Unrealized P/L with color coding
                if unrealized_pnl > 0:
                    info_parts.append(f"🟢 Unrealized P/L: +${abs(unrealized_pnl):,.2f}")
                elif unrealized_pnl < 0:
                    info_parts.append(f"🔴 Unrealized P/L: -${abs(unrealized_pnl):,.2f}")
                else:
                    info_parts.append(f"⚪ Unrealized P/L: $0.00")

                # Daily P/L (if different)
                if daily_pnl != 'N/A' and daily_pnl != unrealized_pnl:
                    if daily_pnl > 0:
                        info_parts.append(f"Daily P/L: +${abs(daily_pnl):,.2f}")
                    elif daily_pnl < 0:
                        info_parts.append(f"Daily P/L: -${abs(daily_pnl):,.2f}")

                # Realized P/L (if any)
                if realized_pnl != 0:
                    if realized_pnl > 0:
                        info_parts.append(f"Realized P/L: +${abs(realized_pnl):,.2f}")
                    else:
                        info_parts.append(f"Realized P/L: -${abs(realized_pnl):,.2f}")
                
                    # Add current market data even when we have a position
                    spread_info = processed_data.get('spread_info')
                    if spread_info and spread_info.get('bid') != 'N/A':
                        bid = spread_info.get('bid', 'N/A')
                        ask = spread_info.get('ask', 'N/A')
                        last = spread_info.get('last', 'N/A')
                        open_interest = spread_info.get('open_interest')

                        # Mirror Real Day Trading layout for IBKR lookup and market data
                        info_parts.append("🔍 IBKR Contract Lookup:")
                        info_parts.append("   💹 Market Data:")
                        # Bid/Ask line (side-by-side)
                        if bid != 'N/A' and ask != 'N/A':
                            info_parts.append(f"      💰 Bid ${bid} | ${ask} Ask 💸 ")
                        else:
                            if bid != 'N/A':
                                info_parts.append(f"      💰 Bid: ${bid}")
                            if ask != 'N/A':
                                info_parts.append(f"      💸 Ask: ${ask}")

                        # Last price with open interest if available
                        if last != 'N/A':
                            last_price_line = f"      📈 Last: ${last}"
                            if open_interest and open_interest != 'N/A':
                                last_price_line += f" | OI: {open_interest}"
                            info_parts.append(last_price_line)
                        
            else:
                # No position - show contract value if available
                contract_details = processed_data.get('contract_details')
                spread_info = processed_data.get('spread_info')
                
                if spread_info and spread_info.get('bid') != 'N/A':
                    bid = spread_info.get('bid', 'N/A')
                    ask = spread_info.get('ask', 'N/A')
                    last = spread_info.get('last', 'N/A')
                    open_interest = spread_info.get('open_interest')

                    # Use the same IBKR Contract Lookup block as Real Day Trading
                    info_parts.append("🔍 IBKR Contract Lookup:")
                    info_parts.append("   💹 Market Data:")
                    if bid != 'N/A' and ask != 'N/A':
                        info_parts.append(f"      💰 Bid ${bid} | ${ask} Ask 💸 ")
                    else:
                        if bid != 'N/A':
                            info_parts.append(f"      💰 Bid: ${bid}")
                        if ask != 'N/A':
                            info_parts.append(f"      💸 Ask: ${ask}")
                    if last != 'N/A':
                        last_line = f"      📈 Last: ${last}"
                        if open_interest and open_interest != 'N/A':
                            last_line += f" | OI: {open_interest}"
                        info_parts.append(last_line)
                        
                elif processed_data.get('contract_to_use'):
                    # Have contract but no pricing data
                    contract = processed_data.get('contract_to_use')
                    strike = contract.get('strike')
                    side = contract.get('side', '').upper()
                    
                    if strike and side:
                        side_emoji = "🔴" if side.startswith('P') else "🟢"
                        info_parts.append(f"{side_emoji} **Contract:** {strike}{side[0]} (No pricing data)")
                else:
                    # No contract or position
                    info_parts.append("💬 **General Alert** (No contract specified)")
            
            return "\n".join(info_parts) if info_parts else ""
            
        except Exception as e:
            logger.error(f"Error formatting demslayer position info: {e}")
            return ""

    def _is_demspxslayer(self, alerter_name: str = '', processed_data: dict | None = None, title: str = '', message: str = '') -> bool:
        """Detect demslayer-style alerts even when the alerter name changed.

        Returns True if 'demspxslayer' or 'demslayer' appears in the alerter name,
        processed_data title/message, or the provided title/message strings.
        """
        try:
            parts = []
            if alerter_name:
                parts.append(str(alerter_name))
            if processed_data and isinstance(processed_data, dict):
                # common fields where original message/title may be stored
                for k in ('title', 'message', 'original_message', 'additional_info'):
                    v = processed_data.get(k)
                    if v:
                        parts.append(str(v))
            if title:
                parts.append(str(title))
            if message:
                parts.append(str(message))
            combined = ' '.join(parts).lower()
            return 'demspxslayer' in combined or 'demslayer' in combined
        except Exception:
            return False

    def _find_matching_open_position(self, text: str) -> dict | None:
        """Search IBKR open positions for a ticker mentioned in `text`.

        Returns the position dict when a match is found (prefers exact symbol or $SYMBOL),
        otherwise None.
        """
        try:
            if not text or not isinstance(text, str):
                return None
            # Normalize
            text_lower = text.lower()

            from app.services.ibkr_service import IBKRService
            ibkr = IBKRService()

            # Prefer formatted positions, fallback to raw positions
            positions = []
            try:
                positions = ibkr.get_formatted_positions() or []
            except Exception:
                try:
                    positions = ibkr.get_positions() or []
                except Exception:
                    positions = []

            candidate = None
            candidate_score = 0

            # Helper to test if a symbol appears in text (exact token or $SYMBOL)
            def text_contains_symbol(sym: str) -> bool:
                if not sym:
                    return False
                s = re.escape(sym)
                # Match $SYM or whole-word SYM (case-insensitive)
                if re.search(rf"\${s}\b", text, flags=re.IGNORECASE):
                    return True
                if re.search(rf"\b{s}\b", text, flags=re.IGNORECASE):
                    return True
                return False

            for p in positions:
                try:
                    pos_qty = p.get('position', 0)
                    try:
                        pos_qty_val = abs(int(pos_qty))
                    except Exception:
                        try:
                            pos_qty_val = abs(int(float(pos_qty)))
                        except Exception:
                            pos_qty_val = 0
                    if pos_qty_val <= 0:
                        continue

                    # collect candidate symbols to test
                    syms = set()
                    for k in ('symbol', 'contractDesc'):
                        v = p.get(k)
                        if isinstance(v, str) and v:
                            # contractDesc can contain spaces; take first token as symbol candidate
                            if k == 'contractDesc':
                                syms.add(v.split()[0])
                            else:
                                syms.add(v)
                    # also check nested contract details
                    cd = p.get('contract') or p.get('contract_details') or {}
                    if isinstance(cd, dict):
                        v = cd.get('symbol') or cd.get('full_name')
                        if v:
                            syms.add(v)

                    # Score matches: exact token or $SYMBOL gives high score, substring lower
                    for s in syms:
                        if not s:
                            continue
                        score = 0
                        if text_contains_symbol(s):
                            score += 100
                        # minor extra score for larger positions
                        score += min(pos_qty_val, 100)
                        if score > candidate_score:
                            candidate_score = score
                            candidate = p
                            # annotate chosen symbol
                            candidate['_matched_symbol'] = s
                except Exception:
                    continue

            return candidate
        except Exception:
            return None
    
    def _format_real_day_trading_details(self, processed_data: dict, additional_info: str = "") -> str:
        """
        Format Real Day Trading specific details including IBKR contract information
        
        Args:
            processed_data: Processed data from Real Day Trading handler
            additional_info: Any additional info to include
            
        Returns:
            Formatted details string
        """
        try:
            details = []
            
            # Start with original additional info if provided
            if additional_info:
                details.append(additional_info)
            
            # Trading action and instrument details
            if 'action' in processed_data:
                details.append(f"📈 Action: {processed_data['action']}")
            
            # Smart instrument display - show option details when available
            instrument_display = processed_data.get('instrument_type', 'UNKNOWN')
            
            # If we have option contract details, format as "350C 9/19" instead of "STOCK"
            if ('ibkr_contract_result' in processed_data and 
                processed_data['ibkr_contract_result'] and 
                'contract_details' in processed_data['ibkr_contract_result']):
                
                contract_details = processed_data['ibkr_contract_result']['contract_details']
                strike = contract_details.get('strike', '')
                option_type = contract_details.get('right', '')
                expiry = contract_details.get('expiry', '')
                
                # Format as "350C 9/19" if we have all the details
                if strike and option_type and expiry and len(expiry) == 8:
                    try:
                        month = expiry[4:6]
                        day = expiry[6:8]
                        short_date = f"{int(month)}/{int(day)}"
                        instrument_display = f"{strike}{option_type} {short_date}"
                    except:
                        pass  # Fall back to original instrument_type
            
            details.append(f"📊 Instrument: {instrument_display}")
            
            # Strike and expiration info (only show if not already in instrument display)
            if (instrument_display == processed_data.get('instrument_type', 'UNKNOWN') and 
                'strike_price' in processed_data and processed_data['strike_price']):
                details.append(f"🎯 Strike: {processed_data['strike_price']}")
            
            if (instrument_display == processed_data.get('instrument_type', 'UNKNOWN') and 
                'expiration_date' in processed_data and processed_data['expiration_date']):
                details.append(f"📅 Expiry: {processed_data['expiration_date']}")
            
            # IBKR Contract Details Section
            if 'ibkr_contract_result' in processed_data and processed_data['ibkr_contract_result']:
                ibkr_data = processed_data['ibkr_contract_result']
                details.append("")  # Add spacing
                details.append("🔍 IBKR Contract Lookup:")
                
                # Contract symbol with properly formatted expiration
                # Support multiple shapes for ibkr_data:
                # - {'contract_details': {...}, 'market_data': {...}}
                # - the contract_details dict itself (older/newer handlers may set this)
                contract_details = None
                if isinstance(ibkr_data, dict) and 'contract_details' in ibkr_data and ibkr_data['contract_details']:
                    contract_details = ibkr_data['contract_details']
                else:
                    # If ibkr_data itself looks like a contract_details dict (has strike/right/expiry/conid), accept it
                    if isinstance(ibkr_data, dict) and any(k in ibkr_data for k in ('strike', 'right', 'expiry', 'conid')):
                        contract_details = ibkr_data
                    symbol = contract_details.get('symbol', '')
                    strike = contract_details.get('strike', '')
                    option_type = contract_details.get('right', '')
                    expiry = contract_details.get('expiry', '')
                    
                    # Format expiry as MM/DD if we have the full date
                    formatted_expiry = expiry
                    if expiry and len(expiry) == 8:  # Format: YYYYMMDD
                        try:
                            month = expiry[4:6]
                            day = expiry[6:8]
                            formatted_expiry = f"{int(month)}/{int(day)}"
                        except:
                            formatted_expiry = expiry
                    
                    # Create formatted symbol
                    if symbol and strike and option_type:
                        formatted_symbol = f"{symbol} ${strike}{option_type} {formatted_expiry}"
                        details.append(f"   📜 Symbol: {formatted_symbol}")
                    elif contract_details and 'full_name' in contract_details:
                        details.append(f"   📜 Symbol: {contract_details['full_name']}")
                
                # Calculate and show days to expiration
                if 'contract_details' in ibkr_data and 'expiry' in ibkr_data['contract_details']:
                    expiry_date = ibkr_data['contract_details']['expiry']
                    if expiry_date and len(expiry_date) == 8:  # Format: YYYYMMDD
                        try:
                            from datetime import datetime
                            expiry_dt = datetime.strptime(expiry_date, '%Y%m%d')
                            current_dt = datetime.now()
                            days_to_exp = (expiry_dt - current_dt).days
                            
                            if days_to_exp >= 0:
                                details.append(f"   📅 DTE: {days_to_exp}")
                            else:
                                details.append(f"   📅 DTE: {days_to_exp} (Expired)")
                        except Exception as e:
                            pass  # Skip if date parsing fails
                
                # Market data if available (handle multiple possible shapes)
                market_data = None
                # ibkr_data may be either:
                # 1) a dict containing keys 'contract_details' and 'market_data'
                # 2) the contract_details dict itself (older/alternate shape)
                # 3) absent; market data may be present at top-level as 'ibkr_market_data' or 'spread_info'
                try:
                    # Case A: nested shape { 'contract_details': {...}, 'market_data': {...} }
                    if isinstance(ibkr_data, dict) and 'market_data' in ibkr_data and ibkr_data.get('market_data'):
                        market_data = ibkr_data.get('market_data')
                    # Case B: handler stored contract_details directly in ibkr_data (so look for market fields on that dict)
                    elif isinstance(ibkr_data, dict) and any(k in ibkr_data for k in ('bid', 'ask', 'last', 'open_interest')):
                        market_data = ibkr_data
                    # Case C: nested 'contract_details' may contain 'market_data'
                    elif isinstance(ibkr_data, dict) and 'contract_details' in ibkr_data and isinstance(ibkr_data.get('contract_details'), dict):
                        cd = ibkr_data.get('contract_details')
                        if cd.get('market_data'):
                            market_data = cd.get('market_data')
                except Exception:
                    market_data = None

                # Top-level fallbacks used by older code paths
                if not market_data:
                    market_data = processed_data.get('ibkr_market_data') or processed_data.get('spread_info')
                
                if market_data:
                    details.append("   💹 Market Data:")
                    
                    # Show bid-ask side by side
                    bid = market_data.get('bid', 'N/A')
                    ask = market_data.get('ask', 'N/A')
                    if bid != 'N/A' and ask != 'N/A':
                        details.append(f"      💰 Bid ${bid} | ${ask} Ask 💸 ")
                    else:
                        if bid != 'N/A':
                            details.append(f"      💰 Bid: ${bid}")
                        if ask != 'N/A':
                            details.append(f"      💸 Ask: ${ask}")
                    
                    # Show last price with open interest if available
                    if 'last' in market_data and market_data['last'] != 'N/A':
                        last_price_line = f"      📈 Last: ${market_data['last']}"
                        
                        # Add open interest if available
                        if 'open_interest' in market_data and market_data['open_interest'] != 'N/A':
                            last_price_line += f" | OI: {market_data['open_interest']}"
                            
                        details.append(last_price_line)
                
                # Add expiration info if defaulted
                if 'expiration_info' in ibkr_data:
                    exp_info = ibkr_data['expiration_info']
                    if 'closest_expiration' in exp_info:
                        details.append(f"   ℹ️ Note: Used closest available expiration")
            
            # Confidence info only (removed price display since we have market data)
            if 'confidence' in processed_data:
                details.append(f"✅ **Confidence**: {processed_data['confidence']}")
            
            return "\n".join(details) if details else additional_info
            
        except Exception as e:
            logger.error(f"Error formatting Real Day Trading details: {e}")
            return additional_info or ""
    
    async def send_lite_alert(self, message: str) -> Dict[str, Any]:
        """
        Send a simple alert message without additional formatting
        Used by lite handlers for clean, compact messages
        """
        try:
            chat_id_to_use = 86655387  # Known working chat ID
            
            if not chat_id_to_use:
                logger.warning("No chat ID available. User needs to start the bot first.")
                return {
                    "success": False,
                    "message": "No chat ID available",
                    "error": "missing_chat_id"
                }
            
            if not self.bot or not getattr(self.bot, 'send_message', None):
                logger.error("Telegram bot instance not available")
                return {
                    "success": False,
                    "message": "Telegram bot not initialized",
                    "error": "bot_not_available"
                }
            
            # Generate unique message ID
            import uuid
            message_id = str(uuid.uuid4()).replace('-', '')[:8]
            
            # Send the message as-is without additional formatting
            sent_message = await self.bot.send_message(
                chat_id=chat_id_to_use,
                text=message,
                parse_mode='HTML'
            )
            
            logger.info(f"Sent trading alert to Telegram. Message ID: {message_id}")
            
            return {
                "success": True,
                "message": "Alert sent successfully",
                "message_id": message_id,
                "telegram_message_id": sent_message.message_id,
                "chat_id": chat_id_to_use
            }
            
        except Exception as e:
            logger.exception("Error sending lite alert")
            return {
                "success": False,
                "message": f"Failed to send alert: {str(e)}",
                "error": str(e)
            }
    
    async def send_trading_alert(self, alerter_name: str, message: str, 
                                ticker: str = "", additional_info: str = "", processed_data: dict = None) -> Dict[str, Any]:
        """
        Send a trading alert with Buy/Sell buttons
        
        Args:
            alerter_name: Name of the alerter (e.g., "Nyrleth")
            message: The alert message
            ticker: Stock ticker (optional)
            additional_info: Additional information (optional)
            
        Returns:
            Dict with send result and message tracking info
        """
        try:
            # Use discovered chat ID from testing
            chat_id_to_use = 86655387  # Known working chat ID from test
            
            if not chat_id_to_use:
                logger.warning("No chat ID available. User needs to start the bot first.")
                return {
                    "success": False,
                    "message": "No chat ID available. User needs to start the bot first.",
                    "error": "missing_chat_id"
                }
            
            # Ensure processed_data is a dict to avoid accidental NoneType attribute access
            if processed_data is None:
                processed_data = {}

            # If processed_data lacks IBKR position info but we have a ticker, try to enrich
            # by asking IBKR for any open option positions that match the ticker. This
            # ensures alerts for tickers with existing option positions show the
            # position panel and close controls in Telegram.
            try:
                if not processed_data.get('ibkr_position_size'):
                    ticker_for_check = ticker or processed_data.get('ticker')
                    if ticker_for_check:
                        from app.services.ibkr_service import IBKRService
                        ibkr = IBKRService()
                        # Try formatted positions first (more consistent fields)
                        found = False
                        try:
                            for p in (ibkr.get_formatted_positions() or []):
                                sec_type = (p.get('secType') or '').upper()
                                symbol = (p.get('symbol') or '')
                                try:
                                    pos_qty = int(p.get('position', 0))
                                except Exception:
                                    pos_qty = 0
                                if sec_type == 'OPT' and ticker_for_check.upper() in str(symbol).upper() and pos_qty != 0:
                                    processed_data['ibkr_position_size'] = abs(pos_qty)
                                    processed_data['ibkr_unrealized_pnl'] = p.get('unrealizedPnl')
                                    processed_data['ibkr_realized_pnl'] = p.get('realizedPnl')
                                    processed_data['ibkr_market_value'] = p.get('marketValue') or p.get('mktValue')
                                    processed_data['ibkr_avg_price'] = p.get('avgPrice') or p.get('avgCost')
                                    processed_data['ibkr_current_price'] = p.get('currentPrice') or p.get('mktPrice')
                                    processed_data['show_close_position_button'] = True
                                    found = True
                                    break
                        except Exception:
                            found = False

                        # Fallback to raw positions if formatted not available or not found
                        if not found:
                            try:
                                for p in (ibkr.get_positions() or []):
                                    sec_type = (p.get('secType') or p.get('assetClass') or '').upper()
                                    symbol = (p.get('contractDesc') or p.get('symbol') or '')
                                    try:
                                        pos_qty = int(p.get('position', 0))
                                    except Exception:
                                        pos_qty = 0
                                    if sec_type == 'OPT' and ticker_for_check.upper() in str(symbol).upper() and pos_qty != 0:
                                        processed_data['ibkr_position_size'] = abs(pos_qty)
                                        processed_data['ibkr_unrealized_pnl'] = p.get('unrealizedPnl')
                                        processed_data['ibkr_realized_pnl'] = p.get('realizedPnl')
                                        processed_data['ibkr_market_value'] = p.get('mktValue') or p.get('marketValue')
                                        processed_data['ibkr_avg_price'] = p.get('avgPrice') or p.get('avgCost')
                                        processed_data['ibkr_current_price'] = p.get('mktPrice') or p.get('currentPrice')
                                        processed_data['show_close_position_button'] = True
                                        found = True
                                        break
                            except Exception:
                                pass
                    # If still not found and this is NOT a demslayer-style alert,
                    # try to match any open position symbol mentioned in the message
                    # or additional_info. This covers RobinDaHood updates that reference
                    # a stock we already hold but did not include a parsed contract.
                    try:
                        if not found and not self._is_demspxslayer(alerter_name, processed_data, title=additional_info, message=message):
                            # Search in message and additional_info for ticker mention
                            text_to_search = ' '.join([str(x) for x in (message or '', additional_info or '') if x])
                            matched = self._find_matching_open_position(text_to_search)
                            if matched:
                                # Only enrich if the matched symbol is registered for this alerter
                                try:
                                    from app.services.alerter_stock_storage import alerter_stock_storage
                                    symbol_guess = matched.get('_matched_symbol') or matched.get('symbol') or matched.get('contractDesc')
                                    symbol_key = None
                                    if isinstance(symbol_guess, str):
                                        symbol_key = symbol_guess.split()[0].upper()
                                    allow_enrich = False
                                    if symbol_key:
                                        try:
                                            allow_enrich = alerter_stock_storage.is_stock_already_alerted(alerter_name, symbol_key)
                                        except Exception:
                                            allow_enrich = False
                                    if not allow_enrich:
                                        logger.debug(f"Skipping enrichment in send_trading_alert: matched '{symbol_guess}' not registered for alerter '{alerter_name}'")
                                    else:
                                        # Populate processed_data similarly to ticker-based enrichment
                                        try:
                                            pos_qty = matched.get('position', 0)
                                            try:
                                                processed_data['ibkr_position_size'] = abs(int(pos_qty))
                                            except Exception:
                                                try:
                                                    processed_data['ibkr_position_size'] = abs(int(float(pos_qty)))
                                                except Exception:
                                                    processed_data['ibkr_position_size'] = pos_qty
                                        except Exception:
                                            processed_data['ibkr_position_size'] = matched.get('position')
                                        processed_data['ibkr_unrealized_pnl'] = matched.get('unrealizedPnl') or matched.get('unrealized')
                                        processed_data['ibkr_realized_pnl'] = matched.get('realizedPnl') or matched.get('realized')
                                        processed_data['ibkr_market_value'] = matched.get('marketValue') or matched.get('mktValue')
                                        processed_data['ibkr_avg_price'] = matched.get('avgPrice') or matched.get('avgCost')
                                        processed_data['ibkr_current_price'] = matched.get('currentPrice') or matched.get('mktPrice') or (matched.get('market_data') or {}).get('last')
                                        processed_data['show_close_position_button'] = True
                                        # Attach contract-like info if available
                                        try:
                                            if matched.get('contract_details'):
                                                processed_data.setdefault('contract_details', matched.get('contract_details'))
                                        except Exception:
                                            pass
                                        logger.info(f"Enriched alert by matching open position: {matched.get('symbol') or matched.get('contractDesc')}")
                                except Exception as e:
                                    logger.debug(f"Enrichment check failed: {e}")
                    except Exception:
                        pass
            except Exception:
                # Keep original processed_data on any failure; this enrichment is best-effort
                pass

            # Generate unique message ID for tracking
            message_id = str(uuid.uuid4())[:8]
            
            # Format contract display with visual enhancements
            formatted_ticker, enhanced_additional_info = self._format_contract_display(
                ticker, additional_info, alerter_name, processed_data
            )

            # Debug: log processed_data summary so we can diagnose missing initial estimates
            try:
                if processed_data is None:
                    logger.debug("send_trading_alert: processed_data is None")
                else:
                    try:
                        pdata_keys = list(processed_data.keys())
                    except Exception:
                        pdata_keys = str(type(processed_data))
                    logger.debug(
                        "send_trading_alert: processed_data keys=%s | ibkr_position_size=%s | ibkr_unrealized_pnl=%s | ibkr_realized_pnl=%s",
                        pdata_keys,
                        processed_data.get('ibkr_position_size'),
                        processed_data.get('ibkr_unrealized_pnl'),
                        processed_data.get('ibkr_realized_pnl')
                    )
            except Exception as e:
                logger.debug(f"Error logging processed_data debug info: {e}")

            # For demslayer-style alerts, ensure processed_data is populated from persistent contract storage
            if self._is_demspxslayer(alerter_name, processed_data):
                try:
                    from app.services.contract_storage import contract_storage
                except Exception:
                    contract_storage = None

                # If we don't already have contract_details in processed_data, try to load stored contract
                stored = None
                try:
                    if contract_storage:
                        # Try the provided alerter key first, then fall back to the legacy key
                        stored = contract_storage.get_contract(alerter_name)
                        if not stored:
                            try:
                                legacy = contract_storage.get_contract('demslayer-spx-alerts')
                                if legacy:
                                    # Migrate legacy key to current alerter_name if possible
                                    try:
                                        migrated = contract_storage.migrate_contract_key('demslayer-spx-alerts', alerter_name)
                                        if migrated:
                                            stored = contract_storage.get_contract(alerter_name)
                                        else:
                                            stored = legacy
                                    except Exception:
                                        stored = legacy
                            except Exception:
                                stored = stored
                except Exception:
                    stored = None

                # If stored contract exists and processed_data is missing IBKR details, fetch them
                if stored and not (processed_data and processed_data.get('contract_details')):
                    try:
                        from app.services.ibkr_service import IBKRService
                        ibkr = IBKRService()
                        # Build a minimal contract dict expected by IBKR helper
                        lookup = {
                            'symbol': stored.get('symbol', 'SPX'),
                            'strike': stored.get('strike'),
                            'right': 'C' if (stored.get('side') or '').upper().startswith('C') else 'P',
                            'expiry': stored.get('expiry')
                        }
                        contract_details = ibkr.get_option_contract_details(
                            symbol=lookup['symbol'],
                            strike=lookup['strike'],
                            right=lookup['right'],
                            expiry=lookup['expiry']
                        )
                        spread_info = None
                        try:
                            spread_info = ibkr.get_option_market_data(contract_details) if contract_details else None
                        except Exception:
                            spread_info = None

                        # Check for an open IBKR position matching this contract
                        ibkr_position = None
                        try:
                            for p in (ibkr.get_formatted_positions() or []):
                                sym = (p.get('symbol') or '').upper()
                                if contract_details and contract_details.get('symbol') and contract_details.get('symbol').upper() in sym:
                                    if p.get('position', 0) != 0:
                                        ibkr_position = p
                                        break
                        except Exception:
                            ibkr_position = None

                        # Populate processed_data fields expected by send_trading_alert
                        if processed_data is None:
                            processed_data = {}

                        processed_data.setdefault('stored_contract', stored)
                        if contract_details:
                            processed_data.setdefault('contract_details', contract_details)
                        if spread_info:
                            processed_data.setdefault('spread_info', spread_info)

                        if ibkr_position:
                            try:
                                processed_data['ibkr_position_size'] = abs(int(ibkr_position.get('position', 0)))
                            except Exception:
                                processed_data['ibkr_position_size'] = ibkr_position.get('position')
                            processed_data['ibkr_unrealized_pnl'] = ibkr_position.get('unrealizedPnl')
                            processed_data['ibkr_realized_pnl'] = ibkr_position.get('realizedPnl')
                            processed_data['ibkr_market_value'] = ibkr_position.get('marketValue') or ibkr_position.get('mktValue')
                            processed_data['ibkr_avg_price'] = ibkr_position.get('avgPrice') or ibkr_position.get('avgCost')
                            processed_data['ibkr_current_price'] = ibkr_position.get('currentPrice') or ibkr_position.get('mktPrice')
                            processed_data['show_close_position_button'] = True
                        else:
                            # No open position for stored contract
                            processed_data.setdefault('ibkr_position_size', 0)
                            processed_data.setdefault('ibkr_unrealized_pnl', None)
                            processed_data.setdefault('ibkr_realized_pnl', None)
                            processed_data.setdefault('ibkr_market_value', None)
                            processed_data.setdefault('ibkr_avg_price', None)
                            processed_data.setdefault('ibkr_current_price', None)
                            processed_data['show_close_position_button'] = False
                    except Exception as e:
                        logger.debug(f"Error populating demslayer processed_data from IBKR: {e}")

                # End demslayer stored-contract enrichment

                # (No non-demslayer fallback enrichment here; keep behavior unchanged)

                # Ensure processed_data is preserved back into the local variable
                # (telegram_service will store it later when creating pending_messages)

            # Build an HTML-formatted message (escaped) for nicer Telegram display
            from html import escape as _html_escape

            def esc(x):
                return _html_escape(str(x)) if x is not None else ""

            alert_html = f"🚨 <b>Trading Alert</b>\n\n"
            alert_html += f"🎯 <b>Alerter:</b> {esc(alerter_name)}\n"

            # Show Contract line when we were able to format a contract display
            # (don't rely on the caller to provide `ticker` — many handlers leave
            # that empty but still provide contract details in processed_data).
            if formatted_ticker:
                # formatted_ticker may include emojis; escape nonetheless
                alert_html += f"📊 <b>Contract:</b> <code>{esc(formatted_ticker)}</code>\n"

            alert_html += f"💬 <b>Message:</b> {esc(message)}\n"

            # Unified Details block: always show enhanced additional info the same way
            # Use a pre block to preserve line breaks and ensure consistent display
            if enhanced_additional_info:
                try:
                    alert_html += f"\nℹ️ <i>Details:</i>\n<pre>{esc(enhanced_additional_info)}</pre>\n"
                except Exception:
                    # Fallback to a simple inline details line if pre fails
                    alert_html += f"\nℹ️ <i>Details:</i> {esc(enhanced_additional_info)}\n"

            # If processed_data contains IBKR contract details or market data,
            # include a small IBKR Contract Lookup block so non-demslayer alerts
            # (e.g., RobinDaHood) show the same market-data section.
            try:
                # Make contract/market-data discovery permissive: different handlers
                # populate different keys depending on environment. Prefer the
                # canonical keys but fall back to several alternatives.
                cd = None
                md = None
                if processed_data:
                    cd = (
                        processed_data.get('contract_details')
                        or processed_data.get('contract_to_use')
                        or processed_data.get('stored_contract')
                        or processed_data.get('ibkr_contract_result')
                        or processed_data.get('ibkr_contract')
                        or processed_data.get('contract')
                    )
                    md = (
                        processed_data.get('spread_info')
                        or processed_data.get('ibkr_market_data')
                        or processed_data.get('market_data')
                        or (processed_data.get('ibkr_contract_result') or {}).get('market_data')
                        or (processed_data.get('contract_details') or {}).get('market_data')
                    )

                if cd or md:
                    # If we don't have a visible formatted_ticker yet, attempt to
                    # derive one from the contract details so the Contract: line
                    # always appears in the alert.
                    try:
                        if not formatted_ticker and isinstance(cd, dict):
                            s = cd.get('symbol') or cd.get('underlying') or cd.get('root')
                            strike = cd.get('strike')
                            right = cd.get('right') or cd.get('side')
                            expiry = cd.get('expiry')
                            if s and strike is not None and right:
                                try:
                                    strike_disp = str(int(float(strike))) if float(strike).is_integer() else str(strike)
                                except Exception:
                                    strike_disp = str(strike)
                                right_disp = (right[0].upper() if right else '')
                                date_disp = ''
                                if isinstance(expiry, str) and len(expiry) == 8:
                                    try:
                                        m = int(expiry[4:6]); d = int(expiry[6:8])
                                        date_disp = f"{m}/{d}"
                                    except Exception:
                                        date_disp = expiry
                                parts = [str(s).upper(), f"{strike_disp}{right_disp}"]
                                if date_disp:
                                    parts.append(date_disp)
                                formatted_ticker = ' - '.join(parts)
                    except Exception:
                        pass

                    alert_html += "\n🔍 <b>IBKR Contract Lookup:</b>\n"
                    # Symbol/contract line
                    try:
                        symbol = cd.get('symbol') if isinstance(cd, dict) else None
                        strike = cd.get('strike') if isinstance(cd, dict) else None
                        right = cd.get('right') if isinstance(cd, dict) else (cd.get('side') if isinstance(cd, dict) else None)
                        expiry = cd.get('expiry') if isinstance(cd, dict) else None
                        if symbol and strike and right:
                            # Format expiry if present
                            formatted_expiry = expiry
                            if isinstance(expiry, str) and len(expiry) == 8:
                                try:
                                    m = int(expiry[4:6]); d = int(expiry[6:8])
                                    formatted_expiry = f"{m}/{d}"
                                except Exception:
                                    pass
                            alert_html += f"   📜 <b>Symbol:</b> {esc(symbol)} {esc(str(strike))}{esc(str(right))} {esc(formatted_expiry)}\n"
                    except Exception:
                        pass

                    # Market data block if available
                    if md and isinstance(md, dict):
                        bid = md.get('bid', 'N/A')
                        ask = md.get('ask', 'N/A')
                        last = md.get('last', 'N/A')
                        oi = md.get('open_interest') or md.get('openInterest') or md.get('open_interest')
                        alert_html += f"   💹 <i>Market Data:</i>\n"
                        if bid != 'N/A' and ask != 'N/A':
                            alert_html += f"      💰 Bid ${esc(bid)} | ${esc(ask)} Ask 💸 \n"
                        else:
                            if bid != 'N/A':
                                alert_html += f"      💰 Bid: ${esc(bid)}\n"
                            if ask != 'N/A':
                                alert_html += f"      💸 Ask: ${esc(ask)}\n"
                        if last != 'N/A':
                            last_line = f"      📈 Last: ${esc(last)}"
                            if oi:
                                last_line += f" | OI: {esc(oi)}"
                            alert_html += last_line + "\n"
            except Exception:
                # Best-effort only; don't block sending on formatting errors
                logger.debug("Failed to append IBKR Contract Lookup block")

            alert_html += f"\n🆔 ID: <code>{esc(message_id)}</code>"

            # Mandatory: Always include IBKR P/L and position info if available in processed_data
            try:
                if processed_data:
                    ibkr_unreal = processed_data.get('ibkr_unrealized_pnl')
                    ibkr_real = processed_data.get('ibkr_realized_pnl')
                    ibkr_avg = processed_data.get('ibkr_avg_price')
                    ibkr_curr = processed_data.get('ibkr_current_price')
                    ibkr_mv = processed_data.get('ibkr_market_value')
                    ibkr_pos = processed_data.get('ibkr_position_size')
                    pl_lines = []
                    if ibkr_pos is not None:
                        try:
                            pl_lines.append(f"📊 Position (IBKR): {int(ibkr_pos)}")
                        except Exception:
                            pl_lines.append(f"📊 Position (IBKR): {ibkr_pos}")
                    if ibkr_avg is not None:
                        pl_lines.append(f"Avg: ${ibkr_avg}")
                    if ibkr_curr is not None:
                        pl_lines.append(f"Current: ${ibkr_curr}")
                    if ibkr_mv is not None:
                        pl_lines.append(f"Market Value: ${ibkr_mv}")
                    # Unrealized P/L coloring: green for positive, red for negative, neutral circle for zero
                    if ibkr_unreal is not None:
                        if ibkr_unreal > 0:
                            pl_lines.append(f"🟢 Unrealized P/L: +${abs(ibkr_unreal):,.2f}")
                        elif ibkr_unreal < 0:
                            pl_lines.append(f"🔴 Unrealized P/L: -${abs(ibkr_unreal):,.2f}")
                        else:
                            pl_lines.append(f"⚪ Unrealized P/L: $0.00")
                    # Realized P/L coloring
                    if ibkr_real is not None:
                        if ibkr_real > 0:
                            pl_lines.append(f"🟢 Realized P/L: +${abs(ibkr_real):,.2f}")
                        elif ibkr_real < 0:
                            pl_lines.append(f"🔴 Realized P/L: -${abs(ibkr_real):,.2f}")
                        else:
                            pl_lines.append(f"⚪ Realized P/L: $0.00")
                    if pl_lines:
                        # Use a pre block for readable multi-line summary
                        alert_html += "\n\n<b>💰 IBKR Position Summary:</b>\n"
                        alert_html += "<pre>"
                        for line in pl_lines:
                            alert_html += esc(line) + "\n"
                        alert_html += "</pre>"
            except Exception:
                logger.debug("Error building IBKR P/L display, skipping")

            # Mandatory: Always include IBKR P/L and position info if available in processed_data
            # (No-op) IBKR P/L is already added to the HTML message above (alert_html).
            # The previous plain-text assembly was removed to avoid referencing
            # an undefined `alert_text` variable and to keep a single canonical
            # message format (HTML) for sending.

            # Provide a plain-text accumulator for backward-compatible sections
            # of the function that still append to `alert_text`. We keep
            # `alert_html` as the canonical HTML message sent to Telegram,
            # but initialize `alert_text` so appends won't raise UnboundLocalError.
            alert_text = ""
            

            # Check for open position using IBKR and storage for Real Day Trading
            has_position = False
            position_size = 0
            ticker_for_check = None
            option_contracts = None
            # Always check IBKR positions/contracts for the alert ticker so
            # we can show a close-position panel when an options position exists.
            if True:
                # Parse $TICKER from message for all alerters
                import re
                match = re.search(r'\$([A-Z]+)', message)
                if match:
                    ticker_for_check = match.group(1)
                if not ticker_for_check:
                    ticker_for_check = processed_data.get('ticker')

                # For all alerters, check stored contracts first, then IBKR positions.
                try:
                    option_contracts = []
                    # 1) Try persisted storage (fast)
                    try:
                        from app.services.alerter_stock_storage import alerter_stock_storage
                        contracts_summary = alerter_stock_storage.get_total_open_contracts(alerter_name)
                        logger.debug(f"Contracts summary from storage for {alerter_name}: {contracts_summary}")
                        if isinstance(contracts_summary, dict) and 'contracts' in contracts_summary:
                            for c in contracts_summary['contracts']:
                                if not ticker_for_check:
                                    continue
                                if (c.get('ticker') or '').upper() == ticker_for_check.upper():
                                    option_contracts.append(c)
                    except Exception as e:
                        logger.debug(f"No alerter storage or failed to read it: {e}")

                    # 2) Query IBKR positions (both raw and formatted) to find option positions
                    try:
                        from app.services.ibkr_service import IBKRService
                        ibkr = IBKRService()

                        inspected = []

                        # Raw positions
                        try:
                            for pos in ibkr.get_positions() or []:
                                inspected.append({'source': 'raw', 'pos': pos})
                                sec_type = (pos.get('assetClass') or pos.get('secType') or '').upper()
                                if sec_type != 'OPT':
                                    continue
                                # try multiple symbol fields that may contain underlying/description
                                symbol = (pos.get('contractDesc') or pos.get('symbol') or '')
                                try:
                                    pos_qty = abs(int(pos.get('position', 0)))
                                except Exception:
                                    try:
                                        pos_qty = abs(int(float(pos.get('position', 0))))
                                    except Exception:
                                        pos_qty = 0
                                if pos_qty <= 0:
                                    continue
                                if ticker_for_check and ticker_for_check.upper() in symbol.upper():
                                    # parse strike/side heuristically
                                    parts = symbol.split()
                                    strike = next((p for p in parts if p.replace('.', '', 1).isdigit()), None)
                                    side = next((p for p in parts if p.upper() in ['C', 'P']), None)
                                    option_contracts.append({
                                        'symbol': symbol,
                                        'ticker': ticker_for_check,
                                        'strike': strike,
                                        'side': 'CALL' if (side or '').upper() == 'C' else ('PUT' if (side or '').upper() == 'P' else None),
                                        'quantity': pos_qty,
                                        'unrealizedPnl': pos.get('unrealizedPnl'),
                                        'realizedPnl': pos.get('realizedPnl'),
                                        'marketValue': pos.get('mktValue') or pos.get('marketValue'),
                                        'avgPrice': pos.get('avgPrice') or pos.get('avgCost'),
                                        'currentPrice': pos.get('mktPrice') or pos.get('currentPrice')
                                    })

                        except Exception as e:
                            logger.debug(f"Error reading raw IBKR positions: {e}")

                        # Formatted positions (some environments expose nicer keys)
                        try:
                            for pos in ibkr.get_formatted_positions() or []:
                                inspected.append({'source': 'formatted', 'pos': pos})
                                sec_type = (pos.get('secType') or '').upper()
                                if sec_type != 'OPT':
                                    continue
                                symbol = (pos.get('symbol') or pos.get('description') or '')
                                try:
                                    pos_qty = abs(int(pos.get('position', 0)))
                                except Exception:
                                    try:
                                        pos_qty = abs(int(float(pos.get('position', 0))))
                                    except Exception:
                                        pos_qty = 0
                                if pos_qty <= 0:
                                    continue
                                if ticker_for_check and ticker_for_check.upper() in symbol.upper():
                                    parts = symbol.split()
                                    strike = next((p for p in parts if p.replace('.', '', 1).isdigit()), None)
                                    side = next((p for p in parts if p.upper() in ['C', 'P']), None)
                                    option_contracts.append({
                                        'symbol': symbol,
                                        'ticker': ticker_for_check,
                                        'strike': strike,
                                        'side': 'CALL' if (side or '').upper() == 'C' else ('PUT' if (side or '').upper() == 'P' else None),
                                        'quantity': pos_qty,
                                        'unrealizedPnl': pos.get('unrealizedPnl'),
                                        'realizedPnl': pos.get('realizedPnl'),
                                        'marketValue': pos.get('marketValue'),
                                        'avgPrice': pos.get('avgPrice') or pos.get('avgCost'),
                                        'currentPrice': pos.get('currentPrice')
                                    })
                        except Exception as e:
                            logger.debug(f"Error reading formatted IBKR positions: {e}")

                        logger.debug(f"Inspected {len(inspected)} IBKR positions for ticker match; found {len(option_contracts)} matching option rows")
                        # If we found option_contracts, set processed_data fields so downstream
                        # UI logic will show the close-position panel.
                        try:
                            if option_contracts:
                                position_size = sum(int(c.get('quantity', 0)) for c in option_contracts)
                                has_position = position_size > 0
                                # Populate processed_data so later formatting uses these values
                                try:
                                    processed_data.setdefault('ibkr_position_size', position_size)
                                except Exception:
                                    pass
                                try:
                                    processed_data['show_close_position_button'] = True
                                except Exception:
                                    pass
                                logger.info(f"Found option positions for {ticker_for_check}: size={position_size} rows={len(option_contracts)}")
                        except Exception:
                            pass

                    except Exception as e:
                        logger.debug(f"IBKR position lookup failed: {e}")
                except Exception as e:
                    logger.error(f"Error checking option contracts in storage/IBKR: {e}")

                # Fallback: Check IBKR positions (if available in processed_data)
                if not has_position:
                    # Use ibkr_position_size if present
                    if processed_data.get('ibkr_position_size') is not None:
                        position_size = int(processed_data.get('ibkr_position_size', 0))
                        has_position = position_size > 0
                    else:
                        position_data = processed_data.get('spx_position') or processed_data.get('position')
                        if position_data and isinstance(position_data, dict):
                            position_size = position_data.get('position', 0)
                            has_position = has_position or (position_size != 0)

                # If we have a position but no per-contract option rows, show IBKR position P/L as fallback
                if has_position and not option_contracts and processed_data:
                    # Add IBKR position P/L info directly to enhanced_additional_info if not already present
                    ibkr_unreal = processed_data.get('ibkr_unrealized_pnl')
                    ibkr_real = processed_data.get('ibkr_realized_pnl')
                    ibkr_avg = processed_data.get('ibkr_avg_price')
                    ibkr_curr = processed_data.get('ibkr_current_price')
                    ibkr_mv = processed_data.get('ibkr_market_value')
                    # Append to alert_text now (position block will be added below)
                    # We'll build a temporary display string and append after the position header
                    pl_lines = []
                    if ibkr_avg is not None:
                        pl_lines.append(f"Avg Price: ${ibkr_avg}")
                    if ibkr_curr is not None:
                        pl_lines.append(f"Current Price: ${ibkr_curr}")
                    if ibkr_mv is not None:
                        pl_lines.append(f"Market Value: ${ibkr_mv}")
                    if ibkr_unreal is not None:
                        pl_lines.append(f"Unrealized P/L: ${ibkr_unreal}" if ibkr_unreal == 0 else (f"✅ Unrealized P/L: +${abs(ibkr_unreal):,.2f}" if ibkr_unreal > 0 else f"❌ Unrealized P/L: -${abs(ibkr_unreal):,.2f}"))
                    if ibkr_real is not None:
                        pl_lines.append(f"Realized P/L: ${ibkr_real}" if ibkr_real == 0 else (f"💎 Realized P/L: +${abs(ibkr_real):,.2f}" if ibkr_real > 0 else f"💸 Realized P/L: -${abs(ibkr_real):,.2f}"))
                    # Store for later insertion
                    fallback_pl_display = " | ".join(pl_lines) if pl_lines else None
            
            # Prepare default values
            # If we have a known open position, default the close quantity to the
            # authoritative IBKR-reported position size when available. Fall back
            # to the summed option_contracts position_size if IBKR field is not
            # present. This avoids cases where per-contract rows are duplicated
            # (raw + formatted) and produce a larger summed value than the true
            # IBKR position.
            try:
                if has_position:
                    # Prefer processed_data.ibkr_position_size when available
                    try:
                        pd_pos = processed_data.get('ibkr_position_size')
                        if pd_pos is not None and int(pd_pos) > 0:
                            default_quantity = abs(int(pd_pos))
                        elif position_size:
                            default_quantity = abs(int(position_size))
                        else:
                            default_quantity = 1
                    except Exception:
                        # Defensive fallback
                        try:
                            default_quantity = abs(int(position_size)) if position_size else 1
                        except Exception:
                            default_quantity = 1
                else:
                    default_quantity = 1
            except Exception:
                default_quantity = 1
            midpoint_price = self._get_midpoint_price(processed_data)
            total_cost = midpoint_price * 100 * default_quantity if midpoint_price else 0

            # Add position and pricing information to alert text
            if not has_position:
                # No position: Show cost information
                alert_text += f"\n💰 Quantity: {default_quantity} contract(s)"
                if midpoint_price:
                    alert_text += f"\n💵 Price per contract: ${midpoint_price:.2f} (≈${midpoint_price * 100:.0f})"
                    alert_text += f"\n🏷️ Total cost: ${total_cost:.0f}"
            else:
                # Has position: Show position information and default close quantity
                alert_text += f"\n📊 Position: {abs(position_size)} contract(s)"
                # If we built a fallback PL display (from IBKR position fields), include it here
                try:
                    if 'fallback_pl_display' in locals() and fallback_pl_display:
                        logger.debug(f"Using fallback PL display: {fallback_pl_display}")
                        alert_text += f"\n   {fallback_pl_display}"
                except Exception:
                    pass
                if option_contracts:
                    for c in option_contracts:
                        # Use compact, unified contract display (e.g. 'SPY - 640C - 9/16')
                        try:
                            raw_ticker = c.get('symbol') or c.get('ticker') or ''
                            formatted_ticker, _ = self._format_contract_display(raw_ticker, additional_info='', alerter_name=alerter_name, processed_data=processed_data)
                            contract_line = f"   {formatted_ticker}"
                        except Exception:
                            # Fallback to legacy fields if formatting fails
                            contract_line = f"   {c.get('symbol') or c.get('ticker') or ''}"

                        # Show quantity and optional P/L/pricing info
                        contract_line += f" Qty: {c.get('quantity', 0)}"
                        if c.get('unrealizedPnl') is not None:
                            contract_line += f" | Unrealized P/L: ${c.get('unrealizedPnl')}"
                        if c.get('realizedPnl') is not None:
                            contract_line += f" | Realized P/L: ${c.get('realizedPnl')}"
                        if c.get('avgPrice') is not None:
                            contract_line += f" | Avg Price: ${c.get('avgPrice')}"
                        if c.get('currentPrice') is not None:
                            contract_line += f" | Current Price: ${c.get('currentPrice')}"
                        if c.get('marketValue') is not None:
                            contract_line += f" | Market Value: ${c.get('marketValue')}"
                        alert_text += f"\n{contract_line}"
                try:
                    # Show as selected/total when we know the position size
                    pos_disp = abs(int(position_size)) if position_size is not None else None
                except Exception:
                    pos_disp = None
                if pos_disp:
                    alert_text += f"\n💰 Close Quantity: {default_quantity}/{pos_disp} contract(s)"
                else:
                    alert_text += f"\n💰 Close Quantity: {default_quantity} contract(s)"

                # Also show estimated P/L for the default close quantity when we have IBKR data
                try:
                    ibkr_pos_size = processed_data.get('ibkr_position_size')
                    ibkr_unreal = processed_data.get('ibkr_unrealized_pnl')
                    ibkr_real = processed_data.get('ibkr_realized_pnl')

                    # Fallback: if IBKR position-level unrealized/realized P/L is missing
                    # but we have option_contracts entries, compute totals from those.
                    if (ibkr_unreal is None or ibkr_unreal == 0) and processed_data.get('option_contracts'):
                        try:
                            total_unreal = 0.0
                            total_real = 0.0
                            total_qty = 0
                            for oc in (processed_data.get('option_contracts') or []):
                                q = oc.get('quantity') or 0
                                try:
                                    qn = abs(int(q))
                                except Exception:
                                    try:
                                        qn = abs(int(float(q)))
                                    except Exception:
                                        qn = 0
                                up = oc.get('unrealizedPnl')
                                rp = oc.get('realizedPnl')
                                if up is not None:
                                    try:
                                        total_unreal += float(up)
                                    except Exception:
                                        pass
                                if rp is not None:
                                    try:
                                        total_real += float(rp)
                                    except Exception:
                                        pass
                                total_qty += qn
                            if total_qty > 0:
                                # Use totals and qty as IBKR position proxies
                                ibkr_unreal = total_unreal
                                ibkr_real = total_real
                                ibkr_pos_size = total_qty
                        except Exception:
                            pass

                    if ibkr_pos_size and default_quantity:
                        try:
                            pos_size_num = float(ibkr_pos_size)
                            if pos_size_num != 0:
                                per_unreal = (float(ibkr_unreal) / pos_size_num) if ibkr_unreal is not None else 0.0
                                per_real = (float(ibkr_real) / pos_size_num) if ibkr_real is not None else 0.0
                                est_unreal = per_unreal * float(default_quantity)
                                est_real = per_real * float(default_quantity)
                                def _color_amt(v):
                                    if v > 0:
                                        return f"🟢 +${abs(v):,.2f}"
                                    if v < 0:
                                        return f"🔴 -${abs(v):,.2f}"
                                    return f"⚪ $0.00"
                                # Append to plain text accumulator (backward-compat)
                                alert_text += f"\nEstimated close unrealized P/L for {default_quantity} contract(s): {_color_amt(est_unreal)}"
                                alert_text += f"\nEstimated close realized P/L for {default_quantity} contract(s): {_color_amt(est_real)}"
                                # Also append the same information to the canonical HTML message
                                try:
                                    def _color_amt_html(v):
                                        if v > 0:
                                            return f"🟢 +${abs(v):,.2f}"
                                        if v < 0:
                                            return f"🔴 -${abs(v):,.2f}"
                                        return f"⚪ $0.00"

                                    alert_html += "\n\n<b>🔎 Estimated Close P/L:</b>\n"
                                    alert_html += "<pre>"
                                    alert_html += esc(f"Estimated close unrealized P/L for {default_quantity} contract(s): {_color_amt_html(est_unreal)}") + "\n"
                                    alert_html += esc(f"Estimated close realized P/L for {default_quantity} contract(s): {_color_amt_html(est_real)}") + "\n"
                                    alert_html += "</pre>"
                                except Exception:
                                    # Don't let HTML insertion failures block sending
                                    logger.debug("Failed to append estimated P/L to alert_html")
                        except Exception:
                            pass
                except Exception:
                    pass
                if enhanced_additional_info and self._is_demspxslayer(alerter_name, processed_data):
                    # Position data already included in enhanced_additional_info
                    pass

            # Also include the calculated cost information in the canonical HTML message
            try:
                if not has_position:
                    alert_html += f"\n\n💰 Quantity: {default_quantity} contract(s)"
                    if midpoint_price:
                        alert_html += f"\n💵 Price per contract: ${midpoint_price:.2f} (≈${midpoint_price * 100:.0f})"
                        alert_html += f"\n🏷️ Total cost: ${total_cost:.0f}"
                else:
                    # When we have a position, show estimated total for the default close quantity as well
                    alert_html += f"\n\n💰 Close Quantity: {default_quantity} contract(s)"
                    if midpoint_price:
                        alert_html += f"\n🏷️ Estimated total for {default_quantity} contract(s): ${total_cost:.0f}"
            except Exception:
                # Don't let display failures block message sending
                pass
            
            # Create position-aware keyboard with position size constraint
            # Prefer IBKR-reported position size for the keyboard max limit
            try:
                if has_position:
                    mpd = processed_data.get('ibkr_position_size')
                    if mpd is not None:
                        try:
                            max_position = abs(int(mpd))
                        except Exception:
                            max_position = abs(int(position_size)) if position_size else None
                    else:
                        max_position = abs(int(position_size)) if position_size else None
                else:
                    max_position = None
            except Exception:
                max_position = abs(position_size) if has_position else None
            keyboard = self._create_position_aware_keyboard(message_id, has_position, default_quantity, max_position)
            # InlineKeyboardMarkup may not be available in some test envs; guard against that
            try:
                if callable(InlineKeyboardMarkup):
                    reply_markup = InlineKeyboardMarkup(keyboard)
                else:
                    reply_markup = None
            except Exception:
                reply_markup = None
            
            # Store message info for callback handling
            self.pending_messages[message_id] = {
                "alerter": alerter_name,
                "original_message": message,
                "ticker": ticker,
                "additional_info": additional_info,
                "processed_data": processed_data,  # Store the full processed data including contract details
                "timestamp": datetime.now().isoformat(),
                "response": None,
                "quantity": default_quantity,  # Store current quantity for both open and close orders
                "has_position": has_position,  # Store position status for keyboard updates
                "max_position": max_position  # Store max position size for close quantity limits
            }
            
            # Send the message
            # Use the discovered chat ID or fall back to instance chat_id
            final_chat_id = chat_id_to_use or self.chat_id

            if not final_chat_id:
                return {
                    "success": False,
                    "message": "Cannot send message: No chat ID available",
                    "message_id": message_id
                }

            # Ensure we have a bot instance. Try application.bot first, then construct one.
            if not self.bot:
                try:
                    if self.application and getattr(self.application, 'bot', None):
                        self.bot = self.application.bot
                        logger.debug("Using bot instance from application")
                    else:
                        try:
                            from telegram import Bot as TelegramBot
                            self.bot = TelegramBot(token=self.bot_token)
                            logger.debug("Created new Telegram Bot instance from token")
                        except Exception as be:
                            logger.error(f"Unable to create Telegram Bot instance: {be}")
                except Exception as e:
                    logger.error(f"Error initializing Telegram bot: {e}")

            if not self.bot:
                return {
                    "success": False,
                    "message": "Telegram bot instance not initialized",
                    "message_id": message_id
                }

            # Ensure bot has a send_message method
            if not self.bot or not getattr(self.bot, 'send_message', None):
                logger.error("Telegram bot instance not available or invalid when sending message")
                return {
                    "success": False,
                    "message": "Telegram bot instance not initialized or invalid",
                    "message_id": message_id
                }

            sent_message = await self.bot.send_message(
                chat_id=final_chat_id,
                text=alert_html,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            logger.info(f"Sent trading alert to Telegram. Message ID: {message_id}")
            
            return {
                "success": True,
                "message": "Trading alert sent successfully",
                "message_id": message_id,
                "telegram_message_id": sent_message.message_id,
                "chat_id": chat_id_to_use
            }
            
        except Exception as e:
            # Log full traceback to aid debugging intermittent NoneType/.get errors
            logger.exception("Error sending Telegram message")
            return {
                "success": False,
                "message": f"Failed to send Telegram message: {str(e)}",
                "error": str(e)
            }
    
    async def start_bot(self):
        """Start the Telegram bot to listen for callbacks"""
        try:
            logger.info("Starting Telegram bot...")
            # Ensure bot instance exists (try application.bot or construct one)
            if not self.bot:
                try:
                    if self.application and getattr(self.application, 'bot', None):
                        self.bot = self.application.bot
                        logger.debug("Using bot instance from application")
                    else:
                        try:
                            from telegram import Bot as TelegramBot
                            self.bot = TelegramBot(token=self.bot_token)
                            logger.debug("Created new Telegram Bot instance from token")
                        except Exception as be:
                            logger.error(f"Unable to create Telegram Bot instance: {be}")
                except Exception as e:
                    logger.error(f"Error initializing Telegram bot instance: {e}")

            # Delete any existing webhook first to avoid conflicts (if available)
            try:
                if self.bot and getattr(self.bot, 'delete_webhook', None):
                    await self.bot.delete_webhook()
                    logger.info("Webhook cleared")
            except Exception as dwe:
                logger.warning(f"Could not clear webhook: {dwe}")

            # Ensure an Application instance exists before calling application lifecycle
            if not self.application:
                try:
                    # Create a new Application and register callback handlers
                    from telegram.ext import Application, CallbackQueryHandler
                    self.application = Application.builder().token(self.bot_token).build()
                    # Register callback query handler that delegates to our dispatcher
                    self.application.add_handler(CallbackQueryHandler(self._on_callback))
                    logger.info("Created Telegram Application and registered callback handlers")
                except Exception as e:
                    logger.error(f"Unable to create Telegram Application: {e}")
                    return

            # Initialize and start the application
            await self.application.initialize()
            await self.application.start()
            
            # Start polling for updates with error handling
            logger.info("Starting bot polling...")
            
            # Use a more robust polling approach
            try:
                await self.application.updater.start_polling(
                    timeout=10,
                    read_timeout=20,
                    write_timeout=20,
                    connect_timeout=20
                )
                logger.info("Telegram bot started successfully and polling for updates")
            except Exception as polling_error:
                logger.warning(f"Standard polling failed: {polling_error}")
                logger.info("Falling back to manual update checking...")
                
                # Fallback to manual polling if the standard approach fails
                await self._manual_polling()
                
        except Exception as e:
            logger.error(f"Error starting Telegram bot: {e}")
    
    async def _manual_polling(self):
        """Manual polling fallback method"""
        last_update_id = 0
        logger.info("Starting manual polling loop...")
        
        while True:
            try:
                updates = await self.bot.get_updates(offset=last_update_id + 1, timeout=5)
                
                if updates:
                    logger.info(f"Received {len(updates)} update(s)")
                    
                    for update in updates:
                        # Process the update through the application handlers
                        await self.application.process_update(update)
                        last_update_id = max(last_update_id, update.update_id)
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error in manual polling: {e}")
                await asyncio.sleep(2)
    
    async def stop_bot(self):
        """Stop the Telegram bot"""
        try:
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Telegram bot stopped")
        except Exception as e:
            logger.error(f"Error stopping Telegram bot: {e}")
    
    def get_pending_messages(self) -> Dict[str, Dict[str, Any]]:
        """Get all pending messages awaiting responses"""
        return self.pending_messages.copy()
    
    def get_message_response(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get the response for a specific message ID"""
        message_info = self.pending_messages.get(message_id)
        if message_info:
            return message_info.get('response')
        return None
    
    def set_chat_id(self, chat_id: str):
        """Set the chat ID for sending messages"""
        self.chat_id = str(chat_id)
        logger.info(f"Chat ID set to: {self.chat_id}")
    
    def _get_midpoint_price(self, processed_data: dict) -> float:
        """Extract midpoint price from processed data"""
        try:
            # Try spread_info first (defensive: processed_data may contain None)
            spread_info = processed_data.get('spread_info') or {}
            bid = spread_info.get('bid')
            ask = spread_info.get('ask')

            if bid and ask and bid != 'N/A' and ask != 'N/A':
                bid_price = float(bid)
                ask_price = float(ask)
                return (bid_price + ask_price) / 2

            # Try several IBKR-derived locations for market data as fallback
            # 1) Top-level 'ibkr_market_data'
            ibkr_md = processed_data.get('ibkr_market_data')
            if ibkr_md and isinstance(ibkr_md, dict):
                bid = ibkr_md.get('bid')
                ask = ibkr_md.get('ask')
                if bid and ask and bid != 'N/A' and ask != 'N/A':
                    return (float(bid) + float(ask)) / 2

            # 2) Nested shape: processed_data['ibkr_contract_result'] may be either a contract_details dict or a wrapper
            ibkr_data = processed_data.get('ibkr_contract_result') or {}
            market_data = None
            try:
                if isinstance(ibkr_data, dict) and 'market_data' in ibkr_data:
                    market_data = ibkr_data.get('market_data')
                elif isinstance(ibkr_data, dict) and any(k in ibkr_data for k in ('bid', 'ask', 'last', 'open_interest')):
                    market_data = ibkr_data
                elif isinstance(ibkr_data, dict) and 'contract_details' in ibkr_data and isinstance(ibkr_data.get('contract_details'), dict):
                    cd = ibkr_data.get('contract_details')
                    market_data = cd.get('market_data') if isinstance(cd, dict) else None
            except Exception:
                market_data = None

            if market_data and isinstance(market_data, dict):
                bid = market_data.get('bid')
                ask = market_data.get('ask')
                if bid and ask and bid != 'N/A' and ask != 'N/A':
                    return (float(bid) + float(ask)) / 2

            # Fall back to last price if available
            last = None
            if isinstance(spread_info, dict):
                last = spread_info.get('last')
            if last and last != 'N/A':
                try:
                    return float(last)
                except Exception:
                    pass

            if market_data and isinstance(market_data, dict):
                last = market_data.get('last')
                if last and last != 'N/A':
                    try:
                        return float(last)
                    except Exception:
                        pass

        except (ValueError, TypeError):
            pass

        return 0.0
    
    def _create_position_aware_keyboard(self, message_id: str, has_position: bool, quantity: int = 1, max_position: int = None) -> list:
        """Create keyboard based on position status"""
        if has_position:
            # Has position: Show quantity selector for closing with max constraint
            return self._create_close_quantity_selector_keyboard(message_id, quantity, max_position)
        else:
            # No position: Show quantity selector with Open button
            return self._create_quantity_selector_keyboard(message_id, quantity)
    
    def _create_close_quantity_selector_keyboard(self, message_id: str, quantity: int, max_position: int) -> list:
        """Create keyboard with quantity adjustment buttons for closing positions"""
        # Row 1: Quantity adjusters for closing
        adjusters = []
        
        # Add negative buttons (disabled if quantity is 1)
        if quantity > 1:
            adjusters.extend([
                InlineKeyboardButton("-10", callback_data=f"qty_close:{message_id}:-10"),
                InlineKeyboardButton("-5", callback_data=f"qty_close:{message_id}:-5"),
                InlineKeyboardButton("-1", callback_data=f"qty_close:{message_id}:-1")
            ])
        else:
            # Add disabled buttons (show but don't respond)
            adjusters.extend([
                InlineKeyboardButton("⚫-10", callback_data=f"disabled"),
                InlineKeyboardButton("⚫-5", callback_data=f"disabled"),
                InlineKeyboardButton("⚫-1", callback_data=f"disabled")
            ])
        
        # Add positive buttons (may be limited by max_position)
        if max_position and quantity >= max_position:
            # At maximum, disable positive buttons
            adjusters.extend([
                InlineKeyboardButton("⚫+1", callback_data=f"disabled"),
                InlineKeyboardButton("⚫+5", callback_data=f"disabled"),
                InlineKeyboardButton("⚫+10", callback_data=f"disabled")
            ])
        else:
            # Normal positive buttons
            adjusters.extend([
                InlineKeyboardButton("+1", callback_data=f"qty_close:{message_id}:+1"),
                InlineKeyboardButton("+5", callback_data=f"qty_close:{message_id}:+5"),
                InlineKeyboardButton("+10", callback_data=f"qty_close:{message_id}:+10")
            ])
        
        # Row 2: Action buttons - Close + Place Trail
        action_button = [
            InlineKeyboardButton("🔴 Close Position", callback_data=f"execute_close:{message_id}"),
            InlineKeyboardButton("🟠 Place Trail", callback_data=f"execute_trail:{message_id}")
        ]
        
        return [adjusters, action_button]
    
    def _create_quantity_selector_keyboard(self, message_id: str, quantity: int) -> list:
        """Create keyboard with quantity adjustment buttons"""
        # Row 1: Quantity adjusters
        adjusters = []
        
        # Add negative buttons (disabled if quantity is 1)
        if quantity > 1:
            adjusters.extend([
                InlineKeyboardButton("-10", callback_data=f"qty:{message_id}:-10"),
                InlineKeyboardButton("-5", callback_data=f"qty:{message_id}:-5"),
                InlineKeyboardButton("-1", callback_data=f"qty:{message_id}:-1")
            ])
        else:
            # Add disabled buttons (show but don't respond)
            adjusters.extend([
                InlineKeyboardButton("⚫-10", callback_data=f"disabled"),
                InlineKeyboardButton("⚫-5", callback_data=f"disabled"),
                InlineKeyboardButton("⚫-1", callback_data=f"disabled")
            ])
        
        # Always add positive buttons
        adjusters.extend([
            InlineKeyboardButton("+1", callback_data=f"qty:{message_id}:+1"),
            InlineKeyboardButton("+5", callback_data=f"qty:{message_id}:+5"),
            InlineKeyboardButton("+10", callback_data=f"qty:{message_id}:+10")
        ])
        
        # Row 2: Action button
        action_button = [
            InlineKeyboardButton("🟢 Open Position", callback_data=f"execute_open:{message_id}")
        ]
        
        return [adjusters, action_button]
    
    async def _handle_quantity_adjustment(self, query, message_id: str, adjustment: int):
        """Handle quantity adjustment button press"""
        try:
            if message_id not in self.pending_messages:
                await query.edit_message_text("⚠️ This message has expired.")
                return

            message_info = self.pending_messages[message_id]
            current_quantity = message_info.get('quantity', 1)
            new_quantity = max(1, current_quantity + adjustment)  # Minimum 1 contract

            # Update stored quantity only
            self.pending_messages[message_id]['quantity'] = new_quantity

            # Use the unified alert regeneration logic to preserve all data
            alert_text = self._regenerate_alert_text_with_action(self.pending_messages[message_id], "OPEN", lightweight=True)

            # Create updated keyboard using position-aware logic
            has_position = message_info.get('has_position', False)
            max_position = message_info.get('max_position', None)
            keyboard = self._create_position_aware_keyboard(message_id, has_position, new_quantity, max_position)
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=alert_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

        except Exception as e:
            logger.error(f"Error handling quantity adjustment: {e}")
            await query.edit_message_text("❌ Error updating quantity.")
    
    async def _handle_close_quantity_adjustment(self, query, message_id: str, adjustment: int):
        """Handle close quantity adjustment button press with position size constraints"""
        try:
            if message_id not in self.pending_messages:
                await query.edit_message_text("⚠️ This message has expired.")
                return
            
            message_info = self.pending_messages[message_id]
            current_quantity = message_info.get('quantity', 1)
            max_position = message_info.get('max_position', current_quantity)
            
            # Calculate new quantity with constraints:
            # - Minimum 1 contract
            # - Maximum equal to position size
            proposed_quantity = current_quantity + adjustment
            
            if proposed_quantity < 1:
                new_quantity = 1
            elif max_position and proposed_quantity > max_position:
                new_quantity = max_position
            else:
                new_quantity = proposed_quantity
            
            # Update stored quantity
            self.pending_messages[message_id]['quantity'] = new_quantity
            
            # Get message details for reconstruction
            processed_data = message_info.get('processed_data', {})
            alerter_name = message_info.get('alerter', '')
            ticker = message_info.get('ticker', '')
            additional_info = message_info.get('additional_info', '')
            
            # Format contract display
            formatted_ticker, enhanced_additional_info = self._format_contract_display(
                ticker, additional_info, alerter_name, processed_data
            )
            
            # Recreate the message using the unified regeneration function so
            # contract details and IBKR P/L remain visible after quantity changes.
            # The quantity was already updated in `self.pending_messages` above.
            try:
                alert_text = self._regenerate_alert_text_with_action(self.pending_messages[message_id], "CLOSE", lightweight=True)
            except Exception as e:
                logger.error(f"Error regenerating alert text for close quantity: {e}")
                # Fall back to minimal display
                alert_text = f"📊 Position: {max_position} contract(s)\n💰 Close Quantity: {new_quantity} contract(s)"

            # Create updated keyboard using position-aware logic
            has_position = message_info.get('has_position', True)  # Should always be true for close
            keyboard = self._create_position_aware_keyboard(message_id, has_position, new_quantity, max_position)
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=alert_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            # print(f"📊 Updated close quantity for {message_id}: {current_quantity} → {new_quantity} (max: {max_position})")
            
        except Exception as e:
            logger.error(f"Error handling close quantity adjustment: {e}")

    async def _on_callback(self, update, context):
        """Telegram.Application CallbackQuery handler wrapper"""
        try:
            query = update.callback_query
            if not query:
                return
            await self.handle_button_callback(query)
        except Exception as e:
            logger.error(f"Error in callback wrapper: {e}")

    async def handle_button_callback(self, query):
        """Public method to handle a callback query-like object.

        Accepts objects with `.data` and `.message` and methods like
        `edit_message_text`. Tests can call this directly with a mock.
        """
        try:
            data = getattr(query, 'data', None)
            if not data:
                logger.debug("No callback data present")
                return

            # Parse callback formats: qty:<id>:<delta>, qty_close:<id>:<delta>, execute_close:<id>, execute_open:<id>
            parts = data.split(":")
            if not parts:
                return

            cmd = parts[0]
            if cmd == 'disabled':
                # Do nothing for disabled buttons
                try:
                    await query.answer("This button is disabled.")
                except Exception:
                    pass
                return

            if cmd in ('qty', 'qty_close') and len(parts) >= 3:
                message_id = parts[1]
                try:
                    adjustment = int(parts[2])
                except Exception:
                    adjustment = 0

                if cmd == 'qty':
                    await self._handle_quantity_adjustment(query, message_id, adjustment)
                else:
                    await self._handle_close_quantity_adjustment(query, message_id, adjustment)
                return

            # PLACE TRAIL button: execute_trail:<message_id>
            if cmd == 'execute_trail' and len(parts) >= 2:
                message_id = parts[1]
                message_info = self.pending_messages.get(message_id)
                if not message_info:
                    try:
                        await query.edit_message_text("⚠️ This message has expired.")
                    except Exception:
                        pass
                    return

                try:
                    # Directly place trailing limit order using dedicated handler
                    result = await self._process_place_trail(message_info)

                    # Regenerate alert text to include updated response/status
                    try:
                        alert_text = self._regenerate_alert_text_with_action(message_info, 'PLACE_TRAIL')
                    except Exception:
                        alert_text = f"✅ Action Selected: PLACE_TRAIL\n🔄 Processing trailing order..."

                    # Recreate keyboard (keep position-aware state)
                    has_position = message_info.get('has_position', False)
                    max_position = message_info.get('max_position', None)
                    current_qty = message_info.get('quantity', 1)
                    try:
                        keyboard = self._create_position_aware_keyboard(message_id, has_position, current_qty, max_position)
                        reply_markup = InlineKeyboardMarkup(keyboard)
                    except Exception:
                        reply_markup = None

                    try:
                        await query.edit_message_text(text=alert_text, reply_markup=reply_markup, parse_mode='HTML')
                    except Exception:
                        pass

                    # Store processing result if present
                    message_info['response'] = result
                except Exception as e:
                    logger.error(f"Error processing execute_trail for {message_id}: {e}")
                return

            if cmd in ('execute_close', 'execute_open') and len(parts) >= 2:
                message_id = parts[1]
                # Map execute_open -> OPEN, execute_close -> CLOSE and call order processing
                action = 'OPEN' if cmd == 'execute_open' else 'CLOSE'
                # Find stored message and process accordingly
                message_info = self.pending_messages.get(message_id)
                if not message_info:
                    try:
                        await query.edit_message_text("⚠️ This message has expired.")
                    except Exception:
                        pass
                    return

                # Call the appropriate processing method depending on alerter
                try:
                    # Prefer content-aware detection of demslayer-style alerts
                    if self._is_demspxslayer(message_info.get('alerter', ''), message_info):
                        # Preserve historical demslayer hook
                        result = await self._process_demslayer_order(action, message_info)
                    else:
                        # All other alerters (including Real Day Trading) use the
                        # generic trading action handler.
                        result = await self._process_trading_action(action, message_info)

                    # Regenerate alert text to include updated response/status
                    try:
                        alert_text = self._regenerate_alert_text_with_action(message_info, action)
                    except Exception:
                        alert_text = f"✅ Action Selected: {action}\n🔄 Processing {action.lower()} action..."

                    # Recreate keyboard (keep position-aware state)
                    has_position = message_info.get('has_position', False)
                    max_position = message_info.get('max_position', None)
                    current_qty = message_info.get('quantity', 1)
                    try:
                        keyboard = self._create_position_aware_keyboard(message_id, has_position, current_qty, max_position)
                        reply_markup = InlineKeyboardMarkup(keyboard)
                    except Exception:
                        reply_markup = None

                    try:
                        await query.edit_message_text(text=alert_text, reply_markup=reply_markup, parse_mode='HTML')
                    except Exception:
                        # Ignore edit failures (message may be expired or edited elsewhere)
                        pass

                    # Store processing result if present
                    message_info['response'] = result
                except Exception as e:
                    logger.error(f"Error processing execute action {action}: {e}")
                return

            logger.debug(f"Unhandled callback data: {data}")

        except Exception as e:
            logger.error(f"Error handling button callback: {e}")
    
    async def _process_trading_action(self, action: str, message_info: Dict[str, Any]):
        """
        Generic handler for processing trading actions (OPEN/CLOSE).

        This function intentionally keeps behavior minimal and safe: it records
        the action result onto the stored `message_info` and runs any
        post-processing (like contract removal) required after a CLOSE.

        More sophisticated behavior (actual IBKR order placement) can be
        implemented later and should live here.
        """
        logger.info(f"Processing trading action '{action}' for alerter: {message_info.get('alerter')}")
        processed_data = message_info.get('processed_data', {}) or {}

        # Default response (in case of early return)
        default_response = {'success': False, 'action': action, 'timestamp': datetime.now().isoformat(), 'note': 'No action taken'}

        try:
            # Only attempt real order placement for CLOSE actions for now
            if action and action.upper() == 'CLOSE':
                # Determine quantity to close
                try:
                    quantity = abs(int(message_info.get('quantity', 1)))
                except Exception:
                    quantity = 1

                # Determine position sign if available (positive => long => sell to close)
                position_size = processed_data.get('ibkr_position_size') or 0
                try:
                    position_size = int(position_size)
                except Exception:
                    position_size = position_size or 0

                side = 'SELL' if position_size >= 0 else 'BUY'

                # Try to resolve conid from processed_data
                conid = None
                try:
                    if processed_data.get('ibkr_contract_result') and processed_data['ibkr_contract_result'].get('contract_details'):
                        con = processed_data['ibkr_contract_result']['contract_details']
                        conid = con.get('conid') or con.get('contractId') or con.get('id')
                except Exception:
                    conid = None

                # If no conid found, try to resolve via many fallbacks (processed data, stored contract, alerter storage)
                if not conid:
                    try:
                        # Candidate symbol/contract info from processed_data and message_info
                        symbol = processed_data.get('ticker') or message_info.get('ticker') or None
                        # Look for various places the handler may have stored contract details
                        contract_details = None
                        # Priority 1: explicit ibkr_contract_result -> contract_details
                        try:
                            contract_details = processed_data.get('ibkr_contract_result', {}).get('contract_details') if processed_data.get('ibkr_contract_result') else None
                        except Exception:
                            contract_details = None

                        # Priority 2: top-level contract_details field
                        if not contract_details:
                            contract_details = processed_data.get('contract_details')

                        # Priority 3: handler-specific fields (demslayer / contract_info)
                        if not contract_details and processed_data.get('contract_info'):
                            # demslayer stores minimal contract_info; ask IBKR for details later
                            contract_details = processed_data.get('contract_info')

                        # Priority 4: stored contract persisted earlier
                        if not contract_details:
                            try:
                                stored = processed_data.get('stored_contract')
                                if not stored:
                                    from app.services.contract_storage import contract_storage
                                    stored = contract_storage.get_contract(message_info.get('alerter'))
                                if stored:
                                    # Normalize to contract_details-like dict
                                    contract_details = {
                                        'symbol': stored.get('symbol', symbol or ''),
                                        'strike': stored.get('strike'),
                                        'right': (stored.get('side') or '')[:1].upper() if stored.get('side') else None,
                                        'expiry': stored.get('expiry')
                                    }
                            except Exception:
                                contract_details = contract_details

                        # If we still don't have a full contract_details with strike/right/expiry,
                        # try to use alerter_stock_storage to find a stored contract for this alerter/ticker
                        if not contract_details and symbol:
                            try:
                                from app.services.alerter_stock_storage import alerter_stock_storage
                                summary = alerter_stock_storage.get_total_open_contracts(message_info.get('alerter'))
                                if isinstance(summary, dict) and 'contracts' in summary:
                                    matches = [c for c in summary['contracts'] if (c.get('ticker') or '').upper() == symbol.upper()]
                                    if matches:
                                        # Use the first matching stored contract
                                        first = matches[0]
                                        contract_details = {
                                            'symbol': first.get('symbol') or symbol,
                                            'strike': first.get('strike') or first.get('strike_price') or None,
                                            'right': (first.get('side') or '')[:1].upper() if first.get('side') else None,
                                            'expiry': first.get('expiry')
                                        }
                            except Exception:
                                pass

                        # If we have enough info (symbol + strike + right + expiry), ask IBKR for a canonical contract (conid)
                        if contract_details and contract_details.get('symbol') and contract_details.get('strike') and contract_details.get('right') and contract_details.get('expiry'):
                            try:
                                from app.services.ibkr_service import IBKRService
                                ibkr = IBKRService()
                                # Ensure strike is numeric
                                strike_val = contract_details.get('strike')
                                try:
                                    strike_val = float(str(strike_val).replace('$', ''))
                                except Exception:
                                    strike_val = contract_details.get('strike')
                                # Try to resolve conid from live IBKR positions first to avoid
                                # reliance on secdef/search (which can fail when the client
                                # session is not authenticated or when secdef returns a
                                # different conid). If we find a matching open position
                                # for the symbol, adopt its conid and skip the secdef lookup.
                                details = None
                                try:
                                    sym = contract_details.get('symbol') if contract_details else None
                                    if sym:
                                        from app.services.ibkr_service import IBKRService
                                        ibkr_tmp = IBKRService()
                                        for pos in ibkr_tmp.get_positions() or []:
                                            pos_symbol = (pos.get('contractDesc') or pos.get('symbol') or '')
                                            pos_conid = pos.get('conid') or pos.get('contractId') or pos.get('conId')
                                            try:
                                                pos_qty = abs(int(pos.get('position', 0)))
                                            except Exception:
                                                pos_qty = 0

                                            if pos_conid and pos_symbol and sym and str(sym).upper() in str(pos_symbol).upper() and pos_qty > 0:
                                                # Found a matching live position; use its conid
                                                details = {'symbol': sym, 'conid': pos_conid}
                                                logger.debug('Resolved conid from IBKR positions for %s -> %s', sym, pos_conid)
                                                break
                                except Exception:
                                    details = None

                                # If no live-position conid was found, fallback to secdef search
                                if not details:
                                    details = ibkr.get_option_contract_details(
                                        symbol=contract_details.get('symbol'),
                                        strike=strike_val,
                                        right=(contract_details.get('right') or '')[:1].upper(),
                                        expiry=contract_details.get('expiry')
                                    )
                                if details and isinstance(details, dict):
                                    conid = details.get('conid') or details.get('contractId') or details.get('id')
                                    # If we found details, store back into processed_data for future use
                                    try:
                                        processed_data.setdefault('ibkr_contract_result', {})
                                        processed_data['ibkr_contract_result']['contract_details'] = details
                                    except Exception:
                                        pass
                            except Exception:
                                # Swallow IBKR lookup failures here; we'll still send message
                                pass
                    except Exception:
                        conid = None
                # Final fallback: try to discover conid from current IBKR positions
                if not conid:
                    try:
                        from app.services.ibkr_service import IBKRService
                        ibkr = IBKRService()
                        for pos in ibkr.get_positions() or []:
                            pos_symbol = (pos.get('contractDesc') or pos.get('symbol') or '')
                            pos_conid = pos.get('conid') or pos.get('contractId') or pos.get('conId')
                            try:
                                pos_qty = abs(int(pos.get('position', 0)))
                            except Exception:
                                pos_qty = 0

                            if pos_conid and pos_symbol and symbol and symbol.upper() in pos_symbol.upper() and pos_qty > 0:
                                # Found a matching open position for this ticker; use its conid
                                conid = pos_conid
                                break
                    except Exception:
                        # Ignore failures in fallback discovery
                        pass
                
                if not conid:
                    # Cannot place order without a conid
                    msg = 'Unable to determine contract id (conid) for order placement.'
                    logger.warning(msg)
                    resp = {'success': False, 'error': msg}
                    message_info['response'] = resp
                    # Still run the removal check (simulated) for logic parity
                    await self._check_and_remove_contract_if_fully_closed(message_info, quantity)
                    return resp

                # Build a simple market order request
                try:
                    from ibind.client.ibkr_utils import OrderRequest
                    from app.services.ibkr_service import IBKRService

                    # Pre-order safety checks: ensure this conid corresponds to an
                    # existing open position and that the requested close quantity
                    # does not exceed the open position size. This prevents accidentally
                    # sending an order that IBKR will treat as opening a new position
                    # (which can cause large margin requirements).
                    ibkr = IBKRService()

                    # Try to find the exact position by conid first
                    position = None
                    try:
                        logger.debug('CLOSE action: conid_at_send=%s, attempting find_position_by_conid conid=%s', processed_data.get('conid_at_send'), conid)
                        position = ibkr.find_position_by_conid(int(conid)) if conid else None
                        logger.debug('CLOSE action find_position_by_conid result: %s', bool(position))
                    except Exception as e:
                        logger.debug('CLOSE action find_position_by_conid raised: %s', e)
                        position = None

                    # If not found by conid, try to match by symbol as a fallback
                    if not position:
                        symbol = processed_data.get('ticker') or message_info.get('ticker') or None
                        try:
                            all_pos = ibkr.get_positions() or []
                            logger.debug('CLOSE symbol-match fallback: symbol=%s, ibkr_positions_count=%d', symbol, len(all_pos))
                            for p in all_pos:
                                pos_symbol = (p.get('contractDesc') or p.get('symbol') or '')
                                pos_conid = p.get('conid') or p.get('contractId') or p.get('conId')
                                try:
                                    pos_qty = int(p.get('position', 0))
                                except Exception:
                                    pos_qty = 0

                                if pos_conid and pos_symbol and symbol and symbol.upper() in str(pos_symbol).upper() and abs(pos_qty) > 0:
                                    # Found a matching open position for this ticker; adopt its conid
                                    position = p
                                    conid = pos_conid
                                    break
                        except Exception:
                            position = None
                        # If still not found via IBKR, allow a safe fallback using processed_data
                        if not position:
                            logger.debug('CLOSE no position found via IBKR; checking processed_data fallbacks')
                            # If processed_data had ibkr_position_size > 0, trust it for closing
                            try:
                                ibkr_pos_size = int(processed_data.get('ibkr_position_size') or 0)
                            except Exception:
                                ibkr_pos_size = 0

                            if ibkr_pos_size and ibkr_pos_size != 0:
                                # construct a lightweight position object from processed_data
                                logger.debug('CLOSE using processed_data ibkr_position_size=%s as fallback', ibkr_pos_size)
                                fake_pos = {
                                    'conid': conid,
                                    'position': ibkr_pos_size,
                                    'mktPrice': None
                                }
                                # try to populate market price from processed_data spread_info or option_contracts
                                try:
                                    md = processed_data.get('spread_info') or processed_data.get('ibkr_market_data') or {}
                                    fake_pos['mktPrice'] = md.get('last') or md.get('currentPrice') or None
                                except Exception:
                                    fake_pos['mktPrice'] = None

                                position = fake_pos
                            else:
                                # Next fallback: inspect option_contracts array for matching conid or quantity
                                try:
                                    optcs = processed_data.get('option_contracts') or []
                                    for oc in optcs:
                                        oc_conid = oc.get('conid') or oc.get('contractId') or None
                                        oc_qty = oc.get('quantity') or oc.get('position') or 0
                                        if (oc_conid and str(oc_conid) == str(conid)) or (symbol and (oc.get('ticker') or '').upper() == symbol.upper() and oc_qty):
                                            logger.debug('CLOSE using option_contracts entry as fallback: %s', oc)
                                            position = {
                                                'conid': oc_conid or conid,
                                                'position': int(oc_qty),
                                                'mktPrice': oc.get('currentPrice') or oc.get('marketValue') or None
                                            }
                                            break
                                except Exception:
                                    position = None

                        if not position:
                            msg = 'No open position found for this contract; refusing to place order to avoid opening a new position.'
                            logger.warning(msg)
                            resp = {'success': False, 'error': msg}
                            message_info['response'] = resp
                            # Keep parity with existing behavior: still run removal check (simulated)
                            try:
                                await self._check_and_remove_contract_if_fully_closed(message_info, quantity)
                            except Exception:
                                pass
                            return resp

                    # If position was found, prefer using its conid when placing the order
                    try:
                        pos_conid = position.get('conid') or position.get('contractId') or position.get('conId')
                        if pos_conid:
                            if str(pos_conid) != str(conid):
                                logger.debug('CLOSE overriding conid from %s to position conid %s', conid, pos_conid)
                            conid = pos_conid
                    except Exception:
                        pass

                    # Ensure requested close quantity does not exceed open position
                    try:
                        open_qty = abs(int(position.get('position', 0)))
                    except Exception:
                        open_qty = 0

                    if quantity > open_qty:
                        msg = f"Requested close quantity {quantity} exceeds open position {open_qty}. Aborting to avoid opening a new position."
                        logger.warning(msg)
                        resp = {'success': False, 'error': msg}
                        message_info['response'] = resp
                        return resp

                    # Determine midpoint price and prefer a limit order at midpoint
                    midpoint_price = self._get_midpoint_price(processed_data)
                    try:
                        if midpoint_price and float(midpoint_price) > 0:
                                # Align price to instrument tick if available
                                try:
                                    # Hard-coded price alignment only (no IBKR minTick queries)
                                    from app.services.ibkr_service import IBKRService
                                    ibkr_local = IBKRService.__new__(IBKRService)

                                    # derive symbol when available to special-case SPX
                                    sym = None
                                    try:
                                        cd = processed_data.get('contract_details') or processed_data.get('contract_to_use') or processed_data.get('stored_contract')
                                        if isinstance(cd, dict):
                                            sym = cd.get('symbol')
                                    except Exception:
                                        sym = None

                                    dir_choice = 'nearest'
                                    try:
                                        if side and str(side).upper() == 'SELL':
                                            dir_choice = 'up'
                                        elif side and str(side).upper() == 'BUY':
                                            dir_choice = 'down'
                                    except Exception:
                                        dir_choice = 'nearest'

                                    try:
                                        aligned_price = float(midpoint_price)
                                        # SPX has a 0.05 min tick; all other instruments default to 0.01
                                        if sym and str(sym).upper() == 'SPX':
                                            aligned_price = float(ibkr_local.align_price_to_min_tick(float(midpoint_price), 0.05, direction=dir_choice))
                                        else:
                                            # Always align non-SPX to 0.01 per requested fallback
                                            try:
                                                aligned_price = float(ibkr_local.align_price_to_min_tick(float(midpoint_price), 0.01, direction=dir_choice))
                                            except Exception:
                                                # Fall back to raw midpoint on any error
                                                aligned_price = float(midpoint_price)
                                    except Exception:
                                        aligned_price = float(midpoint_price)
                                except Exception:
                                    aligned_price = float(midpoint_price)

                                # Prefer the conid from the matched IBKR position when placing the order
                                try:
                                    conid_to_use = int(position.get('conid')) if position and position.get('conid') else int(conid)
                                except Exception:
                                    conid_to_use = int(conid)

                                order_req = OrderRequest(
                                    conid=int(conid_to_use),
                                    side=side,
                                    quantity=quantity,
                                    order_type='LMT',
                                    price=aligned_price,
                                    acct_id=None,
                                    is_close=True,
                                )
                        else:
                            # Fallback to market order if no valid midpoint available
                                try:
                                    conid_to_use = int(position.get('conid')) if position and position.get('conid') else int(conid)
                                except Exception:
                                    conid_to_use = int(conid)

                                order_req = OrderRequest(
                                    conid=int(conid_to_use),
                                    side=side,
                                    quantity=quantity,
                                    order_type='MKT',
                                    acct_id=None,
                                    is_close=True,
                                )
                    except Exception:
                        # On any unexpected error computing midpoint, fall back to market
                        order_req = OrderRequest(
                            conid=int(conid),
                            side=side,
                            quantity=quantity,
                            order_type='MKT',
                            acct_id=None,
                            is_close=True,
                        )

                    logger.debug('CLOSE about to place order - conid_at_send=%s, conid_used=%s, order_req=%s', processed_data.get('conid_at_send'), conid, { 'conid': order_req.conid, 'side': order_req.side, 'quantity': order_req.quantity, 'order_type': order_req.order_type, 'price': getattr(order_req, 'price', None) })
                    placed = ibkr.place_order_with_confirmations(order_req)

                    # Normalize response
                    resp = placed if placed else {'success': True, 'detail': 'Order request sent (no response)'}
                    message_info['response'] = resp

                    # After a successful placement, run contract removal checks
                    try:
                        await self._check_and_remove_contract_if_fully_closed(message_info, quantity)
                    except Exception:
                        pass

                    return resp
                except Exception as e:
                    logger.error(f"Error placing IBKR order: {e}")
                    resp = {'success': False, 'error': str(e)}
                    message_info['response'] = resp
                    return resp

            else:
                # OPEN actions: attempt immediate order placement (market order)
                try:
                    # Determine requested quantity
                    try:
                        quantity = abs(int(message_info.get('quantity', 1)))
                    except Exception:
                        quantity = 1

                    processed_data = message_info.get('processed_data', {}) or {}

                    # Determine side.
                    # For stock alerts: LONG -> BUY, SHORT -> SELL.
                    # For option alerts: both LONG and SHORT actions represent opening
                    # an option position (buying calls for LONG, buying puts for SHORT).
                    # Therefore when instrument is an OPTION, map OPEN actions to BUY
                    # so we create opening BUY orders for options instead of SELL.
                    parsed_action = (processed_data.get('action') or '').upper()
                    instrument_type = (processed_data.get('instrument_type') or '').upper()

                    if instrument_type.startswith('OPTION'):
                        # Treat OPEN alerts for options as BUY (open position)
                        if parsed_action in ('LONG', 'SHORT'):
                            side = 'BUY'
                        else:
                            side = 'BUY'
                    else:
                        # Default stock behavior
                        if parsed_action == 'LONG':
                            side = 'BUY'
                        elif parsed_action == 'SHORT':
                            side = 'SELL'
                        else:
                            side = 'BUY'

                    # Resolve conid / contract details (reuse same fallbacks as CLOSE)
                    conid = None
                    contract_details = None
                    try:
                        if processed_data.get('ibkr_contract_result') and isinstance(processed_data.get('ibkr_contract_result'), dict):
                            ibkrc = processed_data.get('ibkr_contract_result')
                            if ibkrc.get('contract_details'):
                                contract_details = ibkrc.get('contract_details')
                            else:
                                contract_details = ibkrc
                        elif processed_data.get('contract_details'):
                            contract_details = processed_data.get('contract_details')
                        elif processed_data.get('stored_contract'):
                            contract_details = processed_data.get('stored_contract')

                        if contract_details and isinstance(contract_details, dict):
                            conid = contract_details.get('conid') or contract_details.get('contractId') or contract_details.get('id')
                    except Exception:
                        conid = None

                    # If no conid, try lookups similar to CLOSE path
                    if not conid:
                        try:
                            # Try stored contracts in alerter_stock_storage
                            symbol = processed_data.get('ticker') or message_info.get('ticker')
                            if symbol:
                                from app.services.alerter_stock_storage import alerter_stock_storage
                                summary = alerter_stock_storage.get_total_open_contracts(message_info.get('alerter'))
                                if isinstance(summary, dict) and 'contracts' in summary:
                                    matches = [c for c in summary['contracts'] if (c.get('ticker') or '').upper() == symbol.upper()]
                                    if matches:
                                        first = matches[0]
                                        contract_details = {
                                            'symbol': first.get('symbol') or symbol,
                                            'strike': first.get('strike') or first.get('strike_price') or None,
                                            'right': (first.get('side') or '')[:1].upper() if first.get('side') else None,
                                            'expiry': first.get('expiry')
                                        }
                        except Exception:
                            pass

                    # If still not resolved, try asking IBKR for canonical contract
                    if not conid and contract_details and contract_details.get('symbol') and contract_details.get('strike') and contract_details.get('right') and contract_details.get('expiry'):
                        try:
                            from app.services.ibkr_service import IBKRService
                            ibkr = IBKRService()
                            strike_val = contract_details.get('strike')
                            try:
                                strike_val = float(str(strike_val).replace('$', ''))
                            except Exception:
                                pass
                            details = ibkr.get_option_contract_details(
                                symbol=contract_details.get('symbol'),
                                strike=strike_val,
                                right=(contract_details.get('right') or '')[:1].upper(),
                                expiry=contract_details.get('expiry')
                            )
                            if details and isinstance(details, dict):
                                conid = details.get('conid') or details.get('contractId') or details.get('id')
                                # store details back
                                try:
                                    processed_data.setdefault('ibkr_contract_result', {})
                                    processed_data['ibkr_contract_result']['contract_details'] = details
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    if not conid:
                        msg = 'Unable to determine contract id (conid) for OPEN order placement.'
                        logger.warning(msg)
                        resp = {'success': False, 'error': msg}
                        message_info['response'] = resp
                        return resp

                    # Build and place market order
                    try:
                        from ibind.client.ibkr_utils import OrderRequest
                        from app.services.ibkr_service import IBKRService

                        ibkr = IBKRService()
                        # For OPEN orders: place the limit at the cheaper side of the spread
                        # to try to obtain a better entry (BUY -> bid, SELL -> ask).
                        # If bid/ask not available, fall back to midpoint. If no valid
                        # price, fall back to market order.
                        midpoint_price = self._get_midpoint_price(processed_data)
                        spread_info = processed_data.get('spread_info') or {}
                        bid = spread_info.get('bid')
                        ask = spread_info.get('ask')

                        preferred_price = None
                        try:
                            # Prefer raw bid/ask if both present
                            if bid and ask and bid != 'N/A' and ask != 'N/A':
                                try:
                                    if side and str(side).upper() == 'BUY':
                                        preferred_price = float(bid)
                                    elif side and str(side).upper() == 'SELL':
                                        preferred_price = float(ask)
                                except Exception:
                                    preferred_price = None

                            # Fallback to midpoint when no bid/ask available or parsing failed
                            if not preferred_price and midpoint_price and float(midpoint_price) > 0:
                                preferred_price = float(midpoint_price)
                        except Exception:
                            preferred_price = None

                        try:
                            if preferred_price and float(preferred_price) > 0:
                                try:
                                    # Hard-coded price alignment only (no IBKR minTick queries)
                                    from app.services.ibkr_service import IBKRService
                                    ibkr_local = IBKRService.__new__(IBKRService)

                                    # derive symbol when available to special-case SPX
                                    sym = None
                                    try:
                                        cd = processed_data.get('contract_details') or processed_data.get('contract_to_use') or processed_data.get('stored_contract')
                                        if isinstance(cd, dict):
                                            sym = cd.get('symbol')
                                    except Exception:
                                        sym = None

                                    # Align direction: BUY -> down (toward cheaper tick), SELL -> up
                                    dir_choice = 'nearest'
                                    try:
                                        if side and str(side).upper() == 'SELL':
                                            dir_choice = 'up'
                                        elif side and str(side).upper() == 'BUY':
                                            dir_choice = 'down'
                                    except Exception:
                                        dir_choice = 'nearest'

                                    try:
                                        aligned_price = float(preferred_price)
                                        # SPX has a 0.05 min tick; all other instruments default to 0.01
                                        if sym and str(sym).upper() == 'SPX':
                                            aligned_price = float(ibkr_local.align_price_to_min_tick(float(preferred_price), 0.05, direction=dir_choice))
                                        else:
                                            try:
                                                aligned_price = float(ibkr_local.align_price_to_min_tick(float(preferred_price), 0.01, direction=dir_choice))
                                            except Exception:
                                                aligned_price = float(preferred_price)
                                    except Exception:
                                        aligned_price = float(preferred_price)
                                except Exception:
                                    aligned_price = float(preferred_price)

                                order_req = OrderRequest(
                                    conid=int(conid),
                                    side=side,
                                    quantity=quantity,
                                    order_type='LMT',
                                    price=aligned_price,
                                    acct_id=None,
                                    is_close=False,
                                )
                            else:
                                # Fallback to market order if no valid price available
                                order_req = OrderRequest(
                                    conid=int(conid),
                                    side=side,
                                    quantity=quantity,
                                    order_type='MKT',
                                    acct_id=None,
                                    is_close=False,
                                )
                        except Exception:
                            order_req = OrderRequest(
                                conid=int(conid),
                                side=side,
                                quantity=quantity,
                                order_type='MKT',
                                acct_id=None,
                                is_close=False,
                            )

                        placed = ibkr.place_order_with_confirmations(order_req)
                        resp = placed if placed else {'success': True, 'detail': 'Order request sent (no response)'}
                        message_info['response'] = resp

                        # After placing, optionally run contract addition/removal checks if needed
                        return resp
                    except Exception as e:
                        logger.error(f'Error placing OPEN IBKR order: {e}')
                        resp = {'success': False, 'error': str(e)}
                        message_info['response'] = resp
                        return resp
                except Exception as e:
                    logger.error(f'Unexpected error processing OPEN action: {e}')
                    resp = {'success': False, 'error': str(e)}
                    message_info['response'] = resp
                    return resp

        except Exception as e:
            logger.error(f"Unexpected error in _process_trading_action: {e}")
            resp = {'success': False, 'error': str(e)}
            message_info['response'] = resp
            return resp

    async def _process_demslayer_order(self, action: str, message_info: Dict[str, Any]):
        """
        Backwards-compatible wrapper for DeMsLayer-style order processing.

        Historically tests and other code referenced `_process_demslayer_order`.
        Implement it to delegate to the generic `_process_trading_action` so
        real-day trading and other alerters won't fail when the dispatcher
        tries to call this method.
        """
        return await self._process_trading_action(action, message_info)

    async def _process_place_trail(self, message_info: Dict[str, Any]):
        """
        Place a trailing limit SELL order for long option positions using
        the following defaults provided by the user:
          - Order type: TRAILLMT
          - Trail: percentage up to 10% (we compute based on current price)
          - Limit offset: 0.01 (0.05 for SPX)
          - TIF: GTC
          - Reference price: last (use position mktPrice/currentPrice)
          - No confirmation step in Telegram UI (fire-and-forget similar to Close)

        Quantity and contract resolution reuse the same logic as _process_trading_action CLOSE path.
        """
        try:
            processed_data = message_info.get('processed_data', {}) or {}

            # Diagnostic: log incoming callback payload and key processed_data fields
            try:
                logger.debug(
                    'PLACE_TRAIL callback received - alerter=%s, keys=%s, ticker=%s, contract_details=%s, option_contracts_len=%s',
                    message_info.get('alerter'),
                    list(message_info.keys()),
                    processed_data.get('ticker') or message_info.get('ticker'),
                    bool(processed_data.get('contract_details') or processed_data.get('stored_contract')),
                    len(processed_data.get('option_contracts') or []),
                )
            except Exception:
                logger.debug('PLACE_TRAIL callback received (unable to serialize some fields)')

            # Determine quantity to sell (same as close)
            try:
                quantity = abs(int(message_info.get('quantity', 1)))
            except Exception:
                quantity = 1

            # Resolve conid (reuse lookup logic from CLOSE)
            conid = None
            try:
                if processed_data.get('ibkr_contract_result') and processed_data['ibkr_contract_result'].get('contract_details'):
                    con = processed_data['ibkr_contract_result']['contract_details']
                    conid = con.get('conid') or con.get('contractId') or con.get('id')
            except Exception:
                conid = None

            # Fallbacks: stored contract, alerter storage, IBKR positions
            if not conid:
                # try stored_contract
                contract_details = processed_data.get('contract_details') or processed_data.get('stored_contract') or processed_data.get('contract_info')
                if contract_details and isinstance(contract_details, dict):
                    conid = contract_details.get('conid') or contract_details.get('contractId') or contract_details.get('id')

            if not conid:
                # try alerter_stock_storage
                try:
                    symbol = processed_data.get('ticker') or message_info.get('ticker')
                    if symbol:
                        from app.services.alerter_stock_storage import alerter_stock_storage
                        summary = alerter_stock_storage.get_total_open_contracts(message_info.get('alerter'))
                        if isinstance(summary, dict) and 'contracts' in summary:
                            matches = [c for c in summary['contracts'] if (c.get('ticker') or '').upper() == symbol.upper()]
                            if matches:
                                first = matches[0]
                                conid = first.get('conid') or first.get('contractId') or first.get('id')
                except Exception:
                    pass

            if not conid:
                # last-resort: find by open positions
                try:
                    from app.services.ibkr_service import IBKRService
                    ibkr = IBKRService()
                    for pos in ibkr.get_positions() or []:
                        pos_conid = pos.get('conid') or pos.get('contractId') or pos.get('conId')
                        pos_symbol = (pos.get('contractDesc') or pos.get('symbol') or '')
                        pos_qty = abs(int(pos.get('position', 0)))
                        sym = processed_data.get('ticker') or message_info.get('ticker')
                        if pos_qty > 0 and sym and sym.upper() in str(pos_symbol).upper():
                            conid = pos_conid
                            break
                except Exception:
                    pass

            if not conid:
                msg = 'Unable to determine contract id (conid) for PLACE_TRAIL order.'
                logger.warning(msg)
                resp = {'success': False, 'error': msg}
                message_info['response'] = resp
                logger.debug('PLACE_TRAIL giving up conid resolution; processed_data keys: %s', list(processed_data.keys()))
                return resp

            # Ensure we have an open position and that quantity does not exceed it
            try:
                from app.services.ibkr_service import IBKRService
                ibkr = IBKRService()
                position = ibkr.find_position_by_conid(int(conid)) if conid else None
            except Exception:
                position = None

            logger.debug('PLACE_TRAIL: conid_at_send=%s, attempted find_position_by_conid(%s) -> %s', processed_data.get('conid_at_send'), conid, bool(position))

            if not position:
                # fallback to matching by symbol
                try:
                    # Ensure ibkr instance exists for fallback
                    try:
                        ibkr
                    except NameError:
                        ibkr = IBKRService()

                    symbol = processed_data.get('ticker') or message_info.get('ticker')
                    all_positions = ibkr.get_positions() or []
                    logger.debug('PLACE_TRAIL symbol-match fallback: symbol=%s, positions_count=%d', symbol, len(all_positions))
                    for p in all_positions:
                        pos_symbol = (p.get('contractDesc') or p.get('symbol') or '')
                        pos_conid = p.get('conid') or p.get('contractId') or p.get('conId')
                        pos_qty = abs(int(p.get('position', 0)))
                        if pos_qty > 0 and symbol and symbol.upper() in str(pos_symbol).upper():
                            position = p
                            conid = pos_conid
                            break
                except Exception:
                    pass

            if not position:
                msg = 'No open position found for this contract; refusing to place trail order.'
                logger.warning(msg)
                resp = {'success': False, 'error': msg}
                message_info['response'] = resp
                # Extra diagnostic: dump current IBKR positions and processed_data summary
                try:
                    from app.services.ibkr_service import IBKRService
                    ib = IBKRService()
                    positions = ib.get_positions() or []
                    logger.debug('PLACE_TRAIL no position found - ibkr_positions_count=%d; sample_positions=%s', len(positions), [
                        { 'conid': p.get('conid') or p.get('contractId') or p.get('conId'), 'contractDesc': p.get('contractDesc') or p.get('symbol'), 'position': p.get('position') } for p in positions[:10]
                    ])
                except Exception:
                    logger.debug('PLACE_TRAIL no position found and failed to list IBKR positions')
                return resp

            try:
                # Prefer using the position's conid when placing trailing orders
                try:
                    pos_conid = position.get('conid') or position.get('contractId') or position.get('conId')
                    if pos_conid:
                        if str(pos_conid) != str(conid):
                            logger.debug('PLACE_TRAIL overriding conid from %s to matched position conid %s', conid, pos_conid)
                        conid = pos_conid
                except Exception:
                    pass

                open_qty = abs(int(position.get('position', 0)))
            except Exception:
                open_qty = 0

            if quantity > open_qty:
                msg = f"Requested trail quantity {quantity} exceeds open position {open_qty}. Aborting."
                logger.warning(msg)
                resp = {'success': False, 'error': msg}
                message_info['response'] = resp
                return resp

            # Determine reference price: use market price / last
            curr_price = None
            try:
                curr_price = position.get('mktPrice') or position.get('mkt_price') or position.get('currentPrice') or position.get('last')
                curr_price = float(curr_price) if curr_price is not None else None
            except Exception:
                curr_price = None

            if not curr_price or curr_price <= 0:
                # try processed_data market data
                try:
                    md = processed_data.get('spread_info') or processed_data.get('ibkr_market_data') or processed_data.get('market_data')
                    if md and isinstance(md, dict):
                        curr_price = md.get('last') or md.get('mktPrice') or md.get('currentPrice')
                        curr_price = float(curr_price) if curr_price is not None else None
                except Exception:
                    curr_price = None

            if not curr_price or curr_price <= 0:
                msg = 'Unable to determine a valid reference price for trailing order.'
                logger.warning(msg)
                resp = {'success': False, 'error': msg}
                message_info['response'] = resp
                return resp

            # Compute trailing amount using percentage up to 10% (user requested percent 10%)
            # We'll compute trailing_amount = min(10% * price, ensure stop not below entry price if entry exists)
            trail_pct = 0.10  # 10%
            trailing_amount = round(float(curr_price) * trail_pct, 4)

            # Ensure trailing_amount at least minimal cent precision
            if trailing_amount <= 0:
                trailing_amount = 0.01

            # Limit offset: default 0.01, but use 0.05 for SPX-like symbols
            limit_offset = 0.01
            try:
                sym = None
                cd = processed_data.get('contract_details') or processed_data.get('stored_contract')
                if isinstance(cd, dict):
                    sym = cd.get('symbol')
                if sym and str(sym).upper() == 'SPX':
                    limit_offset = 0.05
            except Exception:
                limit_offset = 0.01

            # If there is an entry price in processed_data, ensure the trailing stop won't go below it
            try:
                entry_price = processed_data.get('entry_price') or processed_data.get('ibkr_avg_price') or processed_data.get('avgPrice')
                if entry_price is not None:
                    try:
                        entry_price = float(entry_price)
                        # resulting stop = curr_price - trailing_amount; ensure not below entry
                        resulting_stop = float(curr_price) - float(trailing_amount)
                        if resulting_stop < entry_price:
                            # reduce trailing_amount so stop equals entry_price
                            trailing_amount = round(float(curr_price) - float(entry_price), 4)
                            if trailing_amount <= 0:
                                trailing_amount = 0.01
                    except Exception:
                        pass
            except Exception:
                pass

            # Finally call IBKR service place_trailing_limit_order
            try:
                from app.services.ibkr_service import IBKRService
                ibkr = IBKRService()
                logger.debug('PLACE_TRAIL placing order - conid=%s, qty=%s, curr_price=%s, trailing_amount=%s, limit_offset=%s', conid, quantity, curr_price, trailing_amount, limit_offset)
                placed = ibkr.place_trailing_limit_order(int(conid), int(quantity), trailing_amount, limit_offset=limit_offset)
                resp = placed if placed else {'success': True, 'detail': 'Trailing limit order sent (no response)'}
                message_info['response'] = resp

                # After placing, run removal check like CLOSE
                try:
                    await self._check_and_remove_contract_if_fully_closed(message_info, quantity)
                except Exception:
                    pass

                return resp
            except Exception as e:
                logger.error(f"Error placing trailing limit order: {e}")
                resp = {'success': False, 'error': str(e)}
                message_info['response'] = resp
                return resp

        except Exception as e:
            logger.error(f"Unexpected error in _process_place_trail: {e}")
            resp = {'success': False, 'error': str(e)}
            message_info['response'] = resp
            return resp
    
    async def _check_and_remove_contract_if_fully_closed(self, message_info: Dict[str, Any], closed_quantity: int):
        """
        Check if all positions in a contract are closed and remove contract from storage if so.
        
        Args:
            message_info: Message information containing alerter and processed data
            closed_quantity: Number of contracts that were just closed
        """
        try:
            alerter_name = message_info.get('alerter')
            if not alerter_name:
                return

            processed_data = message_info.get('processed_data', {}) or {}

            # Determine original open quantity (prefer processed_data fields)
            open_qty = 0
            try:
                # 1) IBKR direct position size
                ibkr_pos = processed_data.get('ibkr_position_size')
                if ibkr_pos is not None:
                    try:
                        open_qty = abs(int(ibkr_pos))
                    except Exception:
                        open_qty = abs(float(ibkr_pos)) if isinstance(ibkr_pos, (int, float, str)) and str(ibkr_pos).replace('.', '', 1).isdigit() else 0
                # 2) spx_position or generic position dict
                if open_qty == 0:
                    pos_data = processed_data.get('spx_position') or processed_data.get('position')
                    if isinstance(pos_data, dict):
                        try:
                            open_qty = abs(int(pos_data.get('position', 0)))
                        except Exception:
                            open_qty = abs(float(pos_data.get('position', 0))) if isinstance(pos_data.get('position', 0), (int, float, str)) and str(pos_data.get('position', 0)).replace('.', '', 1).isdigit() else 0
                # 3) message_info max_position (set when creating keyboard)
                if open_qty == 0:
                    try:
                        mp = message_info.get('max_position')
                        if mp is not None:
                            open_qty = abs(int(mp))
                    except Exception:
                        pass
                # 4) Fallback: try to query IBKR for current position matching ticker/contract
                if open_qty == 0:
                    try:
                        from app.services.ibkr_service import IBKRService
                        ibkr = IBKRService()
                        symbol = processed_data.get('ticker') or message_info.get('ticker') or None
                        for p in (ibkr.get_formatted_positions() or []) + (ibkr.get_positions() or []):
                            pos_sym = (p.get('symbol') or p.get('contractDesc') or '').upper()
                            try:
                                pos_qty = abs(int(p.get('position', 0)))
                            except Exception:
                                pos_qty = 0
                            if symbol and symbol.upper() in pos_sym and pos_qty > 0:
                                open_qty = pos_qty
                                break
                    except Exception:
                        pass
            except Exception:
                open_qty = 0

            # If we don't know the open quantity, we cannot safely decide — abort
            if open_qty <= 0:
                logger.debug(f"_check_and_remove_contract_if_fully_closed: unknown open_qty for {alerter_name}, skipping removal check")
                return

            # If the closed quantity equals or exceeds the open quantity, remove storage
            if int(closed_quantity) >= int(open_qty):
                logger.info(f"All contracts closed ({closed_quantity}/{open_qty}) for {alerter_name}; removing stored alert/contract")
                # For demslayer-style alerters, remove contract_storage entry
                try:
                    if self._is_demspxslayer(alerter_name, processed_data, title=message_info.get('title',''), message=message_info.get('original_message','')):
                        from app.services.contract_storage import contract_storage
                        try:
                            # Try removing by provided key first, then fallback to legacy key
                            success = False
                            try:
                                success = contract_storage.remove_contract(alerter_name)
                            except Exception:
                                success = False
                            if not success:
                                try:
                                    success = contract_storage.remove_contract('demslayer-spx-alerts')
                                except Exception:
                                    success = False
                        except Exception:
                            success = False
                        if success:
                            logger.info(f"Removed demslayer stored contract for {alerter_name}")
                        else:
                            logger.warning(f"Failed to remove demslayer stored contract for {alerter_name}")
                        return
                except Exception:
                    pass

                # Otherwise, attempt to remove from alerter_stock_storage by ticker
                try:
                    from app.services.alerter_stock_storage import alerter_stock_storage
                    ticker = (processed_data.get('ticker') or message_info.get('ticker') or '')
                    # Normalize ticker if it contains surrounding text
                    if ticker and isinstance(ticker, str):
                        ticker_key = ticker.strip().split()[0].upper()
                    else:
                        ticker_key = None
                    if ticker_key:
                        try:
                            removed = alerter_stock_storage.remove_stock_alert(alerter_name, ticker_key)
                        except Exception:
                            removed = False
                        if removed:
                            logger.info(f"Removed stock alert for {alerter_name}/{ticker_key}")
                        else:
                            logger.warning(f"Could not remove stock alert for {alerter_name}/{ticker_key}")
                except Exception:
                    logger.debug(f"No alerter_stock_storage available to remove alert for {alerter_name}")
            else:
                logger.info(f"Position partially closed ({closed_quantity}/{open_qty}) for {alerter_name}; not removing stored alert")

        except Exception as e:
            logger.error(f"Error checking position for contract removal: {e}")
            print(f"❌ Error checking position for contract removal: {e}")
    
    def _regenerate_alert_text_with_action(self, message_info: Dict[str, Any], action: str, lightweight: bool = False) -> str:
        """
        Rebuild the alert HTML for edits so that messages keep the same formatting
        as send_trading_alert. Returns an HTML string.
        """
        from html import escape as _html_escape

        def esc(x):
            return _html_escape(str(x)) if x is not None else ""

        try:
            alerter = message_info.get('alerter', '')
            original_message = message_info.get('original_message', '')
            ticker = message_info.get('ticker', '')
            additional_info = message_info.get('additional_info', '')
            processed_data = message_info.get('processed_data') or {}

            # Find message id key if available
            message_id = next((k for k, v in self.pending_messages.items() if v is message_info), '')

            # If processed_data contains option_contracts, prefer a compact
            # contract display built directly from the first contract row so
            # the Contract line always shows 'SYMBOL - 640C - 9/16' (when
            # expiry available), and persists across add/decrease button edits.
            def _compact_from_contract_row(c: dict) -> str:
                try:
                    import re

                    def _normalize_expiry_token(s: str) -> str | None:
                        if not s:
                            return None
                        s = str(s).strip()
                        # M/D or M/D/YYYY
                        if '/' in s:
                            try:
                                parts = [p for p in s.split('/') if p]
                                m = int(parts[0]); d = int(parts[1])
                                return f"{m}/{d}"
                            except Exception:
                                return None
                        # Prefer 6-digit YYMMDD tokens (common in option symbols like 250915)
                        if re.fullmatch(r"\d{6}", s):
                            try:
                                yy = int(s[0:2]); mm = int(s[2:4]); dd = int(s[4:6])
                                if 1 <= mm <= 12 and 1 <= dd <= 31:
                                    return f"{mm}/{dd}"
                            except Exception:
                                return None
                        # Accept 8-digit YYYYMMDD only when plausible (valid year/month/day)
                        if re.fullmatch(r"\d{8}", s):
                            try:
                                year = int(s[0:4]); mm = int(s[4:6]); dd = int(s[6:8])
                                if 1970 <= year <= 2099 and 1 <= mm <= 12 and 1 <= dd <= 31:
                                    return f"{mm}/{dd}"
                            except Exception:
                                return None
                        return None

                    def _extract_expiry_from_symbol(sym: str) -> str | None:
                        if not sym:
                            return None
                        # Look for YYYYMMDD or YYMMDD tokens
                        m = re.search(r"(\d{8})", sym)
                        # Try 6-digit YYMMDD first
                        m6 = re.search(r"(\d{6})", sym)
                        if m6:
                            nx = _normalize_expiry_token(m6.group(1))
                            if nx:
                                return nx
                        # Then try 8-digit YYYYMMDD
                        m8 = re.search(r"(\d{8})", sym)
                        if m8:
                            nx = _normalize_expiry_token(m8.group(1))
                            if nx:
                                return nx
                        # Month name like SEP2025 or SEP25
                        m = re.search(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Za-z]*\s*(\d{2,4})\b", sym, re.IGNORECASE)
                        if m:
                            mon = m.group(1).upper()[:3]
                            mm_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                            mm = mm_map.get(mon)
                            if mm:
                                # If day present in match group 2 (e.g., SEP15), return m/d else just month
                                try:
                                    dd = int(m.group(2)) if m.group(2) and len(m.group(2)) <= 2 else None
                                    if dd and 1 <= dd <= 31:
                                        return f"{mm}/{dd}"
                                except Exception:
                                    pass
                                return str(mm)
                        return None

                    sym = (c.get('ticker') or c.get('symbol') or '').strip()
                    strike = c.get('strike')
                    side = (c.get('side') or c.get('right') or '')
                    right = (side[0].upper() if isinstance(side, str) and side else '')
                    # format strike
                    strike_disp = None
                    if strike is not None:
                        try:
                            sf = float(strike)
                            strike_disp = str(int(sf)) if sf.is_integer() else str(strike)
                        except Exception:
                            strike_disp = str(strike)

                    parts = [s for s in [sym.upper() if sym else None, (f"{strike_disp}{right}" if strike_disp else None)] if s]

                    # expiry resolution: prefer explicit expiry field, then symbol parsing
                    exp = c.get('expiry') or (c.get('contract_details') or {}).get('expiry')
                    formatted_exp = None
                    if exp:
                        formatted_exp = _normalize_expiry_token(exp)
                    if not formatted_exp:
                        # try to extract from symbol text (e.g., 'SEP2025' or embedded '250915')
                        formatted_exp = _extract_expiry_from_symbol(str(c.get('symbol') or ''))
                    if formatted_exp:
                        parts.append(str(formatted_exp))
                    return ' - '.join(parts)
                except Exception:
                    return ''

            # Prefer option_contracts-derived display when available
            formatted_ticker = ''
            enhanced_info = ''
            try:
                if processed_data and isinstance(processed_data, dict) and processed_data.get('option_contracts'):
                    first = processed_data.get('option_contracts')[0]
                    formatted_ticker = _compact_from_contract_row(first) or ''
                    # still compute enhanced_info via existing formatter
                    try:
                        _, enhanced_info = self._format_contract_display(ticker, additional_info, alerter, processed_data)
                    except Exception:
                        enhanced_info = additional_info or ''
                else:
                    # derive compact contract display from first option_contracts row when possible
                    def _compact_from_contract_row(c: dict) -> str:
                        try:
                            import re

                            def _normalize_expiry_token(s: str) -> str | None:
                                if not s:
                                    return None
                                s = str(s).strip()
                                if '/' in s:
                                    try:
                                        parts = [p for p in s.split('/') if p]
                                        m = int(parts[0]); d = int(parts[1])
                                        return f"{m}/{d}"
                                    except Exception:
                                        return s
                                if re.fullmatch(r"\d{8}", s):
                                    try:
                                        m = int(s[4:6]); d = int(s[6:8])
                                        return f"{m}/{d}"
                                    except Exception:
                                        return s
                                if re.fullmatch(r"\d{6}", s):
                                    try:
                                        m = int(s[2:4]); d = int(s[4:6])
                                        return f"{m}/{d}"
                                    except Exception:
                                        return s
                                return s

                            def _extract_expiry_from_symbol(sym: str) -> str | None:
                                if not sym:
                                    return None
                                m = re.search(r"(\d{8})", sym)
                                if m:
                                    return _normalize_expiry_token(m.group(1))
                                m = re.search(r"(\d{6})", sym)
                                if m:
                                    return _normalize_expiry_token(m.group(1))
                                m = re.search(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Za-z]*\s*(\d{2,4})\b", sym, re.IGNORECASE)
                                if m:
                                    mon = m.group(1).upper()[:3]
                                    mm_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                                    mm = mm_map.get(mon)
                                    if mm:
                                        return str(mm)
                                return None

                            sym = (c.get('ticker') or c.get('symbol') or '').strip()
                            strike = c.get('strike')
                            side = (c.get('side') or c.get('right') or '')
                            right = (side[0].upper() if isinstance(side, str) and side else '')
                            strike_disp = None
                            if strike is not None:
                                try:
                                    sf = float(strike)
                                    strike_disp = str(int(sf)) if sf.is_integer() else str(strike)
                                except Exception:
                                    strike_disp = str(strike)

                            parts = [s for s in [sym.upper() if sym else None, (f"{strike_disp}{right}" if strike_disp else None)] if s]
                            exp = c.get('expiry') or (c.get('contract_details') or {}).get('expiry')
                            formatted_exp = None
                            if exp:
                                formatted_exp = _normalize_expiry_token(exp)
                            if not formatted_exp:
                                formatted_exp = _extract_expiry_from_symbol(str(c.get('symbol') or ''))
                            if formatted_exp:
                                parts.append(str(formatted_exp))
                            return ' - '.join(parts)
                        except Exception:
                            return ''

                    formatted_ticker = ''
                    enhanced_info = ''
                    try:
                        if processed_data and isinstance(processed_data, dict) and processed_data.get('option_contracts'):
                            first = processed_data.get('option_contracts')[0]
                            formatted_ticker = _compact_from_contract_row(first) or ''
                            try:
                                _, enhanced_info = self._format_contract_display(ticker, additional_info, alerter, processed_data)
                            except Exception:
                                enhanced_info = additional_info or ''
                        else:
                            formatted_ticker, enhanced_info = self._format_contract_display(ticker, additional_info, alerter, processed_data)
                    except Exception:
                        formatted_ticker, enhanced_info = self._format_contract_display(ticker, additional_info, alerter, processed_data)
            except Exception:
                formatted_ticker, enhanced_info = self._format_contract_display(
                    ticker, additional_info, alerter, processed_data
                )

            alert_html = f"🚨 <b>Trading Alert</b>\n\n"
            alert_html += f"🎯 <b>Alerter:</b> {esc(alerter)}\n"
            # Show contract line when we have a formatted display (don't rely
            # on the original `ticker` field which may be empty for some
            # alerters). This ensures the contract remains visible after
            # button-press regenerations.
            if formatted_ticker:
                alert_html += f"📊 <b>Contract:</b> <code>{esc(formatted_ticker)}</code>\n"
            alert_html += f"💬 <b>Message:</b> {esc(original_message)}\n"

            if enhanced_info:
                if self._is_demspxslayer(alerter, processed_data):
                    alert_html += f"\n{esc(enhanced_info)}\n"
                else:
                    alert_html += f"ℹ️ <i>Details:</i> {esc(enhanced_info)}\n"

            # Include permissive IBKR Contract Lookup + market data if present
            try:
                cd = (
                    processed_data.get('contract_details')
                    or processed_data.get('contract_to_use')
                    or processed_data.get('stored_contract')
                    or processed_data.get('ibkr_contract_result')
                    or processed_data.get('ibkr_contract')
                    or processed_data.get('contract')
                ) if processed_data else None
                md = (
                    processed_data.get('spread_info')
                    or processed_data.get('ibkr_market_data')
                    or processed_data.get('market_data')
                    or (processed_data.get('ibkr_contract_result') or {}).get('market_data')
                    or (processed_data.get('contract_details') or {}).get('market_data')
                ) if processed_data else None

                if cd or md:
                    alert_html += "\n\n🔍 <b>IBKR Contract Lookup:</b>\n"
                    try:
                        symbol = cd.get('symbol') if isinstance(cd, dict) else None
                        strike = cd.get('strike') if isinstance(cd, dict) else None
                        right = cd.get('right') if isinstance(cd, dict) else (cd.get('side') if isinstance(cd, dict) else None)
                        expiry = cd.get('expiry') if isinstance(cd, dict) else None
                        if symbol and strike and right:
                            formatted_expiry = expiry
                            if isinstance(expiry, str) and len(expiry) == 8:
                                try:
                                    m = int(expiry[4:6]); d = int(expiry[6:8])
                                    formatted_expiry = f"{m}/{d}"
                                except Exception:
                                    pass
                            alert_html += f"   📜 <b>Symbol:</b> {esc(symbol)} {esc(str(strike))}{esc(str(right))} {esc(formatted_expiry)}\n"
                    except Exception:
                        pass

                    if md and isinstance(md, dict):
                        bid = md.get('bid', 'N/A')
                        ask = md.get('ask', 'N/A')
                        last = md.get('last', 'N/A')
                        oi = md.get('open_interest') or md.get('openInterest')
                        alert_html += f"   💹 <i>Market Data:</i>\n"
                        if bid != 'N/A' and ask != 'N/A':
                            alert_html += f"      💰 Bid ${esc(bid)} | ${esc(ask)} Ask 💸 \n"
                        else:
                            if bid != 'N/A':
                                alert_html += f"      💰 Bid: ${esc(bid)}\n"
                            if ask != 'N/A':
                                alert_html += f"      💸 Ask: ${esc(ask)}\n"
                        if last != 'N/A':
                            last_line = f"      📈 Last: ${esc(last)}"
                            if oi:
                                last_line += f" | OI: {esc(oi)}"
                            alert_html += last_line + "\n"
            except Exception:
                # Best-effort; don't block message edits
                logger.debug("Failed to append IBKR Contract Lookup in regeneration")

            alert_html += f"\n🆔 ID: <code>{esc(message_id)}</code>"

            # IBKR P/L summary (mandatory if present)
            try:
                ibkr_unreal = processed_data.get('ibkr_unrealized_pnl')
                ibkr_real = processed_data.get('ibkr_realized_pnl')
                ibkr_avg = processed_data.get('ibkr_avg_price')
                ibkr_curr = processed_data.get('ibkr_current_price')
                ibkr_mv = processed_data.get('ibkr_market_value')
                ibkr_pos = processed_data.get('ibkr_position_size')
                pl_lines = []
                if ibkr_pos is not None:
                    try:
                        pl_lines.append(f"📊 Position (IBKR): {int(ibkr_pos)}")
                    except Exception:
                        pl_lines.append(f"📊 Position (IBKR): {ibkr_pos}")
                if ibkr_avg is not None:
                    pl_lines.append(f"Avg: ${ibkr_avg}")
                if ibkr_curr is not None:
                    pl_lines.append(f"Current: ${ibkr_curr}")
                if ibkr_mv is not None:
                    pl_lines.append(f"Market Value: ${ibkr_mv}")
                # Unified coloring: green = positive, red = negative, neutral circle otherwise
                if ibkr_unreal is not None:
                    if ibkr_unreal > 0:
                        pl_lines.append(f"🟢 Unrealized P/L: +${abs(ibkr_unreal):,.2f}")
                    elif ibkr_unreal < 0:
                        pl_lines.append(f"🔴 Unrealized P/L: -${abs(ibkr_unreal):,.2f}")
                    else:
                        pl_lines.append(f"⚪ Unrealized P/L: $0.00")
                if ibkr_real is not None:
                    if ibkr_real > 0:
                        pl_lines.append(f"🟢 Realized P/L: +${abs(ibkr_real):,.2f}")
                    elif ibkr_real < 0:
                        pl_lines.append(f"🔴 Realized P/L: -${abs(ibkr_real):,.2f}")
                    else:
                        pl_lines.append(f"⚪ Realized P/L: $0.00")
                if pl_lines:
                    alert_html += "\n<b>💰 IBKR Position Summary:</b>\n<pre>"
                    for line in pl_lines:
                        alert_html += esc(line) + "\n"
                    alert_html += "</pre>"
            except Exception:
                logger.debug("Error building IBKR P/L display in regeneration")

            # Position and quantity info
            # Prefer a dynamic computation of has_position derived from processed_data
            # so the UI shows a close panel when option positions truly exist even if
            # message_info was created without that flag.
            current_qty = int(message_info.get('quantity', 1))
            has_position = bool(message_info.get('has_position', False))
            try:
                # processed_data may contain direct IBKR fields populated earlier
                pd = processed_data or {}
                # 1) explicit IBKR position size
                ibkr_pos_size = pd.get('ibkr_position_size')
                if ibkr_pos_size is not None:
                    try:
                        if float(ibkr_pos_size) != 0:
                            has_position = True
                    except Exception:
                        pass

                # 2) flag set earlier to force close button
                if pd.get('show_close_position_button'):
                    has_position = True

                # 3) option_contracts listed in processed_data
                if pd.get('option_contracts') and isinstance(pd.get('option_contracts'), (list, tuple)) and len(pd.get('option_contracts')) > 0:
                    has_position = True

                # 4) stored_contract presence with storage indicating open contracts
                if not has_position and pd.get('stored_contract'):
                    try:
                        from app.services.alerter_stock_storage import alerter_stock_storage
                        stored = pd.get('stored_contract')
                        ticker_k = (stored.get('ticker') or stored.get('symbol') or '')
                        if ticker_k:
                            summary = alerter_stock_storage.get_total_open_contracts(message_info.get('alerter'))
                            if isinstance(summary, dict) and 'contracts' in summary:
                                matches = [c for c in summary['contracts'] if (c.get('ticker') or '').upper() == str(ticker_k).upper()]
                                if matches:
                                    has_position = True
                    except Exception:
                        pass
            except Exception:
                # Fall back to message_info flag if anything fails
                has_position = bool(message_info.get('has_position', False))

            midpoint_price = self._get_midpoint_price(processed_data)
            if not has_position:
                alert_html += f"\n💰 Quantity: {current_qty} contract(s)"
                if midpoint_price:
                    total_cost = midpoint_price * 100 * current_qty
                    alert_html += f"\n💵 Price per contract: ${midpoint_price:.2f}"
                    # Show total estimated cost like the initial send_trading_alert
                    try:
                        alert_html += f"\n🏷️ Total cost: ${total_cost:.0f}"
                    except Exception:
                        # rounding/display shouldn't block regeneration
                        alert_html += f"\n🏷️ Total cost: ${int(total_cost)}"
            else:
                # Determine position size consistently. Prefer IBKR-provided value,
                # then fall back to spx_position/position dicts, then to sum of option_contracts.
                position_size = 0
                # 1) IBKR direct position size
                ibkr_pos_size = processed_data.get('ibkr_position_size')
                if ibkr_pos_size is not None:
                    try:
                        position_size = int(ibkr_pos_size)
                    except Exception:
                        position_size = ibkr_pos_size
                else:
                    # 2) spx_position or generic 'position' dict
                    pos_data = processed_data.get('spx_position') or processed_data.get('position')
                    if isinstance(pos_data, dict):
                        position_size = pos_data.get('position', 0)
                    elif isinstance(pos_data, (int, float)):
                        position_size = int(pos_data)

                # 3) If we have option_contracts, prefer their summed quantities when greater than 0
                try:
                    if 'option_contracts' in locals() and option_contracts:
                        summed = sum(int(c.get('quantity', 0)) for c in option_contracts)
                        if summed > 0:
                            position_size = summed
                except Exception:
                    pass
                alert_html += f"\n📊 Position: {abs(position_size)} contract(s)"
                try:
                    pos_disp = abs(int(position_size)) if position_size is not None else None
                except Exception:
                    pos_disp = None
                if pos_disp:
                    alert_html += f"\n💰 Close Quantity: {current_qty}/{pos_disp} contract(s)"
                else:
                    alert_html += f"\n💰 Close Quantity: {current_qty} contract(s)"

                # Lightweight mode: estimate P/L for the selected close quantity using cached processed_data
                try:
                    if lightweight:
                        ibkr_pos_size = processed_data.get('ibkr_position_size')
                        ibkr_unreal = processed_data.get('ibkr_unrealized_pnl')
                        ibkr_real = processed_data.get('ibkr_realized_pnl')
                        # Only compute when we have a numeric IBKR position size
                        if ibkr_pos_size and current_qty:
                            try:
                                pos_size_num = float(ibkr_pos_size)
                                if pos_size_num != 0:
                                    # Per-contract unrealized/realized (fall back to 0 if missing)
                                    per_unreal = (float(ibkr_unreal) / pos_size_num) if ibkr_unreal is not None else 0.0
                                    per_real = (float(ibkr_real) / pos_size_num) if ibkr_real is not None else 0.0
                                    est_unreal = per_unreal * float(current_qty)
                                    est_real = per_real * float(current_qty)
                                    # Colorize
                                    def _color_amt(v):
                                        if v > 0:
                                            return f"🟢 +${abs(v):,.2f}"
                                        if v < 0:
                                            return f"🔴 -${abs(v):,.2f}"
                                        return f"⚪ $0.00"

                                    # Keep the same preformatted HTML block as the initial send
                                    try:
                                        alert_html += "\n\n<b>🔎 Estimated Close P/L:</b>\n<pre>"
                                        alert_html += esc(f"Estimated close unrealized P/L for {current_qty} contract(s): {_color_amt(est_unreal)}") + "\n"
                                        alert_html += esc(f"Estimated close realized P/L for {current_qty} contract(s): {_color_amt(est_real)}") + "\n"
                                        alert_html += "</pre>"
                                    except Exception:
                                        # Fallback to inline escaped lines if HTML insertion fails
                                        alert_html += "\n" + esc(f"Estimated close unrealized P/L for {current_qty} contract(s): {_color_amt(est_unreal)}")
                                        alert_html += "\n" + esc(f"Estimated close realized P/L for {current_qty} contract(s): {_color_amt(est_real)}")
                            except Exception:
                                # Numeric conversion failed; skip estimates
                                pass
                except Exception:
                    # Don't let estimation failures block regeneration
                    pass

                # Add per-contract rows (storage first, then IBKR fallback)
                try:
                    # In lightweight mode we avoid storage/IBKR lookups to keep UI updates snappy
                    option_contracts = []
                    if not lightweight:
                        import re
                        ticker_for_check = None
                        m = re.search(r'\$([A-Z]+)', original_message)
                        if m:
                            ticker_for_check = m.group(1)
                        if not ticker_for_check:
                            ticker_for_check = processed_data.get('ticker')

                        if ticker_for_check:
                            try:
                                from app.services.alerter_stock_storage import alerter_stock_storage
                                contracts_summary = alerter_stock_storage.get_total_open_contracts(alerter)
                                if isinstance(contracts_summary, dict) and 'contracts' in contracts_summary:
                                    option_contracts = [c for c in contracts_summary['contracts'] if (c.get('ticker') or '').upper() == ticker_for_check.upper()]
                            except Exception:
                                option_contracts = []

                            if not option_contracts:
                                try:
                                    from app.services.ibkr_service import IBKRService
                                    ibkr = IBKRService()
                                    for pos in ibkr.get_positions() or []:
                                        sec_type = (pos.get('assetClass') or pos.get('secType') or '').upper()
                                        symbol = pos.get('contractDesc') or pos.get('symbol') or ''
                                        position_qty = abs(int(pos.get('position', 0)))
                                        if sec_type == 'OPT' and symbol and position_qty > 0 and ticker_for_check.upper() in symbol.upper():
                                            parts = symbol.split()
                                            strike = next((p for p in parts if p.replace('.', '', 1).isdigit()), None)
                                            side = next((p for p in parts if p.upper() in ['C', 'P']), None)
                                            option_contracts.append({
                                                'symbol': symbol,
                                                'ticker': ticker_for_check,
                                                'strike': strike,
                                                'side': 'CALL' if (side or '').upper() == 'C' else ('PUT' if (side or '').upper() == 'P' else None),
                                                'quantity': position_qty,
                                                'unrealizedPnl': pos.get('unrealizedPnl'),
                                                'realizedPnl': pos.get('realizedPnl'),
                                                'marketValue': pos.get('mktValue') or pos.get('marketValue'),
                                                'avgPrice': pos.get('avgPrice') or pos.get('avgCost'),
                                                'currentPrice': pos.get('mktPrice') or pos.get('currentPrice')
                                            })
                                    # formatted positions
                                    if not option_contracts:
                                        for pos in (ibkr.get_formatted_positions() or []):
                                            sec_type = (pos.get('secType') or '').upper()
                                            symbol = pos.get('symbol') or pos.get('description') or ''
                                            position_qty = abs(int(pos.get('position', 0)))
                                            if sec_type == 'OPT' and symbol and position_qty > 0 and ticker_for_check.upper() in symbol.upper():
                                                parts = symbol.split()
                                                strike = next((p for p in parts if p.replace('.', '', 1).isdigit()), None)
                                                side = next((p for p in parts if p.upper() in ['C', 'P']), None)
                                                option_contracts.append({
                                                    'symbol': symbol,
                                                    'ticker': ticker_for_check,
                                                    'strike': strike,
                                                    'side': 'CALL' if (side or '').upper() == 'C' else ('PUT' if (side or '').upper() == 'P' else None),
                                                    'quantity': position_qty,
                                                    'unrealizedPnl': pos.get('unrealizedPnl'),
                                                    'realizedPnl': pos.get('realizedPnl'),
                                                    'marketValue': pos.get('marketValue'),
                                                    'avgPrice': pos.get('avgPrice') or pos.get('avgCost'),
                                                    'currentPrice': pos.get('currentPrice')
                                                })
                                except Exception:
                                    # Ignore IBKR/storage lookup failures for regeneration
                                    pass

                    if option_contracts:
                        alert_html += "\n<b>Contracts:</b>\n<pre>"
                        for c in option_contracts:
                                try:
                                    raw_ticker = c.get('symbol') or c.get('ticker') or ''
                                    formatted_ticker, _ = self._format_contract_display(raw_ticker, additional_info='', alerter_name=alerter, processed_data=processed_data)
                                    line = f"{formatted_ticker}"
                                except Exception:
                                    line = f"{c.get('symbol', '')}"

                                # Add quantity and optional P/L/pricing info
                                line += f" Qty: {c.get('quantity', 0)}"
                                if c.get('unrealizedPnl') is not None:
                                    line += f" | Unrealized P/L: ${c.get('unrealizedPnl')}"
                                if c.get('realizedPnl') is not None:
                                    line += f" | Realized P/L: ${c.get('realizedPnl')}"
                                if c.get('avgPrice') is not None:
                                    line += f" | Avg Price: ${c.get('avgPrice')}"
                                if c.get('currentPrice') is not None:
                                    line += f" | Current Price: ${c.get('currentPrice')}"
                                if c.get('marketValue') is not None:
                                    line += f" | Market Value: ${c.get('marketValue')}"
                                alert_html += esc(line) + "\n"
                        alert_html += "</pre>"
                except Exception:
                    logger.debug("Error adding per-contract rows in regeneration")

            # Footer: action and timestamp
            # If processing produced a response (order result), include it so
            # users see whether an order was placed or failed.
            resp = message_info.get('response') if isinstance(message_info, dict) else None
            if resp:
                try:
                    alert_html += "\n\n<b>🔔 Order Result:</b>\n<pre>"
                    if isinstance(resp, dict):
                        for k, v in resp.items():
                            try:
                                alert_html += esc(f"{k}: {v}") + "\n"
                            except Exception:
                                alert_html += esc(f"{k}: {str(v)}") + "\n"
                    else:
                        alert_html += esc(str(resp)) + "\n"
                    alert_html += "</pre>"
                except Exception:
                    # Ignore rendering errors
                    pass

            alert_html += f"\n\n<b>✅ Action Selected: {esc(action)}</b>"
            alert_html += f"\n{datetime.now().strftime('%H:%M:%S')}"
            alert_html += f"\n🔄 Processing {esc(action.lower())} action..."

            return alert_html
        except Exception as e:
            logger.error(f"Error regenerating alert text (HTML): {e}")
            from html import escape as _html_escape
            def esc(x):
                return _html_escape(str(x)) if x is not None else ""
            return (
                f"✅ Action Selected: <b>{esc(action)}</b><br/><br/>"
                f"🎯 Alerter: {esc(message_info.get('alerter', 'Unknown'))}<br/>"
                f"💬 Message: {esc(message_info.get('original_message', 'Unknown'))}<br/>"
                f"⏰ Response Time: {datetime.now().strftime('%H:%M:%S')}<br/><br/>"
                f"🔄 Processing {esc(action.lower())} action..."
            )

# Global instance - token loaded from environment variable
import os
telegram_service = TelegramService(bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""))
