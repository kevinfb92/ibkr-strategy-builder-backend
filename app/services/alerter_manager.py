"""
Alerter management service - routes notifications to appropriate handlers
"""
from typing import Dict, Any, Optional
import logging
import asyncio

from .alerter_config import AlerterConfig, AlerterType
from .handlers import (
    RealDayTradingHandler,
    NyrlethHandler,
    DemslayerSpxAlertsHandler,
    ProfAndKianAlertsHandler
)
from .handlers import RobinDaHoodHandler
from .telegram_service import telegram_service

logger = logging.getLogger(__name__)

class AlerterManager:
    """Manages routing of notifications to specific alerter handlers"""
    
    def __init__(self):
        self.handlers = {
            AlerterType.REAL_DAY_TRADING.value: RealDayTradingHandler(),
            AlerterType.NYRLETH.value: NyrlethHandler(),
            AlerterType.DEMSLAYER_SPX_ALERTS.value: DemslayerSpxAlertsHandler(),
            AlerterType.PROF_AND_KIAN_ALERTS.value: ProfAndKianAlertsHandler()
        }
        # Add RobinDaHood handler mapped to its canonical supported name
        # The canonical alerter name is 'robindahood-alerts' (ensured in AlerterConfig)
        try:
            self.handlers['robindahood-alerts'] = RobinDaHoodHandler()
        except Exception:
            logger.debug('Failed to initialize RobinDaHoodHandler')
        
    async def process_notification(self, title: str, message: str, subtext: str) -> Dict[str, Any]:
        """
        Process notification by routing to appropriate alerter handler
        
        Args:
            title: The notification title
            message: The message/ticker info
            subtext: The main notification content
            
        Returns:
            Dict with processed notification data
        """
        try:
            # First, check if we need to extract alerter from message format
            extracted_alerter, cleaned_message = AlerterConfig.extract_alerter_from_message(message)
            
            # Use cleaned message if extraction occurred
            if extracted_alerter:
                message = cleaned_message
                logger.info(f"Extracted alerter '{extracted_alerter}' from message, cleaned message: '{message}'")
            
            # Detect which alerter this notification is from
            detected_alerter = AlerterConfig.detect_alerter(title, message if not extracted_alerter else f"{extracted_alerter}: {message}")
            
            if not detected_alerter:
                # Unknown alerter - use generic processing
                logger.warning(f"Unknown alerter detected. Title: '{title}', Message: '{message}'")
                return self._process_generic_notification(title, message, subtext)
            
            # Route to specific handler
            handler = self.handlers.get(detected_alerter)
            if not handler:
                logger.error(f"No handler found for alerter: {detected_alerter}")
                return self._process_generic_notification(title, message, subtext)
            
            logger.info(f"Routing notification to {detected_alerter} handler")
            result = handler.process_notification(title, message, subtext)
            
            # DEBUG: Check if contract was retrieved from API
            if result.get("data"):
                processed_data = result.get("data", {})
                print(f"🔍 DEBUG: Handler result for {detected_alerter}:")
                print(f"   Contract Info: {processed_data.get('contract_info')}")
                print(f"   Contract To Use: {processed_data.get('contract_to_use')}")
                print(f"   Contract Details (IBKR): {processed_data.get('contract_details')}")
                print(f"   Spread Info (IBKR): {processed_data.get('spread_info')}")
                print(f"   Ticker (IBKR): {processed_data.get('ticker')}")
                print(f"   Stored Contract: {processed_data.get('stored_contract')}")
                print(f"   Storage Stats: {processed_data.get('storage_stats')}")
                
                # Specific check for IBKR API retrieval
                contract_details = processed_data.get('contract_details')
                if contract_details:
                    print(f"✅ IBKR CONTRACT API SUCCESS: Retrieved contract details")
                    print(f"   IBKR ConID: {contract_details.get('conid')}")
                    print(f"   IBKR Symbol: {contract_details.get('symbol')}")
                    print(f"   IBKR Strike: {contract_details.get('strike')}")
                    print(f"   IBKR Right: {contract_details.get('right')}")
                    print(f"   IBKR Exchange: {contract_details.get('exchange')}")
                else:
                    print(f"❌ IBKR CONTRACT API FAILED: No contract details retrieved")
                
                spread_info = processed_data.get('spread_info')
                if spread_info and spread_info.get('bid') != 'N/A':
                    print(f"✅ IBKR MARKET DATA SUCCESS: Retrieved pricing")
                    print(f"   Bid: {spread_info.get('bid')}")
                    print(f"   Ask: {spread_info.get('ask')}")
                    print(f"   Last: {spread_info.get('last')}")
                    print(f"   Spread: {spread_info.get('spread')}")
                else:
                    print(f"❌ IBKR MARKET DATA FAILED: No pricing retrieved")
                
                print(f"=" * 60)
            
            # Add routing info to result
            if result.get("data"):
                result["data"]["routed_to"] = detected_alerter
                result["data"]["handler_used"] = handler.__class__.__name__
            
            # Send to Telegram if processing was successful
            if result.get("success"):
                telegram_result = await self._send_telegram_alert(
                    detected_alerter, title, message, subtext, result.get("data", {})
                )
                result["data"]["telegram_sent"] = telegram_result
            
            return result
            
        except Exception as e:
            logger.error(f"Error in alerter manager: {e}")
            return {
                "success": False,
                "message": f"Alerter manager error: {str(e)}",
                "data": {
                    "error_type": "alerter_manager_error",
                    "original_title": title,
                    "original_message": message,
                    "original_subtext": subtext
                }
            }
    
    async def _send_telegram_alert(self, alerter_name: str, title: str, message: str, 
                                  subtext: str, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        # print("Sending Telegram alert...")
        """Send alert to Telegram with Buy/Sell buttons"""
        try:
            # Extract ticker from processed data if available, fallback to subtext (ticker)
            ticker = processed_data.get('ticker', subtext)

            # Centralized enrichment: ensure processed_data contains open-position info
            # for all alerters (except demslayer-spx-alerts) so Telegram formatting is consistent.
            try:
                if alerter_name != 'demslayer-spx-alerts':
                    await self._enrich_processed_data_with_ibkr(alerter_name, title, message, subtext, processed_data)
            except Exception:
                # Best-effort enrichment; don't block sending on failures
                pass
            
            # Format additional info from processed data
            additional_info = []
            
            # Add specific info based on processed data
            if 'action' in processed_data:
                additional_info.append(f"Action: {processed_data['action']}")
            if 'price' in processed_data and processed_data['price'] != 'N/A':
                additional_info.append(f"Price: {processed_data['price']}")
            if 'signal_type' in processed_data:
                additional_info.append(f"Signal: {processed_data['signal_type']}")
            if 'confidence' in processed_data:
                additional_info.append(f"Confidence: {processed_data['confidence']}")
            if 'entry_point' in processed_data and processed_data['entry_point'] != 'N/A':
                additional_info.append(f"Entry: {processed_data['entry_point']}")
            if 'target' in processed_data and processed_data['target'] != 'N/A':
                additional_info.append(f"Target: {processed_data['target']}")
            
            # Special handling for demslayer-spx-alerts
            if alerter_name == "demslayer-spx-alerts":
                self._add_demslayer_info(additional_info, processed_data)
            
            additional_info_str = " | ".join(additional_info) if additional_info else ""
            
            # Combine message and subtext for display
            combined_message = message
            if subtext and subtext.strip() and subtext != ticker and subtext != "NO_SUBTEXT":
                # Only append subtext if it's different from ticker, not empty, and not placeholder
                combined_message = f"{message}\n{subtext.strip()}"
            
            # Try a lightweight auto-enrichment: if processed_data lacks a ticker,
            # ask the TelegramService to find an open IBKR position mentioned in
            # the combined message. If found, set processed_data['ticker'] so
            # the downstream send_trading_alert logic can enrich the alert.
            try:
                # Skip auto-enrichment for DeMsLayer-style alerts; those have
                # specialized stored-contract handling and we don't want the
                # generic position-matcher to override it.
                try:
                    is_dem = False
                    if telegram_service:
                        is_dem = telegram_service._is_demspxslayer(alerter_name, processed_data, title=title, message=message)
                except Exception:
                    is_dem = False

                if (not processed_data.get('ticker')) and telegram_service and not is_dem:
                    try:
                        matched = telegram_service._find_matching_open_position(combined_message)
                        if matched:
                            # Only auto-enrich from matched open positions if that
                            # matched position's ticker is actually associated with
                            # this alerter in our alerter_stock_storage. This avoids
                            # leaking positions/close-buttons across unrelated
                            # alerters (e.g., showing SPY from RobinDaHood on an NFLX alert).
                            try:
                                from app.services.alerter_stock_storage import alerter_stock_storage
                                # Resolve the matched symbol/ticker candidate
                                symbol_guess = matched.get('_matched_symbol') or matched.get('symbol') or matched.get('contractDesc')
                                symbol_key = None
                                if isinstance(symbol_guess, str):
                                    # For a contractDesc like 'SPY SEP2025 659 C' take first token as ticker
                                    symbol_key = symbol_guess.split()[0].upper()
                                # If we cannot determine a symbol_key, don't enrich
                                can_enrich = False
                                if symbol_key:
                                    try:
                                        can_enrich = alerter_stock_storage.is_stock_already_alerted(detected_alerter, symbol_key)
                                    except Exception:
                                        can_enrich = False

                                if not can_enrich:
                                    logger.debug(f"Skipping auto-enrichment: matched position '{symbol_guess}' is not registered for alerter '{alerter_name}'")
                                else:
                                    # Populate processed_data with IBKR-friendly fields so
                                    # send_trading_alert will include the IBKR position block
                                    try:
                                        if symbol_guess:
                                            processed_data.setdefault('ticker', symbol_guess)

                                        # Map common position fields (best-effort)
                                        try:
                                            pos_qty = matched.get('position') or matched.get('pos') or matched.get('positionSize') or 0
                                            try:
                                                pos_qty_val = int(pos_qty)
                                            except Exception:
                                                try:
                                                    pos_qty_val = int(float(pos_qty))
                                                except Exception:
                                                    pos_qty_val = 0
                                        except Exception:
                                            pos_qty_val = 0

                                        processed_data['ibkr_position_size'] = abs(pos_qty_val)
                                        processed_data['ibkr_unrealized_pnl'] = matched.get('unrealizedPnl') or matched.get('unrealized') or matched.get('unrealized_pnl')
                                        processed_data['ibkr_realized_pnl'] = matched.get('realizedPnl') or matched.get('realized') or matched.get('realized_pnl')
                                        processed_data['ibkr_market_value'] = matched.get('marketValue') or matched.get('mktValue') or matched.get('market_value')
                                        processed_data['ibkr_avg_price'] = matched.get('avgPrice') or matched.get('avgCost') or matched.get('avg_price')
                                        processed_data['ibkr_current_price'] = matched.get('currentPrice') or matched.get('mktPrice') or (matched.get('market_data') or {}).get('last') or matched.get('last')
                                        processed_data['show_close_position_button'] = True

                                        # Attach a contract-ish dict if available so formatting helpers work
                                        cd = matched.get('contract') or matched.get('contract_details') or matched.get('contractDetails')
                                        if isinstance(cd, dict):
                                            processed_data.setdefault('contract_details', cd)

                                        logger.info(f"Auto-enriched ticker from message using open positions: {symbol_guess}")
                                    except Exception as e:
                                        logger.debug(f"Error enriching processed_data from matched position: {e}")
                            except Exception as e:
                                logger.debug(f"Auto-enrichment stock storage check failed: {e}")
                    except Exception as e:
                        logger.debug(f"Ticker auto-enrichment failed: {e}")
            except Exception:
                # Best-effort only; don't block sending on enrichment failures
                pass

            # Send to Telegram
            print(f"DEBUG: About to send Telegram alert - alerter: {alerter_name}")
            telegram_result = await telegram_service.send_trading_alert(
                alerter_name=alerter_name,
                message=combined_message,  # Combined message and subtext
                ticker=ticker,    # Extracted from processed data or fallback to subtext
                additional_info=additional_info_str,
                processed_data=processed_data  # Pass processed data for enhanced formatting
            )
            print(f"DEBUG: Telegram result - success: {telegram_result.get('success', 'unknown')}")
            
            return telegram_result
            
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")
            return {
                "success": False,
                "message": f"Failed to send Telegram alert: {str(e)}",
                "error": str(e)
            }
    
    def _add_demslayer_info(self, additional_info: list, processed_data: dict):
        """Add demslayer-specific contract and position info to additional_info"""
        try:
            # For demslayer, we don't add to additional_info since we're removing the Details section
            # The enhanced display will be handled directly in the Telegram service
            pass
                
        except Exception as e:
            logger.error(f"Error adding demslayer info: {e}")
            # Don't add error info for demslayer to keep it clean

    def _process_generic_notification(self, title: str, message: str, subtext: str) -> Dict[str, Any]:
        """Process notification with generic handler when alerter is unknown"""
        logger.info("Processing with generic handler")
        
        return {
            "success": True,
            "message": "Processed with generic handler (unknown alerter)",
            "data": {
                "alerter": "UNKNOWN",
                "handler_used": "Generic",
                "original_title": title,
                "original_message": message,
                "original_subtext": subtext,
                "processed": True,
                "timestamp": self._get_timestamp(),
                "warning": "Unknown alerter - processed with generic handler"
            }
        }
    
    def get_supported_alerters(self) -> Dict[str, Any]:
        """Get information about supported alerters"""
        return {
            "supported_alerters": AlerterConfig.get_supported_alerters(),
            "handler_count": len(self.handlers),
            "handlers": {
                alerter: handler.__class__.__name__ 
                for alerter, handler in self.handlers.items()
            }
        }
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()

    async def _enrich_processed_data_with_ibkr(self, alerter_name: str, title: str, message: str, subtext: str, processed_data: Dict[str, Any]):
        """Best-effort IBKR enrichment to populate open-position fields used by Telegram.

        This centralizes the logic so all alerters (except demslayer-spx-alerts) have
        consistent behavior for showing close buttons and estimated P/L.
        """
        try:
            # Keep existing processed_data if provided
            if processed_data is None:
                processed_data = {}

            # If the handler already populated position info, skip
            if processed_data.get('ibkr_position_size'):
                return

            # Determine ticker candidate
            ticker_candidate = processed_data.get('ticker') or (subtext if subtext and subtext != 'NO_SUBTEXT' else None) or message
            if not ticker_candidate:
                return

            # Ask IBKR for formatted positions and try to match
            try:
                from app.services.ibkr_service import IBKRService
                ibkr = IBKRService()
                for p in (ibkr.get_formatted_positions() or []):
                    sec_type = (p.get('secType') or '').upper()
                    symbol = (p.get('symbol') or '')
                    try:
                        pos_qty = int(p.get('position', 0))
                    except Exception:
                        pos_qty = 0
                    if sec_type == 'OPT' and (processed_data.get('ticker') or '').upper() in str(symbol).upper() and pos_qty != 0:
                        processed_data['ibkr_position_size'] = abs(pos_qty)
                        processed_data['ibkr_unrealized_pnl'] = p.get('unrealizedPnl')
                        processed_data['ibkr_realized_pnl'] = p.get('realizedPnl')
                        processed_data['ibkr_market_value'] = p.get('marketValue') or p.get('mktValue')
                        processed_data['ibkr_avg_price'] = p.get('avgPrice') or p.get('avgCost')
                        processed_data['ibkr_current_price'] = p.get('currentPrice') or p.get('mktPrice')
                        processed_data['show_close_position_button'] = True
                        # Build option_contracts row for downstream formatting
                        processed_data.setdefault('option_contracts', [])
                        processed_data['option_contracts'].append({
                            'symbol': symbol,
                            'ticker': processed_data.get('ticker') or symbol.split()[0],
                            'strike': p.get('strike'),
                            'side': 'CALL' if (p.get('right') or '').upper().startswith('C') else 'PUT',
                            'quantity': abs(pos_qty),
                            'unrealizedPnl': p.get('unrealizedPnl'),
                            'realizedPnl': p.get('realizedPnl'),
                            'marketValue': p.get('marketValue') or p.get('mktValue'),
                            'avgPrice': p.get('avgPrice') or p.get('avgCost'),
                            'currentPrice': p.get('currentPrice') or p.get('mktPrice')
                        })
                        break
            except Exception:
                # Best-effort only
                return
        except Exception:
            return

# Global instance
alerter_manager = AlerterManager()
