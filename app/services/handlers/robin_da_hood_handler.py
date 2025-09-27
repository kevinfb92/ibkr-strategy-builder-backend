"""
Robin Da Hood alerts handler

Parses messages for patterns like: "SPY 647C @.68 9/5" and stores contract when valid.
"""
from typing import Dict, Any, Optional
import logging
import re
from datetime import datetime
from ..ibkr_service import IBKRService
from ..contract_storage import contract_storage

logger = logging.getLogger(__name__)


class RobinDaHoodHandler:
    """Handler for RobinDaHood notifications"""

    def __init__(self):
        self.alerter_name = "RobinDaHood"
        # initialize IBKR service lazily for compatibility with test loader
        try:
            self.ibkr_service = IBKRService()
        except Exception:
            self.ibkr_service = None

    def process_notification(self, title: str, message: str, subtext: str) -> Dict[str, Any]:
        """Process a RobinDaHood notification and attempt to discover option contracts.

        This implementation attempts to resolve contract details via IBKR and
        reconcile the discovered conid with any live positions so that the
        conid recorded at send-time matches the account's open position conid.
        """
        logger.info(f"Processing {self.alerter_name} notification")
        processed_data = {
            "alerter": self.alerter_name,
            "original_title": title,
            "original_message": message,
            "original_subtext": subtext,
            "processed": True,
            "contract_info": None,
            "contract_details": None,
            "spread_info": None,
            "ticker": None,
            "show_close_position_button": False,
            "ibkr_position_size": None,
            "option_contracts": [],
            "timestamp": datetime.now().isoformat()
        }

        # 1) Try to extract explicit contract info from the message
        try:
            contract_info = self._extract_contract_info(title, message)
        except Exception:
            contract_info = None

        if contract_info:
            logger.info(f"RobinDaHood: extracted contract_info: {contract_info}")
            # validate symbol exists via IBKR
            symbol = contract_info.get('symbol')
            valid = False
            try:
                cd = self.ibkr_service.search_contract_by_symbol(symbol)
                if cd is not None:
                    if hasattr(cd, 'data') and cd.data:
                        valid = True
                    elif isinstance(cd, (dict, list)) and cd:
                        valid = True
                if not valid:
                    cd2 = self.ibkr_service.search_contract_by_symbol(symbol, sec_type='STK')
                    if cd2 is not None and ((hasattr(cd2, 'data') and cd2.data) or (isinstance(cd2, (dict, list)) and cd2)):
                        valid = True
            except Exception:
                valid = False

            if valid:
                try:
                    details = self.ibkr_service.get_option_contract_details(
                        symbol=contract_info.get('symbol'),
                        strike=contract_info.get('strike'),
                        right=(contract_info.get('side') or '')[:1].upper() if contract_info.get('side') else None,
                        expiry=contract_info.get('expiry')
                    )
                except Exception:
                    details = None

                if details:
                    # Try to reconcile with live formatted positions: prefer a live
                    # position's conid if present for the same symbol to avoid
                    # conid mismatches between send-time lookup and account positions.
                    try:
                        fmt_pos = self.ibkr_service.get_formatted_positions() or []
                        for ppos in (fmt_pos or []):
                            try:
                                p_symbol = (ppos.get('symbol') or '')
                                pos_qty = int(abs(int(ppos.get('position', 0))))
                            except Exception:
                                p_symbol = None
                                pos_qty = 0
                            if pos_qty > 0 and p_symbol and details.get('symbol') and details.get('symbol').upper() in p_symbol.upper():
                                live_conid = ppos.get('conid') or ppos.get('contractId') or ppos.get('conId')
                                if live_conid:
                                    details['conid'] = live_conid
                                    logger.debug('Overriding contract_details conid with live position conid: %s', live_conid)
                                    break
                    except Exception:
                        pass

                    processed_data['contract_details'] = details
                    try:
                        processed_data['conid_at_send'] = details.get('conid')
                    except Exception:
                        pass

                    processed_data['contract_info'] = contract_info
                    # attempt to fetch market data for the discovered contract
                    try:
                        processed_data['spread_info'] = self.ibkr_service.get_option_market_data(details)
                    except Exception:
                        processed_data['spread_info'] = None

                    # Save validated contract to storage
                    try:
                        contract_storage.store_contract(self.alerter_name, {
                            'symbol': details.get('symbol'),
                            'strike': details.get('strike'),
                            'side': 'CALL' if (details.get('right') or '').upper().startswith('C') else 'PUT',
                            'expiry': details.get('expiry')
                        })
                    except Exception:
                        pass

                    # Populate option_contracts and position size from formatted positions
                    try:
                        fmt_pos = self.ibkr_service.get_formatted_positions() or []
                        for p in (fmt_pos or []):
                            try:
                                if details.get('symbol') and details.get('symbol').upper() in (p.get('symbol') or '').upper():
                                    pos_qty = int(abs(int(p.get('position', 0))))
                                    if pos_qty > 0:
                                        processed_data['ibkr_position_size'] = pos_qty
                                        processed_data['show_close_position_button'] = True
                                        processed_data.setdefault('option_contracts', []).append({
                                            'symbol': p.get('symbol'),
                                            'ticker': details.get('symbol'),
                                            'conid': p.get('conid'),
                                            'strike': details.get('strike'),
                                            'side': 'CALL' if (details.get('right') or '').upper().startswith('C') else 'PUT',
                                            'quantity': pos_qty,
                                            'unrealizedPnl': p.get('unrealizedPnl'),
                                            'realizedPnl': p.get('realizedPnl'),
                                            'marketValue': p.get('marketValue') or p.get('mktValue'),
                                            'avgPrice': p.get('avgPrice') or p.get('avgCost'),
                                            'currentPrice': p.get('currentPrice') or p.get('mktPrice')
                                        })
                                        break
                            except Exception:
                                continue
                    except Exception:
                        pass

        # 2) If no explicit contract_info or contract_details, attempt stored contract lookup
        if not processed_data.get('contract_details'):
            try:
                stored = contract_storage.get_contract(self.alerter_name)
            except Exception:
                stored = None

            if stored:
                processed_data['stored_contract'] = stored
                try:
                    processed_data.setdefault('ticker', stored.get('symbol'))
                except Exception:
                    pass
                try:
                    processed_data['storage_stats'] = contract_storage.get_storage_stats()
                except Exception:
                    processed_data['storage_stats'] = None

                try:
                    details = self.ibkr_service.get_option_contract_details(
                        symbol=stored.get('symbol'),
                        strike=stored.get('strike'),
                        right=(stored.get('side') or '')[:1].upper() if stored.get('side') else None,
                        expiry=stored.get('expiry')
                    )
                except Exception:
                    details = None

                if details:
                    # reconcile with live positions as above
                    try:
                        fmt_pos = self.ibkr_service.get_formatted_positions() or []
                        for ppos in (fmt_pos or []):
                            try:
                                p_symbol = (ppos.get('symbol') or '')
                                pos_qty = int(abs(int(ppos.get('position', 0))))
                            except Exception:
                                p_symbol = None
                                pos_qty = 0
                            if pos_qty > 0 and p_symbol and details.get('symbol') and details.get('symbol').upper() in p_symbol.upper():
                                live_conid = ppos.get('conid') or ppos.get('contractId') or ppos.get('conId')
                                if live_conid:
                                    details['conid'] = live_conid
                                    logger.debug('Stored-contract path: overriding details.conid with live position conid: %s', live_conid)
                                    break
                    except Exception:
                        pass

                    processed_data['contract_details'] = details
                    processed_data['contract_to_use'] = details
                    try:
                        processed_data['conid_at_send'] = details.get('conid')
                    except Exception:
                        pass
                    try:
                        processed_data['spread_info'] = self.ibkr_service.get_option_market_data(details)
                    except Exception:
                        processed_data['spread_info'] = None

                    # build option_contracts from formatted positions
                    try:
                        fmt_pos = self.ibkr_service.get_formatted_positions() or []
                        for p in (fmt_pos or []):
                            try:
                                pos_symbol = (p.get('symbol') or p.get('contractDesc') or '')
                                if stored.get('symbol') and stored.get('symbol').upper() in pos_symbol.upper():
                                    pos_qty = int(abs(int(p.get('position', 0))))
                                    if pos_qty > 0:
                                        processed_data['ibkr_position_size'] = pos_qty
                                        processed_data['show_close_position_button'] = True
                                        processed_data.setdefault('option_contracts', []).append({
                                            'symbol': pos_symbol,
                                            'ticker': stored.get('symbol'),
                                            'conid': p.get('conid'),
                                            'strike': stored.get('strike'),
                                            'side': stored.get('side'),
                                            'quantity': pos_qty,
                                            'unrealizedPnl': p.get('unrealizedPnl'),
                                            'realizedPnl': p.get('realizedPnl'),
                                            'marketValue': p.get('marketValue') or p.get('mktValue'),
                                            'avgPrice': p.get('avgPrice') or p.get('avgCost'),
                                            'currentPrice': p.get('currentPrice') or p.get('mktPrice')
                                        })
                                        break
                            except Exception:
                                continue
                    except Exception:
                        pass

        # Ensure contract_info field always present
        processed_data['contract_info'] = processed_data.get('contract_info') or contract_info if 'contract_info' in locals() else None

        return {'success': True, 'message': f"Processed {self.alerter_name} notification", 'data': processed_data}

    def _extract_contract_info(self, title: str, message: str) -> Optional[Dict[str, Any]]:
        """Extract a simple option token from title+message text.

        Looks for patterns like: 'SPY 647C', 'SPY 647 C', optionally followed by a M/D
        expiry like '9/5'. Returns None when nothing parseable is found.
        """
        search_text = f"{title} {message}" if title else (message or '')
        if not search_text:
            return None

        # match strike + side (C or P)
        m = re.search(r"(\d+(?:\.\d+)?)\s*([CP])\b", search_text, re.IGNORECASE)
        if not m:
            return None

        strike_raw = m.group(1)
        side = m.group(2).upper()

        # preceding word as symbol
        start = m.start()
        before = search_text[:start].strip()
        parts = before.split()
        if not parts:
            return None
        symbol = parts[-1].upper()

        # look for a M/D date after the strike token
        after = search_text[m.end():]
        date_match = re.search(r"(\b\d{1,2}/\d{1,2}\b)", after)
        expiry = date_match.group(1) if date_match else None

        try:
            strike_val = float(strike_raw)
        except Exception:
            strike_val = strike_raw

        return {
            'symbol': symbol,
            'strike': strike_val,
            'side': 'CALL' if side == 'C' else 'PUT',
            'expiry': expiry,
            'found_in': 'title_or_message'
        }
