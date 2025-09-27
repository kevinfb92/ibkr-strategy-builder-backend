"""
Real Day Trading alerter handler
"""
from typing import Dict, Any
import logging
from ..alerter_stock_storage import alerter_stock_storage
from ..ibkr_service import ibkr_service

logger = logging.getLogger(__name__)

class RealDayTradingHandler:
    """Handler for Real Day Trading notifications"""
    
    def __init__(self):
        self.alerter_name = "Real Day Trading"
    
    def process_notification(self, title: str, message: str, subtext: str) -> Dict[str, Any]:
        """
        Process Real Day Trading notification
        
        Handles alerts that start with:
        - Long - Opening a long position
        - Short - Opening a short position
        - Exit - Closing a position
        - Added - Adding to an existing position
        
        Args:
            title: The notification title
            message: The message/ticker info
            subtext: The main notification content
            
        Returns:
            Dict with processed notification data
        """
        try:
            logger.info(f"Processing {self.alerter_name} notification")
            print(f"DEBUG: Processing {self.alerter_name} notification")
            print(f"DEBUG: Title: {title}")
            print(f"DEBUG: Message: {message}")
            print(f"DEBUG: Subtext: {subtext}")
            
            # Parse the alert content
            parsed_data = self._parse_day_trading_alert(message, subtext)
            
            # Store the stock alert ONLY if all conditions are met
            ticker = parsed_data.get("ticker", "").strip()
            valid_to_store = False
            ibkr_contract = None
            if ticker and ticker != "UNKNOWN":
                # 1. Notification must include Long or Short (either starting in message or detected by parser)
                message_lower = message.strip().lower()
                starts_with_long_short = message_lower.startswith("long") or message_lower.startswith("short")
                parsed_action_is_long_short = parsed_data.get("action", "").upper() in ("LONG", "SHORT")
                # Accept if the message explicitly starts with long/short OR parser found the action somewhere
                should_attempt_store = starts_with_long_short or parsed_action_is_long_short
                # 2. Ticker must exist in a US exchange (via IBKR contract lookup)
                if should_attempt_store:
                    from app.services.ibkr_service import IBKRService
                    ibkr_service = IBKRService()
                    contracts = ibkr_service.client.search_contract_by_symbol(symbol=ticker, sec_type="STK")
                    # Normalize different possible response shapes and defensively handle non-dict entries
                    entries = []
                    if contracts:
                        data_attr = getattr(contracts, 'data', None)
                        if data_attr:
                            entries = data_attr
                        elif isinstance(contracts, dict) and 'data' in contracts:
                            entries = contracts.get('data') or []
                        elif isinstance(contracts, list):
                            entries = contracts

                    if entries:
                        for contract in entries:
                            # Skip non-dict contract representations (defensive)
                            if not isinstance(contract, dict):
                                continue

                            # Only store if contract is on a US exchange (exchange string contains 'NYSE', 'NASDAQ', etc.)
                            exch = contract.get("exchange", "").upper()
                            valid_exchanges = ["SMART", "NYSE", "NASDAQ", "AMEX", "ARCA", "BATS", "IEX", "OTC", "CBOE", "NYS", "NSD"]
                            found_valid = False
                            # Check top-level exchange
                            if any(e in exch for e in valid_exchanges):
                                found_valid = True
                            # Check description field
                            desc = contract.get("description", "").upper()
                            if any(e in desc for e in valid_exchanges):
                                found_valid = True
                            # Check sections field for exchanges
                            sections = contract.get("sections", [])
                            for section in sections:
                                sec_exch = section.get("exchange", "").upper() if isinstance(section, dict) else ""
                                if any(e in sec_exch for e in valid_exchanges):
                                    found_valid = True
                                    break
                            # Check validExchanges field (comma-separated string)
                            valid_exchanges_field = contract.get("validExchanges", "")
                            if valid_exchanges_field:
                                for e in valid_exchanges:
                                    if e in valid_exchanges_field.upper():
                                        found_valid = True
                                        break
                            if found_valid:
                                ibkr_contract = contract
                                valid_to_store = True
                                break
            found_dollar_pattern = message.strip().startswith("$")
            if valid_to_store:
                stock_alert_data = {
                    "action": parsed_data.get("action", "UNKNOWN"),
                    "instrument_type": parsed_data.get("instrument_type", "UNKNOWN"),
                    "contract_count": parsed_data.get("contract_count"),
                    "strike_price": parsed_data.get("strike_price"),
                    "expiration_date": parsed_data.get("expiration_date"),
                    "price": parsed_data.get("price"),
                    "quantity": parsed_data.get("quantity"),
                    "alert_type": parsed_data.get("alert_type", "GENERAL"),
                    "original_title": title,
                    "original_message": message,
                    "original_subtext": subtext,
                    "full_text": parsed_data.get("raw_text", ""),
                    "ibkr_contract": ibkr_contract,
                    "ibkr_option_lookup": parsed_data.get("ibkr_option_lookup"),
                    "ibkr_contract_result": parsed_data.get("ibkr_contract_result")
                }
                was_new_stock = alerter_stock_storage.add_stock_alert(
                    self.alerter_name,
                    ticker,
                    stock_alert_data
                )
                parsed_data["stored_in_alerter_storage"] = True
                parsed_data["was_new_stock_alert"] = was_new_stock
                if was_new_stock:
                    logger.info(f"Added new stock to {self.alerter_name} alerts: {ticker}")
                    print(f"DEBUG: Added new stock to {self.alerter_name} alerts: {ticker}")
                else:
                    logger.info(f"Updated existing stock alert for {self.alerter_name}: {ticker}")
                    print(f"DEBUG: Updated existing stock alert for {self.alerter_name}: {ticker}")
                active_stocks = alerter_stock_storage.get_active_stocks(self.alerter_name)
                parsed_data["active_stocks_count"] = len(active_stocks)
                parsed_data["all_active_stocks"] = active_stocks
            # IBKR position lookup for every notification
            try:
                from app.services.ibkr_service import IBKRService
                ibkr_service = IBKRService()
                positions = ibkr_service.get_formatted_positions()
                # Find position for this ticker
                ticker_positions = [p for p in positions if p.get("symbol", "").upper().startswith(ticker.upper())]
                if ticker_positions:
                    pos = ticker_positions[0]
                    parsed_data["ibkr_position_size"] = pos.get("position", 0)
                    parsed_data["ibkr_unrealized_pnl"] = pos.get("unrealizedPnl", 0)
                    parsed_data["ibkr_realized_pnl"] = pos.get("realizedPnl", 0)
                    parsed_data["ibkr_market_value"] = pos.get("marketValue", 0)
                    parsed_data["ibkr_avg_price"] = pos.get("avgPrice", 0)
                    parsed_data["ibkr_current_price"] = pos.get("currentPrice", 0)
                    parsed_data["show_close_position_button"] = True
                    # Remove ticker from storage if position is closed
                    if pos.get("position", 0) == 0:
                        alerter_stock_storage.remove_stock_alert(self.alerter_name, ticker)
                else:
                    parsed_data["ibkr_position_size"] = 0
                    parsed_data["show_close_position_button"] = False
            except Exception as e:
                parsed_data["ibkr_position_error"] = str(e)

            # If we didn't validate for storage, explicitly mark that
            if not valid_to_store:
                parsed_data["stored_in_alerter_storage"] = False
                parsed_data["storage_error"] = "Stock did not meet all validation conditions (Long/Short, $NAME, US exchange)"
                logger.warning(f"Stock did not meet all validation conditions - not stored")
                print(f"DEBUG: Stock did not meet all validation conditions - not stored")
            
            # Real Day Trading specific processing logic
            processed_data = {
                "alerter": self.alerter_name,
                "original_title": title,
                "original_message": message,
                "original_subtext": subtext,
                "processed": True,
                "timestamp": self._get_timestamp()
            }
            
            # Add parsed trading data
            processed_data.update(parsed_data)
            
            # Condensed debug output - only show key fields for readability
            try:
                concise = {
                    "alerter": processed_data.get("alerter"),
                    "timestamp": processed_data.get("timestamp"),
                    "action": processed_data.get("action"),
                    "ticker": processed_data.get("ticker"),
                    "price": processed_data.get("price"),
                    "quantity": processed_data.get("quantity"),
                    "ibkr_position_size": processed_data.get("ibkr_position_size"),
                    "show_close_position_button": processed_data.get("show_close_position_button"),
                    "stored_in_alerter_storage": processed_data.get("stored_in_alerter_storage"),
                    "storage_error": processed_data.get("storage_error")
                }
            except Exception:
                concise = {"alerter": processed_data.get("alerter"), "timestamp": processed_data.get("timestamp")}

            print(f"DEBUG: Processed summary: {concise}")
            
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
    
    def _parse_day_trading_alert(self, message: str, subtext: str) -> Dict[str, Any]:
        """
        Parse day trading alert content
        
        Recognizes patterns like:
        - Long AAPL
        - Short TSLA at $150
        - Exit MSFT
        - Added to NVDA position
        
        Note: After notification service fix, message contains the ticker/action (e.g., "Long $AAPL")
        and subtext contains the full alert content.
        """
        import re
        
        # Combine message and subtext for parsing, prioritizing message for action detection
        # Message now contains: "Long $AAPL" (action + ticker)
        # Subtext contains: "Going long on Apple at $150.25..." (full content)
        full_text = f"{message} {subtext}".strip()
        print(f"DEBUG: Parsing full text: '{full_text}'")
        print(f"DEBUG: Message (action+ticker): '{message}'")
        print(f"DEBUG: Subtext (full content): '{subtext}'")
        
        # Initialize result
        result = {
            "action": "UNKNOWN",
            "ticker": "",
            "instrument_type": "UNKNOWN",  # STOCK or OPTION
            "price": None,
            "quantity": None,
            "alert_type": "GENERAL",
            "raw_text": full_text
        }
        
        # Check for specific action patterns (case insensitive) - prioritize message field
        action_patterns = {
            "LONG": r'^(long|going long)\s+',
            "SHORT": r'^(short|going short|shorting)\s+',
            "EXIT": r'^(exit|exiting|close|closing)\s+',
            "ADDED": r'^(added|adding|add)\s+'
        }
        
        # First check the message field for action (more reliable now)
        message_lower = message.lower()
        
        for action, pattern in action_patterns.items():
            if re.match(pattern, message_lower):
                result["action"] = action
                result["alert_type"] = "TRADING_ACTION"
                print(f"DEBUG: Detected action from message: {action}")
                break
        
        # If no action found in message, check full text
        if result["action"] == "UNKNOWN":
            full_text_lower = full_text.lower()
            
            # Also check for "shorting" pattern in full text
            full_text_patterns = {
                "LONG": r'(^|\s)(long|going long)\s+',
                "SHORT": r'(^|\s)(short|going short|shorting)\s+',
                "EXIT": r'(^|\s)(exit|exiting|close|closing)\s+',
                "ADDED": r'(^|\s)(added|adding|add)\s+'
            }
            
            for action, pattern in full_text_patterns.items():
                if re.search(pattern, full_text_lower):
                    result["action"] = action
                    result["alert_type"] = "TRADING_ACTION"
                    print(f"DEBUG: Detected action from full text: {action}")
                    break
        
        # Extract ticker symbol (check message first, then full text)
        ticker = self._extract_ticker_enhanced(message)
        if not ticker:
            ticker = self._extract_ticker_enhanced(full_text)
        
        if ticker:
            result["ticker"] = ticker
            print(f"DEBUG: Extracted ticker: {ticker}")
        
        # Determine instrument type (stock vs option) - use full text for context
        instrument_type, contract_count = self._detect_instrument_type_enhanced(full_text, result["action"])
        result["instrument_type"] = instrument_type
        result["contract_count"] = contract_count
        print(f"DEBUG: Detected instrument type: {instrument_type}")
        if contract_count:
            print(f"DEBUG: Detected contract count: {contract_count}")
        
        # Extract price information - use full text for better context
        # Pass ticker so the extractor can pick the price closest to current market price when ambiguous
        price = self._extract_price_enhanced(full_text, ticker=result.get("ticker"))
        if price:
            result["price"] = price
            print(f"DEBUG: Extracted price: {price}")
        
        # Extract strike price if this is an options play
        strike_price = None
        if result["action"] in ["LONG", "SHORT"] and result["instrument_type"] in ["OPTION", "OPTION_CONFIRMED"]:
            strike_price = self._extract_strike_price(full_text)
            if strike_price:
                result["strike_price"] = strike_price
                print(f"DEBUG: Extracted strike price: {strike_price}")
        
        # Extract expiration date if provided
        expiration_date = None
        if result["action"] in ["LONG", "SHORT"]:
            expiration_date = self._extract_expiration_date(full_text)
            if expiration_date:
                result["expiration_date"] = expiration_date
                print(f"DEBUG: Extracted expiration date: {expiration_date}")
        
        # Extract quantity if mentioned - use full text
        quantity = self._extract_quantity(full_text)
        if quantity:
            result["quantity"] = quantity
            print(f"DEBUG: Extracted quantity: {quantity}")
        
        # Add bot decision flags based on instrument type detection
        result["bot_should_offer_options"] = self._should_bot_offer_options(result)

        # For LONG/SHORT actions, find the option contract via IBKR API
        if result["action"] in ["LONG", "SHORT"]:
            # Skip PDS/CDS for now as requested
            if not any(keyword in full_text.upper() for keyword in ["PDS", "CDS"]):
                # Use the centralized IBKRService.find_option_contract when possible
                try:
                    from app.services.ibkr_service import IBKRService
                    ibkr = IBKRService()

                    # Compute strike and expiry sentinels as before
                    strike = None
                    try:
                        strike = self._get_strike_price(result, result.get("ticker"), result.get("action"))
                    except Exception:
                        strike = None

                    expiry = None
                    try:
                        expiry = self._get_expiration_date(result)
                    except Exception:
                        expiry = None

                    option_type = None
                    try:
                        option_type = self._determine_option_type(result, result.get("action"), full_text)
                    except Exception:
                        option_type = None

                    used_ibkr_result = None

                    # If strike is a closest_itm sentinel or expiry requests closest, prefer the robust finder
                    if (isinstance(strike, str) and strike.startswith("closest_itm_")) or expiry == "closest":
                        try:
                            fc = ibkr.find_option_contract(
                                ticker=result.get("ticker") or "",
                                option_type=option_type or "CALL",
                                expiration_date=expiry or "closest",
                                strike_price=str(strike) if strike is not None else "",
                                action=result.get("action") or "LONG",
                            )
                            # Merge fields from find_option_contract result
                            if isinstance(fc, dict):
                                if fc.get("contract_details"):
                                    used_ibkr_result = used_ibkr_result or {}
                                    used_ibkr_result["ibkr_contract_result"] = fc.get("contract_details")
                                    used_ibkr_result["instrument_type"] = "OPTION"
                                if fc.get("market_data"):
                                    used_ibkr_result = used_ibkr_result or {}
                                    used_ibkr_result["ibkr_market_data"] = fc.get("market_data")
                                # preserve metadata returned by the finder
                                for k in ("used_strike", "used_expiration", "strike_source", "expiration_source", "conid", "success"):
                                    if k in fc:
                                        used_ibkr_result = used_ibkr_result or {}
                                        used_ibkr_result[k] = fc[k]
                        except Exception:
                            used_ibkr_result = None

                    # If the robust finder returned something, use it; otherwise fall back to existing logic
                    if used_ibkr_result:
                        result.update(used_ibkr_result)
                    else:
                        ibkr_result = self._find_option_contract(result, full_text)
                        result.update(ibkr_result)
                except Exception:
                    # As a last resort, call the local finder which has its own defensive fallbacks
                    ibkr_result = self._find_option_contract(result, full_text)
                    result.update(ibkr_result)

        return result
    
    def _should_bot_offer_options(self, parsed_data: Dict[str, Any]) -> bool:
        """
        Determine if the bot should offer option contracts regardless of original intent
        
        Based on the requirement: "no matter if the alert says to buy stock or options,
        we're always going to offer, in the bot, to buy the equivalent option contract"
        
        Args:
            parsed_data: The parsed alert data
            
        Returns:
            bool: True if bot should offer options, False otherwise
        """
        action = parsed_data.get("action", "")
        
        # Only offer options for LONG and SHORT actions (not EXIT or ADDED)
        if action in ["LONG", "SHORT"]:
            return True
        return False
    
    def _determine_option_type(self, parsed_data: Dict[str, Any], action: str, full_text: str) -> str:
        """
        Determine option type (CALL or PUT) based on alert content and action
        
        Logic:
        - If calls/puts explicitly mentioned, use that
        - If no option keywords found: LONG → CALL, SHORT → PUT
        """
        text_lower = full_text.lower()
        
        # Check for explicit mentions
        if "calls" in text_lower or "call" in text_lower:
            return "CALL"
        elif "puts" in text_lower or "put" in text_lower:
            return "PUT"
        
        # Default based on action
        if action == "LONG":
            print(f"DEBUG: No option type specified, defaulting to CALL for LONG")
            return "CALL"
        elif action == "SHORT":
            print(f"DEBUG: No option type specified, defaulting to PUT for SHORT")
            return "PUT"
        
        return "CALL"  # fallback
    
    def _get_expiration_date(self, parsed_data: Dict[str, Any]) -> str:
        """Get expiration date from parsed data or use default (closest expiration)"""
        exp_date = parsed_data.get("expiration_date")
        if exp_date:
            print(f"DEBUG: Using extracted expiration date: {exp_date}")
            return exp_date
        
        print(f"DEBUG: No expiration date found, will use closest available")
        return "closest"  # Special value for IBKR service to use closest expiration
    
    def _get_strike_price(self, parsed_data: Dict[str, Any], ticker: str, action: str) -> str:
        """
        Get strike price from parsed data or determine based on current stock price
        
        For closest ITM selection:
        - LONG (calls): Strike below current price (ITM call)
        - SHORT (puts): Strike above current price (ITM put)
        """
        strike = parsed_data.get("strike_price")
        if strike and "/" not in strike:  # Exclude spreads for now
            # Remove $ symbol for IBKR API
            strike_clean = strike.replace("$", "")
            print(f"DEBUG: Using extracted strike price: {strike_clean}")
            return strike_clean
        
        print(f"DEBUG: No single strike found, will find closest ITM for {action}")
        return f"closest_itm_{action.lower()}"  # Special value for IBKR service

    def _find_option_contract(self, parsed_data: Dict[str, Any], full_text: str) -> Dict[str, Any]:
        """
        Find an option contract using IBKR based on parsed data.

        Returns a dictionary safe to merge into parsed results. Keys:
        - ibkr_option_lookup: raw search/lookup result (if any)
        - ibkr_contract_result: resolved IBKR contract details (if any)
        - ibkr_market_data: market data for the contract (if any)
        - instrument_type: set to 'OPTION' when contract found
        """
        try:
            # Minimal defensive import to avoid startup cycles
            from app.services.ibkr_service import IBKRService

            ibkr = IBKRService()

            ticker = parsed_data.get("ticker") or "SPX"
            action = parsed_data.get("action", "LONG")

            # Resolve strike, expiry and right
            strike = None
            try:
                strike = self._get_strike_price(parsed_data, ticker, action)
            except Exception:
                strike = None

            expiry = None
            try:
                expiry = self._get_expiration_date(parsed_data)
            except Exception:
                expiry = None

            right = None
            try:
                right = self._determine_option_type(parsed_data, action, full_text)
            except Exception:
                right = None

            lookup_result = None
            contract_details = None
            market_data = None

            # Only attempt lookup if we have at least a strike or expiry or ticker
            try:
                lookup_result = ibkr.client.search_contract_by_symbol(symbol=ticker, sec_type="OPT")
            except Exception:
                lookup_result = None

            # Try to get a specific option contract if we have strike/right/expiry
            if strike or expiry or right:
                try:
                    contract_details = ibkr.get_option_contract_details(
                        symbol=ticker,
                        strike=strike,
                        right=(right[0] if right else None),
                        expiry=expiry,
                    )
                except Exception:
                    contract_details = None

            # Fetch market data if we resolved a contract
            if contract_details:
                try:
                    market_data = ibkr.get_option_market_data(contract_details)
                except Exception:
                    market_data = None

            # Fallback: if no contract_details or market_data but we have a lookup_result,
            # try each conid from the lookup_result and request a market-data snapshot until we find pricing.
            if (not contract_details or not market_data) and lookup_result:
                try:
                    entries = getattr(lookup_result, 'data', None) or lookup_result.data if hasattr(lookup_result, 'data') else None
                    if entries and isinstance(entries, list):
                        for entry in entries:
                            try:
                                # extract conid candidate
                                candidate_conid = None
                                if isinstance(entry, dict):
                                    candidate_conid = entry.get('conid') or (entry.get('contracts')[0].get('conid') if entry.get('contracts') else None)
                                else:
                                    candidate_conid = getattr(entry, 'conid', None)

                                if not candidate_conid:
                                    continue

                                # request market data snapshot for candidate conid
                                md = ibkr._request_market_data_with_retry(str(candidate_conid), fields=["31", "84", "86", "87"]) or {}
                                last = md.get('31') or md.get('last') or md.get('lastPrice') if isinstance(md, dict) else None
                                if last is not None:
                                    # attach minimal contract details and market data
                                    contract_details = {"conid": candidate_conid, "symbol": ticker}
                                    market_data = md
                                    print(f"DEBUG: Fallback: found market data for option conid={candidate_conid} last={last}")
                                    break
                            except Exception:
                                continue
                except Exception:
                    pass

            result = {}
            if lookup_result:
                result["ibkr_option_lookup"] = lookup_result
                try:
                    n = len(getattr(lookup_result, 'data', [])) if lookup_result else 0
                    print(f"DEBUG: Option lookup returned {n} entries for {ticker}")
                except Exception:
                    print(f"DEBUG: Option lookup returned entries for {ticker}")
            if contract_details:
                result["ibkr_contract_result"] = contract_details
                result["instrument_type"] = "OPTION"
                # Concise contract summary
                try:
                    conid = contract_details.get('conid') if isinstance(contract_details, dict) else getattr(contract_details, 'conid', None)
                    exp = contract_details.get('expiry') if isinstance(contract_details, dict) else getattr(contract_details, 'expiry', None)
                    strike_val = contract_details.get('strike') if isinstance(contract_details, dict) else getattr(contract_details, 'strike', None)
                    right_val = contract_details.get('right') if isinstance(contract_details, dict) else getattr(contract_details, 'right', None)
                    print(f"DEBUG: Resolved option contract: conid={conid} expiry={exp} strike={strike_val} right={right_val}")
                except Exception:
                    print("DEBUG: Resolved option contract (summary unavailable)")
            if market_data:
                result["ibkr_market_data"] = market_data
                # Concise market data summary (try common field keys)
                try:
                    conid_md = None
                    if isinstance(market_data, dict):
                        conid_md = market_data.get('conid') or market_data.get('conidEx')
                        last = market_data.get('31') or market_data.get('last') or market_data.get('lastPrice') or None
                    else:
                        last = None
                    print(f"DEBUG: Market data fetched for conid={conid_md} last={last}")
                except Exception:
                    print("DEBUG: Market data fetched (summary unavailable)")

            # If nothing useful found, log concise message
            if not contract_details and not market_data:
                print(f"DEBUG: No option contract or market data resolved for {ticker}")

            return result

        except Exception as e:
            # Fail softly and return empty dict so parsing can continue
            print(f"DEBUG: _find_option_contract error: {e}")
            return {}
    
    def _extract_ticker_enhanced(self, text: str) -> str:
        """Enhanced ticker extraction for day trading alerts"""
        import re
        
        # Remove common words first
        text_clean = text.upper()
        print(f"DEBUG: Extracting ticker from: '{text_clean}'")
        
        # Look for ticker patterns - prioritize $TICKER format but avoid prices
        ticker_patterns = [
            # Priority 1: $TICKER format (but not prices like $50, $123.45)
            r'\$([A-Z]{1,5})(?![0-9\.])',  # $TICKER not followed by numbers or decimal
            
            # Priority 2: TICKER followed by instrument indicators  
            r'([A-Z]{1,5})\s+(?:STOCK|SHARES|OPTION|CALLS?|PUTS?)',
            
            # Priority 3: Action + TICKER patterns
            r'(?:LONG|SHORT|EXIT|ADDED?)\s+([A-Z]{1,5})(?:\s|$)',
            
            # Priority 4: General ticker patterns (but avoid common words)
            r'\b([A-Z]{2,5})\b',  # 2-5 uppercase letters (avoid single letters)
        ]
        
        for i, pattern in enumerate(ticker_patterns, 1):
            matches = re.findall(pattern, text_clean)
            print(f"DEBUG: Pattern {i} matches: {matches}")
            
            if matches:
                # Return the first match that's not a common word or number
                for match in matches:
                    # Skip common words and action keywords
                    excluded_words = {
                        'LONG', 'SHORT', 'EXIT', 'ADDED', 'CALL', 'PUT', 'STOCK', 'OPTION', 
                        'CALLS', 'PUTS', 'SHARES', 'GOING', 'ADDED', 'THE', 'AND', 'OR',
                        'AT', 'TO', 'FROM', 'FOR', 'WITH', 'ON', 'IN', 'BY', 'OF'
                    }
                    
                    # Skip if it's an excluded word
                    if match in excluded_words:
                        continue
                        
                    # Skip if it looks like a number (shouldn't happen with our regex, but safety check)
                    if match.isdigit():
                        continue
                        
                    print(f"DEBUG: Selected ticker: {match}")
                    return match
        
        print(f"DEBUG: No ticker found")
        return ""
    
    def _detect_instrument_type_enhanced(self, text: str, action: str) -> tuple[str, str]:
        """
        Enhanced detection of instrument type with specific option contract detection
        
        For Long/Short actions, checks for:
        - Calls, Puts, PDS, CDS keywords
        - Contract count format: "15 contracts" or "1 contract"
        
        Args:
            text: Full text to analyze
            action: Detected action (LONG, SHORT, etc.)
            
        Returns:
            Tuple of (instrument_type, contract_count)
            instrument_type: "OPTION_CONFIRMED", "OPTION", "STOCK"
            contract_count: "15" or "1" or None
        """
        text_lower = text.lower()
        
        # Only apply enhanced detection for LONG and SHORT actions
        if action in ["LONG", "SHORT"]:
            print(f"DEBUG: Enhanced option detection for {action} action")
            
            # Check for option-specific keywords
            option_keywords = ['calls', 'puts', 'pds', 'cds']
            option_keyword_found = any(keyword in text_lower for keyword in option_keywords)
            
            if option_keyword_found:
                print(f"DEBUG: Found option keywords in text")
                
                # Look for contract count patterns
                import re
                
                # Pattern for "X contracts" or "X contract"
                contract_patterns = [
                    r'(\d+)\s+contracts?',  # "15 contracts" or "1 contract"
                ]
                
                contract_count = None
                for pattern in contract_patterns:
                    matches = re.findall(pattern, text_lower)
                    if matches:
                        contract_count = matches[0]  # Take the first match
                        print(f"DEBUG: Found contract count: {contract_count}")
                        break
                
                if contract_count:
                    # Both option keywords AND contract count found = confirmed option
                    print(f"DEBUG: CONFIRMED OPTION - Keywords + Contract count found")
                    return "OPTION_CONFIRMED", contract_count
                else:
                    # Option keywords found but no contract count = likely option
                    print(f"DEBUG: LIKELY OPTION - Keywords found but no contract count")
                    return "OPTION", None
            else:
                print(f"DEBUG: No option keywords found for {action}")
        
        # Fall back to standard detection
        return self._detect_instrument_type_standard(text), None
    
    def _detect_instrument_type_standard(self, text: str) -> str:
        """Standard instrument type detection (original logic)"""
        text_lower = text.lower()
        
        # Option indicators
        option_keywords = ['call', 'put', 'option', 'strike', 'exp', 'expiry', 'expiration']
        if any(keyword in text_lower for keyword in option_keywords):
            return "OPTION"
        
        # Stock indicators (default)
        stock_keywords = ['stock', 'shares', 'equity']
        if any(keyword in text_lower for keyword in stock_keywords):
            return "STOCK"
        
        # Default to stock if unclear
        return "STOCK"
    
    def _extract_price_enhanced(self, text: str, ticker: str = None) -> str:
        """Enhanced price extraction - avoid confusing $TICKER with $PRICE.

        If multiple candidate prices are found, and a ticker is provided, query IBKR
        for the current stock price and return the candidate closest to that price.

        Falls back to the previous first-match behavior if market data is unavailable.
        """
        import re

        # Look for various price patterns, but be careful not to match $TICKER
        price_patterns = [
            # Price with decimal places (clearly a price)
            r'\$(\d+\.\d+)',           # $123.45

            # Price with "at" or "@" prefix
            r'at\s+\$?(\d+\.?\d*)',    # at $123 or at 123.45
            r'@\s*\$?(\d+\.?\d*)',     # @ $123 or @ 123.45

            # Price in context
            r'price\s+\$?(\d+\.?\d*)', # price $123
            r'target\s+\$?(\d+\.?\d*)', # target $123

            # Standalone numbers that are clearly prices (integers > 10, to avoid small numbers)
            r'\$(\d{2,})',             # $123 (but not $1, $2, etc.)

            # Numbers without $ but in price context
            r'(\d+\.\d+)',             # 123.45 (decimal indicates price)
        ]

        print(f"DEBUG: Extracting price from: '{text}'")

        candidates: list[float] = []
        candidates_raw: list[str] = []

        for i, pattern in enumerate(price_patterns, 1):
            matches = re.findall(pattern, text)
            print(f"DEBUG: Price pattern {i} matches: {matches}")

            for m in matches:
                try:
                    pv = float(m)
                    if 0.01 <= pv <= 10000:
                        candidates.append(pv)
                        candidates_raw.append(m)
                except Exception:
                    continue

            if candidates:
                # keep collecting matches across patterns but break after first pattern that produced matches
                break

        if not candidates:
            print(f"DEBUG: No price found")
            return None

        # If only one candidate, return it formatted
        if len(candidates) == 1:
            result = f"${candidates_raw[0]}"
            print(f"DEBUG: Selected price: {result}")
            return result

        # Multiple candidates: try to pick the one closest to current market price
        market_price = None
        if ticker:
            try:
                from app.services.ibkr_service import IBKRService
                ibkr = IBKRService()
                positions = ibkr.get_formatted_positions()
                # try to find the current price by ticker symbol match
                ticker_up = ticker.upper()
                for pos in positions:
                    sym = (pos.get("symbol") or "").upper()
                    if sym.startswith(ticker_up) or ticker_up in sym:
                        market_price = pos.get("currentPrice") or pos.get("avgPrice") or pos.get("marketValue")
                        break
                # If positions didn't contain it, try a market data snapshot via search_contract_by_symbol
                if market_price is None:
                    try:
                        search = ibkr.client.search_contract_by_symbol(symbol=ticker, sec_type="STK")
                        if search and getattr(search, 'data', None):
                            conid = search.data[0].get('conid')
                            md = ibkr._request_market_data_with_retry(str(conid), fields=["31"]) or {}
                            market_price = md.get('31') or md.get('last') or None
                    except Exception:
                        market_price = None
            except Exception as e:
                print(f"DEBUG: Unable to determine market price for {ticker}: {e}")

        # If market price available, pick candidate closest to it
        if market_price is not None:
            try:
                market_price = float(market_price)
                diffs = [abs(c - market_price) for c in candidates]
                idx = int(min(range(len(diffs)), key=lambda i: diffs[i]))
                selected_raw = candidates_raw[idx]
                result = f"${selected_raw}"
                print(f"DEBUG: Multiple prices found, selected closest to market price {market_price}: {result}")
                return result
            except Exception as e:
                print(f"DEBUG: Error comparing to market price: {e}")

        # Fallback: return the first candidate
        result = f"${candidates_raw[0]}"
        print(f"DEBUG: Multiple prices found but no market price available, selected first: {result}")
        return result
    
    def _extract_strike_price(self, text: str) -> str:
        """
        Extract strike price for options - handles single strikes and spreads
        
        Formats supported:
        - Single strike: $300, 420P, strike 150
        - Spread strikes: $500/$490 (for PDS/CDS)
        
        Key distinctions:
        - Strike: $300 or $500/$490 (whole numbers, comes first)
        - Price: $4.02 (has decimals, comes after strike)
        
        Args:
            text: Full text to analyze
            
        Returns:
            Strike price as string (e.g., "$300" or "$500/$490") or None
        """
        import re
        
        print(f"DEBUG: Extracting strike price from: '{text}'")
        
        # Check for PDS/CDS spread patterns first (more specific)
        spread_patterns = [
            # $XXX/$YYY format for spreads
            r'\$(\d{2,4})/\$(\d{2,4})',  # $500/$490
            r'\$(\d{2,4})/(\d{2,4})',    # $500/490
            r'(\d{2,4})/(\d{2,4})',      # 500/490
        ]
        
        # Look for spread strikes first
        for i, pattern in enumerate(spread_patterns, 1):
            matches = re.findall(pattern, text)
            print(f"DEBUG: Spread pattern {i} matches: {matches}")
            
            for match in matches:
                try:
                    if len(match) == 2:
                        strike1, strike2 = int(match[0]), int(match[1])
                        # Reasonable strike range
                        if 10 <= strike1 <= 9999 and 10 <= strike2 <= 9999:
                            result = f"${strike1}/${strike2}"
                            print(f"DEBUG: Found spread strikes: {result}")
                            return result
                except ValueError:
                    continue
        
        # If no spreads found, look for single strike patterns
        single_strike_patterns = [
            # $XXX strike patterns (whole numbers only)
            r'\$(\d{2,4})(?!\.\d)(?!/)',  # $300 but not $300.50 or $300/490
            
            # Context-specific patterns
            r'(\d{2,4})\s*strike',   # "300 strike" or "300strike"
            r'strike\s*\$?(\d{2,4})(?!\.\d)(?!/)',  # "strike $300" or "strike 300"
            
            # Option chain format patterns
            r'(\d{2,4})[CP](?:\s|$)',  # "300C" or "400P" (call/put designation)
        ]
        
        # Find single strike candidates
        potential_strikes = []
        
        for i, pattern in enumerate(single_strike_patterns, 1):
            matches = re.findall(pattern, text)
            print(f"DEBUG: Single strike pattern {i} matches: {matches}")
            
            for match in matches:
                try:
                    strike_value = int(match)
                    # Reasonable strike range (avoid tiny numbers that might be quantities)
                    if 10 <= strike_value <= 9999:
                        potential_strikes.append(strike_value)
                        print(f"DEBUG: Valid single strike candidate: {strike_value}")
                except ValueError:
                    continue
        
        if potential_strikes:
            # Remove duplicates and sort
            unique_strikes = sorted(list(set(potential_strikes)))
            
            # If multiple strikes found, try to pick the most likely one
            if len(unique_strikes) == 1:
                selected_strike = unique_strikes[0]
            else:
                # Multiple strikes - pick the first reasonable one
                # Could be enhanced with more context logic if needed
                selected_strike = unique_strikes[0]
                print(f"DEBUG: Multiple single strikes found {unique_strikes}, selected: {selected_strike}")
            
            result = f"${selected_strike}"
            print(f"DEBUG: Selected single strike price: {result}")
            return result
        
        print(f"DEBUG: No strike price found")
        return None
    
    def _extract_expiration_date(self, text: str) -> str:
        """
        Extract expiration date in monthNumber/dayNumber format
        
        Examples:
        - "expiring 8/29" → "8/29"
        - "8/30 expiry" → "8/30"
        - "exp 9/15" → "9/15"
        
        Args:
            text: Full text to analyze
            
        Returns:
            Expiration date as string (e.g., "8/29") or None
        """
        import re
        
        print(f"DEBUG: Extracting expiration date from: '{text}'")
        
        # Look for date patterns in M/D or MM/DD format
        date_patterns = [
            # "expiring M/D" or "expiring MM/DD"
            r'expiring\s+(\d{1,2}/\d{1,2})',
            
            # "exp M/D" or "exp MM/DD"
            r'exp\s+(\d{1,2}/\d{1,2})',
            
            # "expiry M/D" or "expiry MM/DD"
            r'expiry\s+(\d{1,2}/\d{1,2})',
            
            # "M/D expiry" or "MM/DD expiry"
            r'(\d{1,2}/\d{1,2})\s+expiry',
            
            # "M/D exp" or "MM/DD exp"
            r'(\d{1,2}/\d{1,2})\s+exp',
            
            # Standalone date patterns (be careful not to match prices)
            r'(?:^|\s)(\d{1,2}/\d{1,2})(?:\s|$)',
        ]
        
        text_lower = text.lower()
        
        for i, pattern in enumerate(date_patterns, 1):
            matches = re.findall(pattern, text_lower)
            print(f"DEBUG: Date pattern {i} matches: {matches}")
            
            for match in matches:
                # Validate the date format
                try:
                    month, day = match.split('/')
                    month_int = int(month)
                    day_int = int(day)
                    
                    # Basic validation: reasonable month and day ranges
                    if 1 <= month_int <= 12 and 1 <= day_int <= 31:
                        result = match
                        print(f"DEBUG: Valid expiration date found: {result}")
                        return result
                except (ValueError, AttributeError):
                    continue
        
        print(f"DEBUG: No expiration date found")
        return None
    
    def _extract_quantity(self, text: str) -> str:
        """Extract quantity/shares information"""
        import re
        
        # Look for quantity patterns
        quantity_patterns = [
            r'(\d+)\s+shares',
            r'(\d+)\s+contracts',
            r'(\d+)x',
            r'qty\s*(\d+)',
        ]
        
        text_lower = text.lower()
        for pattern in quantity_patterns:
            matches = re.findall(pattern, text_lower)
            if matches:
                return matches[0]
        
        return None
    
    def _extract_ticker(self, message: str, subtext: str) -> str:
        """Extract ticker symbol from the notification"""
        # Look in message first, then subtext
        text_to_search = f"{message} {subtext}".upper()
        
        # Common ticker patterns (this can be expanded)
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
    
    def _extract_action(self, subtext: str) -> str:
        """Extract trading action from subtext"""
        if not subtext:
            return "UNKNOWN"
            
        subtext_lower = subtext.lower()
        
        if any(word in subtext_lower for word in ["buy", "long", "enter", "bullish"]):
            return "BUY"
        elif any(word in subtext_lower for word in ["sell", "short", "exit", "bearish"]):
            return "SELL"
        elif any(word in subtext_lower for word in ["hold", "wait", "watch"]):
            return "HOLD"
        
        return "UNKNOWN"
    
    def _extract_price(self, subtext: str) -> str:
        """Extract price information from subtext"""
        if not subtext:
            return "N/A"
            
        import re
        # Look for price patterns like $123.45, 123.45, etc.
        price_patterns = [
            r'\$(\d+\.?\d*)',
            r'(\d+\.\d+)',
            r'(\d+)'
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, subtext)
            if matches:
                return f"${matches[0]}"
        
        return "N/A"
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()
