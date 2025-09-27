"""
Demslayer SPX Alerts handler
Specialized handler for 0DTE SPX options alerts from demslayer-spx-alerts
"""
from typing import Dict, Any, Optional
import logging
import re
from datetime import datetime, date
from ..ibkr_service import IBKRService
from ..contract_storage import contract_storage

logger = logging.getLogger(__name__)

class DemslayerSpxAlertsHandler:
    """Handler for demslayer-spx-alerts notifications"""
    
    def __init__(self):
        self.alerter_name = "demslayer-spx-alerts"
        # Initialize IBKR service for real contract data
        self.ibkr_service = IBKRService()
        # Load stored contract on startup
        self._load_stored_contract()
    
    def _load_stored_contract(self):
        """Load the stored contract from persistent storage"""
        try:
            # Clean up expired contracts first
            contract_storage.cleanup_expired_contracts()
            
            # Load the contract for this alerter
            stored_contract = contract_storage.get_contract(self.alerter_name)
            
            if stored_contract and not contract_storage.is_contract_expired(self.alerter_name):
                print(f"DEBUG: Loaded stored contract for {self.alerter_name}: {stored_contract}")
                logger.info(f"Loaded stored contract for {self.alerter_name}")
                return stored_contract
            else:
                print(f"DEBUG: No valid stored contract found for {self.alerter_name}")
                return None
                
        except Exception as e:
            logger.error(f"Error loading stored contract: {e}")
            print(f"DEBUG: Error loading stored contract: {e}")
            return None
    
    def _save_contract(self, contract_info: Dict[str, Any]):
        """Save contract to persistent storage"""
        try:
            contract_storage.store_contract(self.alerter_name, contract_info)
            print(f"DEBUG: Saved contract to persistent storage: {contract_info}")
        except Exception as e:
            logger.error(f"Error saving contract: {e}")
            print(f"DEBUG: Error saving contract: {e}")
    
    def get_stored_contract(self) -> Optional[Dict[str, Any]]:
        """Get the current stored contract"""
        return contract_storage.get_contract(self.alerter_name)
        # Load stored contract on startup
        self._load_stored_contract()
    
    def process_notification(self, title: str, message: str, subtext: str) -> Dict[str, Any]:
        """
        Process demslayer-spx-alerts notification
        All alerts are for SPX 0DTE options (buying calls or puts)
        
        Args:
            title: The notification title
            message: The actual message content
            subtext: Additional info (usually %evtprm4 if no subtext)
            
        Returns:
            Dict with processed notification data
        """
        try:
            logger.info(f"Processing {self.alerter_name} notification")
            print(f"DEBUG: Processing demslayer notification")
            print(f"DEBUG: Title: {title}")
            print(f"DEBUG: Message: {message}")
            print(f"DEBUG: Subtext: {subtext}")
            
            # Extract contract information from both message AND subtext
            contract_info = self._extract_contract_info(message, subtext)
            print(f"DEBUG: Extracted contract_info: {contract_info}")
            
            # Get SPX position from IBKR
            spx_position = self._get_spx_position()
            print(f"DEBUG: SPX position: {spx_position}")
            
            # Determine contract to use (from message/subtext, stored, or none)
            contract_to_use = self._determine_contract(contract_info)
            print(f"DEBUG: Contract to use: {contract_to_use}")

            # Prepare a baseline processed_data early so downstream blocks can update it
            processed_data = {
                "alerter": self.alerter_name,
                "original_title": title,
                "original_message": message,
                "original_subtext": subtext,
                "processed": True,
                "instrument": "SPX",
                "option_type": "0DTE",
                "action": "BUY",  # Always buying for demslayer
                "contract_info": contract_info,
                "stored_contract": self.get_stored_contract(),  # Get from persistent storage
                "contract_to_use": None,
                "contract_details": None,
                "spread_info": None,
                "ticker": None,  # Use IBKR-formatted ticker when available
                "has_spx_position": spx_position is not None,
                "spx_position": spx_position,
                "timestamp": datetime.now().isoformat(),
                "storage_stats": contract_storage.get_storage_stats()  # Include storage info
            }

            # Get real IBKR contract details
            contract_details = None
            spread_info = None
            ticker_info = None
            
            if contract_to_use:
                print(f"DEBUG: Getting IBKR contract details for: {contract_to_use}")
                contract_details = self._get_contract_details(contract_to_use)
                print(f"DEBUG: IBKR contract details: {contract_details}")
                
                if contract_details:
                    spread_info = self._get_contract_spread(contract_details)
                    print(f"DEBUG: Contract spread info: {spread_info}")
                    
                    # Create ticker info from IBKR data
                    ticker_info = self._format_ticker_from_ibkr(contract_details, spread_info)
                    print(f"DEBUG: Formatted ticker from IBKR: {ticker_info}")
                    # Save contract to persistent storage now that IBKR recognizes it
                    try:
                        self._save_contract({
                            "strike": contract_details.get('strike'),
                            "side": 'CALL' if (contract_details.get('right') or '').upper().startswith('C') else 'PUT',
                            "symbol": contract_details.get('symbol', 'SPX'),
                            "expiry": contract_details.get('expiry')
                        })
                        print(f"DEBUG: Stored contract after IBKR verification: {contract_details.get('symbol')} {contract_details.get('strike')}{contract_details.get('right')} {contract_details.get('expiry')}")
                    except Exception as e:
                        logger.debug(f"Failed to save contract after IBKR verification: {e}")

                    # Check for an open position for this contract and populate IBKR position fields
                    try:
                        pos = None
                        # Look through formatted positions for a matching symbol
                        for p in (self.ibkr_service.get_formatted_positions() or []):
                            sym = (p.get('symbol') or '').upper()
                            if ticker_info and ticker_info.split()[0].upper() in sym:
                                pos = p
                                break
                        if pos:
                            print(f"DEBUG: Found IBKR position for contract: {pos}")
                            processed_spx_position = {
                                'symbol': pos.get('symbol'),
                                'position': pos.get('position'),
                                'unrealizedPnl': pos.get('unrealizedPnl'),
                                'realizedPnl': pos.get('realizedPnl'),
                                'marketValue': pos.get('marketValue') or pos.get('mktValue'),
                                'avgPrice': pos.get('avgPrice') or pos.get('avgCost'),
                                'currentPrice': pos.get('currentPrice') or pos.get('mktPrice')
                            }
                        else:
                            processed_spx_position = None
                    except Exception as e:
                        logger.debug(f"Error checking position after IBKR contract lookup: {e}")
                        processed_spx_position = None
                    
                    # Populate IBKR summary fields for send_trading_alert compatibility
                    ibkr_position_size = None
                    ibkr_unrealized = None
                    ibkr_realized = None
                    ibkr_mv = None
                    ibkr_avg = None
                    ibkr_curr = None
                    if processed_spx_position:
                        try:
                            ibkr_position_size = abs(int(processed_spx_position.get('position', 0)))
                        except Exception:
                            ibkr_position_size = processed_spx_position.get('position')
                        ibkr_unrealized = processed_spx_position.get('unrealizedPnl')
                        ibkr_realized = processed_spx_position.get('realizedPnl')
                        ibkr_mv = processed_spx_position.get('marketValue')
                        ibkr_avg = processed_spx_position.get('avgPrice')
                        ibkr_curr = processed_spx_position.get('currentPrice')

                    # Build option_contracts list in the same shape TelegramService expects
                    option_contracts = []
                    try:
                        if processed_spx_position:
                            option_contracts.append({
                                'symbol': processed_spx_position.get('symbol'),
                                'ticker': (ticker_info or contract_details.get('symbol') if contract_details else 'SPX'),
                                'strike': contract_details.get('strike') if contract_details else processed_spx_position.get('symbol'),
                                'side': 'CALL' if (contract_details and (contract_details.get('right') or '').upper().startswith('C')) else ('PUT' if (contract_details and (contract_details.get('right') or '').upper().startswith('P')) else processed_spx_position.get('position')),
                                'quantity': abs(int(processed_spx_position.get('position', 0))) if processed_spx_position.get('position') is not None else 0,
                                'unrealizedPnl': processed_spx_position.get('unrealizedPnl'),
                                'realizedPnl': processed_spx_position.get('realizedPnl'),
                                'marketValue': processed_spx_position.get('marketValue'),
                                'avgPrice': processed_spx_position.get('avgPrice'),
                                'currentPrice': processed_spx_position.get('currentPrice')
                            })
                    except Exception:
                        option_contracts = []
                    
                    # Make these available to processed_data so send_trading_alert renders the same layout
                    processed_data.update({
                        'ibkr_position_size': ibkr_position_size,
                        'ibkr_unrealized_pnl': ibkr_unrealized,
                        'ibkr_realized_pnl': ibkr_realized,
                        'ibkr_market_value': ibkr_mv,
                        'ibkr_avg_price': ibkr_avg,
                        'ibkr_current_price': ibkr_curr,
                        'show_close_position_button': bool(ibkr_position_size),
                        'option_contracts': option_contracts
                    })
            
            # Finalize processed_data with values computed above
            processed_data["contract_to_use"] = contract_to_use
            processed_data["contract_details"] = contract_details
            processed_data["spread_info"] = spread_info
            processed_data["ticker"] = ticker_info

            print(f"DEBUG: Final processed_data keys: {list(processed_data.keys())}")
            print(f"DEBUG: Final ticker value: {processed_data.get('ticker')}")

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
    
    
    def _extract_contract_info(self, message: str, subtext: str = None) -> Optional[Dict[str, Any]]:
        """
        Extract contract information from message and/or subtext
        Looks for patterns like 6480P (put) or 6480C (call)
        
        Args:
            message: The alert message
            subtext: The alert subtext (optional)
            
        Returns:
            Dict with contract info or None if no contract found
        """
        # Combine both message and subtext to search for contracts
        search_texts = []
        if message:
            search_texts.append(("message", message))
        if subtext:
            search_texts.append(("subtext", subtext))
        
        if not search_texts:
            print(f"DEBUG: No message or subtext provided")
            return None
            
        print(f"DEBUG: Extracting contract from:")
        for source, text in search_texts:
            print(f"  {source}: '{text}'")
        
        # Pattern for SPX options: 4-digit strike + C/P
        contract_pattern = r'(\d{4})([CP])'
        
        for source, text in search_texts:
            matches = re.findall(contract_pattern, text.upper())
            print(f"DEBUG: Contract pattern matches in {source}: {matches}")
            
            if matches:
                strike, side = matches[0]
                contract_info = {
                    "strike": int(strike),
                    "side": "CALL" if side == "C" else "PUT",
                    "symbol": "SPX",
                    "expiry": date.today().strftime("%Y%m%d"),  # 0DTE = today
                    "found_in": source
                }

                # Do not persist here; defer saving until we verify IBKR knows about the contract
                print(f"DEBUG: Extracted contract from {source} (not yet saved): {contract_info}")
                logger.info(f"Extracted contract from {source} (not yet saved): {contract_info}")

                return contract_info
        
        print(f"DEBUG: No contract pattern found in any source")
        return None
    
    def _determine_contract(self, contract_info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Determine which contract to use:
        1. If message has contract info, use it
        2. If no contract in message but we have stored contract, use stored
        3. If neither, return None
        
        Args:
            contract_info: Contract info extracted from current message
            
        Returns:
            Contract to use or None
        """
        if contract_info:
            print(f"DEBUG: Using contract from message: {contract_info}")
            return contract_info
        else:
            # Try to get from persistent storage
            stored_contract = self.get_stored_contract()
            if stored_contract and not contract_storage.is_contract_expired(self.alerter_name):
                print(f"DEBUG: Using stored contract: {stored_contract}")
                logger.info(f"Using stored contract: {stored_contract}")
                return stored_contract
            else:
                print(f"DEBUG: No contract specified and no valid stored contract available")
                logger.info("No contract specified and no stored contract available")
                return None
    
    def _get_spx_position(self) -> Optional[Dict[str, Any]]:
        """
        Get current SPX options position from IBKR that matches the stored contract
        
        Returns:
            Position info if found, None otherwise
        """
        try:
            if not self.ibkr_service:
                print("DEBUG: No IBKR service available for position check")
                return None
                
            print("DEBUG: Getting SPX positions from IBKR...")
            positions = self.ibkr_service.get_formatted_positions()
            print(f"DEBUG: All positions: {positions}")
            
            # Get the stored contract to match against
            stored_contract = self.get_stored_contract()
            if not stored_contract:
                print("DEBUG: No stored contract to match positions against")
                # Fall back to any SPX position
                for position in positions:
                    symbol = position.get("symbol", "").upper()
                    if "SPX" in symbol and position.get("position", 0) != 0:
                        print(f"DEBUG: Found SPX position (no contract match): {position}")
                        logger.info(f"Found SPX position (no contract match): {position}")
                        return position
                print("DEBUG: No SPX positions found")
                return None
            
            # Try to find position matching the stored contract
            # Normalize strike to match IBKR symbol text (e.g., '6500' not '6500.0')
            raw_strike = stored_contract.get('strike', '')
            try:
                if isinstance(raw_strike, float) and float(raw_strike).is_integer():
                    target_strike = str(int(raw_strike))
                else:
                    target_strike = str(raw_strike)
            except Exception:
                target_strike = str(raw_strike)
            target_side = stored_contract.get('side', '').upper()
            target_expiry = stored_contract.get('expiry', '')
            
            print(f"DEBUG: Looking for position matching: {target_strike}{target_side[0] if target_side else ''} {target_expiry}")
            
            # Look for matching SPX options positions
            for position in positions:
                symbol = position.get("symbol", "").upper()
                position_size = position.get("position", 0)
                
                if "SPX" in symbol and position_size != 0:
                    print(f"DEBUG: Checking position: {symbol}")
                    
                    # Try to extract strike and expiry from symbol
                    # Example: "SPX    AUG2025 6054 P [SPXW  250827P00006054000 100]"
                    if target_strike in symbol:
                        # Check if it's the right type (C/P)
                        if target_side.startswith('PUT') and ' P ' in symbol:
                            print(f"DEBUG: Found matching PUT position: {position}")
                            logger.info(f"Found matching PUT position: {position}")
                            return position
                        elif target_side.startswith('CALL') and ' C ' in symbol:
                            print(f"DEBUG: Found matching CALL position: {position}")
                            logger.info(f"Found matching CALL position: {position}")
                            return position
            
            print("DEBUG: No SPX positions found matching stored contract")
            return None
            
        except Exception as e:
            logger.error(f"Error getting SPX position: {e}")
            print(f"DEBUG: Error getting SPX position: {e}")
            return None
    
    def _check_spx_position(self) -> Optional[Dict[str, Any]]:
        """
        Check if we have an open SPX options position
        
        Returns:
            Position info if found, None otherwise
        """
        try:
            if not self.ibkr_service:
                return None
                
            positions = self.ibkr_service.get_formatted_positions()
            
            # Look for SPX options positions
            for position in positions:
                symbol = position.get("symbol", "").upper()
                if "SPX" in symbol and position.get("position", 0) != 0:
                    logger.info(f"Found SPX position: {position}")
                    return position
                    
            return None
            
        except Exception as e:
            logger.error(f"Error checking SPX position: {e}")
            return None
    
    def _get_contract_details(self, contract: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get detailed contract information using IBKR API
        
        Args:
            contract: Contract info dict
            
        Returns:
            Detailed contract info or None
        """
        try:
            if not self.ibkr_service:
                print("DEBUG: No IBKR service for contract details")
                return None
                
            print(f"DEBUG: Getting contract details from IBKR for: {contract}")
            
            # Use IBKR service to search for the contract
            # Format: symbol, strike, side, expiry
            symbol = contract.get("symbol", "SPX")
            strike = contract.get("strike")
            side = contract.get("side")  # "CALL" or "PUT"
            expiry = contract.get("expiry")
            
            print(f"DEBUG: Searching IBKR for contract - Symbol: {symbol}, Strike: {strike}, Side: {side}, Expiry: {expiry}")
            
            # Get contract details using ibind library through IBKR service
            contract_details = self.ibkr_service.get_option_contract_details(
                symbol=symbol,
                strike=strike,
                right=side[0] if side else "P",  # "C" or "P"
                expiry=expiry
            )
            
            print(f"DEBUG: IBKR contract details result: {contract_details}")
            logger.info(f"IBKR contract details: {contract_details}")
            
            return contract_details
            
        except Exception as e:
            logger.error(f"Error getting contract details: {e}")
            print(f"DEBUG: Error getting contract details: {e}")
            return None
    
    def _get_contract_spread(self, contract: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get current bid/ask spread for the contract
        
        Args:
            contract: Contract info dict
            
        Returns:
            Spread info or None
        """
        try:
            if not self.ibkr_service:
                print("DEBUG: No IBKR service for spread data")
                return None
                
            print(f"DEBUG: Getting spread data from IBKR for: {contract}")
            
            # Get market data for the contract
            print(f"DEBUG: About to call get_option_market_data with contract: {contract}")
            print(f"DEBUG: IBKR service object: {self.ibkr_service}")
            print(f"DEBUG: get_option_market_data method: {getattr(self.ibkr_service, 'get_option_market_data', 'METHOD NOT FOUND')}")
            
            spread_data = self.ibkr_service.get_option_market_data(contract)
            
            print(f"DEBUG: get_option_market_data returned: {spread_data}")
            print(f"DEBUG: Return type: {type(spread_data)}")
            
            print(f"DEBUG: IBKR spread data result: {spread_data}")
            logger.info(f"IBKR spread data: {spread_data}")
            
            return spread_data
            
        except Exception as e:
            logger.error(f"Error getting contract spread: {e}")
            print(f"DEBUG: Error getting contract spread: {e}")
            return None
    
    def _format_ticker_from_ibkr(self, contract_details: Dict[str, Any], spread_info: Optional[Dict[str, Any]] = None) -> str:
        """
        Format ticker information from IBKR contract data
        
        Args:
            contract_details: Contract details from IBKR
            spread_info: Optional spread information
            
        Returns:
            Formatted ticker string
        """
        try:
            print(f"DEBUG: Formatting ticker from IBKR data")
            print(f"DEBUG: Contract details: {contract_details}")
            print(f"DEBUG: Spread info: {spread_info}")
            
            if not contract_details:
                return "SPX Contract (No IBKR Data)"
            
            # Extract key information from IBKR contract
            symbol = contract_details.get("symbol", "SPX")
            strike = contract_details.get("strike", "Unknown")
            right = contract_details.get("right", "Unknown")
            expiry = contract_details.get("expiry", "0DTE")
            
            # Add market data if available
            price_info = ""
            if spread_info:
                bid = spread_info.get("bid", "N/A")
                ask = spread_info.get("ask", "N/A")
                last = spread_info.get("last", "N/A")
                
                if bid != "N/A" and ask != "N/A":
                    price_info = f" @ {bid}x{ask}"
                elif last != "N/A":
                    price_info = f" @ {last}"
            
            # Format final ticker
            ticker = f"{symbol} {strike}{right} {expiry}{price_info}"
            
            print(f"DEBUG: Formatted ticker: {ticker}")
            return ticker
            
        except Exception as e:
            logger.error(f"Error formatting ticker: {e}")
            print(f"DEBUG: Error formatting ticker: {e}")
            return "SPX Contract (Format Error)"
