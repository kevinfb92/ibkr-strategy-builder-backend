"""
IBKR service for managing client connections and API interactions
"""
from typing import Dict, List, Any, Optional
import os
import json
import logging

logger = logging.getLogger(__name__)
from ibind import IbkrClient, IbkrWsClient, IbkrWsKey
from ibind.client.ibkr_utils import OrderRequest


class IBKRService:
    """Service class for IBKR client operations"""
    
    def __init__(self):
        self.client = IbkrClient()
        # Allow tests or environments to disable the background websocket
        # thread by setting IBKR_WS_DISABLE=1 in the environment. When
        # disabled we DO NOT instantiate the IbkrWsClient to avoid any
        # background threads during unit tests.
        disable_ws = str(os.getenv('IBKR_WS_DISABLE', '')).lower() in ('1', 'true', 'yes')
        if disable_ws:
            self.ws_client = None
        else:
            try:
                self.ws_client = IbkrWsClient(ibkr_client=self.client, start=True)
            except Exception:
                # If the websocket client fails to initialize, fall back gracefully
                self.ws_client = None

        self._current_account_id = None
        # Simple per-conid minTick cache to avoid repeated secdef/info calls
        # Cache shape: { str(conid): { 'min_tick': float, 'fetched_at': timestamp } }
        self._min_tick_cache = {}

        # Try to set a current account early to avoid repeated pre-flight failures
        try:
            acct_res = None
            # prefer 'accounts' if available, otherwise fall back to portfolio_accounts
            if hasattr(self.client, 'accounts'):
                acct_res = self.client.accounts()
            else:
                acct_res = self.client.portfolio_accounts()

            if acct_res and hasattr(acct_res, 'data') and acct_res.data:
                # data shape may differ; try several common keys
                first = acct_res.data[0] if isinstance(acct_res.data, list) else acct_res.data
                acct_id = None
                if isinstance(first, dict):
                    acct_id = first.get('accountId') or first.get('acctId') or first.get('account')
                if acct_id:
                    self._current_account_id = acct_id
                    try:
                        self.client.switch_account(self._current_account_id)
                    except Exception:
                        pass
        except Exception:
            # best-effort only; continue without failing
            pass

        # Runtime toggle for websocket orders logging (can be set at runtime by admin endpoint)
        # This takes precedence over the environment variable when True.
        self._runtime_log_ws_orders = False

    def align_price_to_min_tick(self, price: float, min_tick: float, direction: str = 'nearest') -> float:
        """
        Align a price to the instrument's minimum tick increment.

        Args:
            price: original price
            min_tick: minimum price variation (tick)
            direction: 'nearest'|'up'|'down' - how to round

        Returns:
            price aligned to the nearest tick as float
        """
        try:
            from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING
            p = Decimal(str(price))
            t = Decimal(str(min_tick))

            # Use the reported min_tick directly; if it's zero treat as invalid
            if t == 0:
                return float(round(price, 8))

            # Compute the ratio and round according to direction
            ratio = p / t
            if direction == 'up':
                quant = ratio.quantize(Decimal('1'), rounding=ROUND_CEILING)
            elif direction == 'down':
                quant = ratio.quantize(Decimal('1'), rounding=ROUND_FLOOR)
            else:
                quant = ratio.quantize(Decimal('1'), rounding=ROUND_HALF_UP)

            aligned = (quant * t)
            # Ensure we quantize to the same exponent as the tick to preserve formatting
            try:
                aligned = aligned.quantize(t)
            except Exception:
                # If quantize fails for odd ticks, fall back to rounding to 8 decimals
                aligned = aligned.quantize(Decimal('0.00000001'))

            # Return a float constructed from the exact decimal string to avoid binary float artifacts
            try:
                return float(str(aligned))
            except Exception:
                return float(aligned)
        except Exception:
            try:
                from decimal import Decimal
                t = Decimal(str(min_tick or 0.01))
                p = Decimal(str(price))
                steps = (p / t).quantize(Decimal('1'))
                fallback = (steps * t)
                try:
                    return float(str(fallback))
                except Exception:
                    return float(fallback)
            except Exception:
                return float(round(price, 8))

    def get_aligned_price(self, conid: str, target_price: float, side: str = 'BUY') -> float:
        """
        Helper to return a price aligned to the instrument's minimum tick for a given conid.

        Args:
            conid: contract id (int or str)
            target_price: suggested price (midpoint)
            side: 'BUY' or 'SELL' to choose rounding direction

        Returns:
            Aligned price as float. Falls back to target_price when minTick is unavailable.
        """
        try:
            if target_price is None:
                return 0.0
            price = float(target_price)

            # Discover min_tick using helper (market-data -> secdef/info) with caching
            min_tick = None
            try:
                min_tick = self._get_min_tick_for_conid(conid)
            except Exception:
                min_tick = None

            if not min_tick or min_tick == 0:
                # Nothing to align against
                return float(price)

            dir_choice = 'nearest'
            try:
                if side and str(side).upper() == 'SELL':
                    dir_choice = 'up'
                elif side and str(side).upper() == 'BUY':
                    dir_choice = 'down'
            except Exception:
                dir_choice = 'nearest'

            return float(self.align_price_to_min_tick(price, min_tick, direction=dir_choice))
        except Exception:
            try:
                return float(target_price)
            except Exception:
                return 0.0
    
    def _get_min_tick_for_conid(self, conid: str, ttl: int = 300) -> Optional[float]:
        """Discover minTick for a conid using market-data or secdef/info and cache the result.

        Args:
            conid: contract id
            ttl: cache time-to-live in seconds

        Returns:
            min_tick as float or None
        """
        import time

        key = str(conid)
        now = time.time()
        # Cache hit
        cached = self._min_tick_cache.get(key)
        if cached and (now - cached.get('fetched_at', 0) < ttl):
            return cached.get('min_tick')

        # 1) Try market-data response which sometimes includes minTick
        min_tick = None
        try:
            md = self.get_option_market_data({'conid': conid})
            if md and isinstance(md, dict):
                for k in ('minTick', 'min_tick', 'minPriceIncrement', 'min_price_increment'):
                    if k in md and md.get(k) is not None:
                        try:
                            min_tick = float(md.get(k))
                            break
                        except Exception:
                            continue
        except Exception:
            min_tick = None

        # 2) Fallback to secdef/info via ibind client
        if not min_tick:
            try:
                secdef_res = None
                try:
                    secdef_res = self.client.search_secdef_info_by_conid(conid=str(conid))
                except TypeError:
                    secdef_res = None

                if not secdef_res:
                    # try common sec_type variants
                    for sec_type in ('OPT', 'STK'):
                        try:
                            secdef_res = self.client.search_secdef_info_by_conid(conid=str(conid), sec_type=sec_type)
                            if secdef_res:
                                break
                        except Exception:
                            continue

                if secdef_res and hasattr(secdef_res, 'data') and secdef_res.data:
                    sd = secdef_res.data[0] if isinstance(secdef_res.data, list) else secdef_res.data
                    if isinstance(sd, dict):
                        for key in ('minTick', 'min_tick', 'minPriceIncrement', 'min_price_increment'):
                            if key in sd and sd.get(key) is not None:
                                try:
                                    min_tick = float(sd.get(key))
                                    break
                                except Exception:
                                    continue
            except Exception:
                min_tick = None

        # Save to cache even if None to avoid tight-loop calls
        self._min_tick_cache[key] = {'min_tick': min_tick, 'fetched_at': now}
        return min_tick
    
    def check_health(self):
        """Check IBKR client health"""
        return self.client.check_health()
    
    def tickle(self):
        """Keep the session alive"""
        return self.client.tickle()
    
    def get_accounts(self):
        """Get portfolio accounts"""
        return self.client.portfolio_accounts()

    def get_accounts_safe(self):
        """Return accounts result using whichever method the client supports (best-effort)."""
        try:
            if hasattr(self.client, 'accounts'):
                return self.client.accounts()
        except Exception:
            pass
        try:
            return self.client.portfolio_accounts()
        except Exception:
            return None

    def search_contract_by_symbol(self, symbol: str, sec_type: str = None, name: bool = None, secType: str = None):
        """Proxy wrapper for client's search_contract_by_symbol with flexible param names.

        Returns the raw client result or None on failure. Handlers should inspect
        the returned object's `.data` to determine if any contracts were found.
        """
        try:
            # prefer the standardized sec_type kwarg
            return self.client.search_contract_by_symbol(symbol=symbol, sec_type=sec_type or secType, name=name)
        except Exception:
            try:
                # some client variants expect secType casing
                return self.client.search_contract_by_symbol(symbol=symbol, secType=secType or sec_type, name=name)
            except Exception as e:
                print(f"DEBUG: search_contract_by_symbol proxy failed: {e}")
                return None
    
    def diagnose_market_data_connection(self):
        """
        Diagnose market data connection issues
        """
        try:
            print(f"🔍 DIAGNOSING MARKET DATA CONNECTION...")
            
            # Check 1: Basic connection - use safe accessor that tolerates different client shapes
            print(f"📡 Checking basic API connection...")
            accounts = self.get_accounts_safe()
            if accounts and hasattr(accounts, 'data') and accounts.data:
                # Try to display a helpful summary (selectedAccount for one API shape, length for another)
                try:
                    if isinstance(accounts.data, dict) and 'selectedAccount' in accounts.data:
                        print(f"✅ API Connection: OK - {accounts.data.get('selectedAccount', 'Unknown')}")
                    elif isinstance(accounts.data, list):
                        print(f"✅ API Connection: OK - {len(accounts.data)} accounts")
                    else:
                        print(f"✅ API Connection: OK - account data available")
                except Exception:
                    print(f"✅ API Connection: OK - account data available (uninspectable shape)")
            else:
                print(f"❌ API Connection: FAILED - no accounts returned from client")
                return False
            
            # Check 2: Try a simple market data request for SPY (highly liquid)
            print(f"📊 Testing market data with SPY (highly liquid)...")
            try:
                # Get SPY contract first
                spy_search = self.client.search_contract_by_symbol(symbol="SPY", secType="STK")
                if spy_search and spy_search.data:
                    spy_conid = spy_search.data[0].get('conid')
                    print(f"✅ SPY Contract Found: {spy_conid}")
                    
                    # Try market data for SPY
                    spy_data = self.client.live_marketdata_snapshot(conids=[str(spy_conid)], fields=["31"])
                    print(f"📈 SPY Market Data Response: {spy_data.data if spy_data else 'None'}")
                    
                    if spy_data and spy_data.data and isinstance(spy_data.data, list) and len(spy_data.data) > 0:
                        spy_fields = spy_data.data[0]
                        if '31' in spy_fields:
                            print(f"✅ Market Data: WORKING - SPY Last Price: {spy_fields['31']}")
                            return True
                        else:
                            print(f"❌ Market Data: NO PRICING FIELDS - Only got: {list(spy_fields.keys())}")
                            print(f"🔧 SOLUTION: Enable 'Stream market data to API' in TWS/Gateway settings")
                            return False
                    else:
                        print(f"❌ Market Data: EMPTY RESPONSE")
                        return False
                else:
                    print(f"❌ SPY Contract: NOT FOUND")
                    
            except Exception as e:
                print(f"❌ Market Data Test: FAILED - {e}")
                return False
                
        except Exception as e:
            print(f"❌ Diagnosis Failed: {e}")
            return False

    def switch_account(self, account_id: str = None):
        """Switch to specified account or first available account"""
        if account_id:
            self.client.switch_account(account_id)
            self._current_account_id = account_id
        else:
            accounts = self.get_accounts().data
            if accounts and isinstance(accounts, list) and len(accounts) > 0:
                account_id = accounts[0]["accountId"]
                self.client.switch_account(account_id)
                self._current_account_id = account_id
        
        # print(f"DEBUG: Switched to account: {self._current_account_id}")
        return self._current_account_id

    def get_accounts(self):
        """Get portfolio accounts"""
        return self.client.portfolio_accounts()

    def _request_market_data_with_retry(self, conid: str, fields: list, max_retries: int = 3) -> dict:
        """
        Request market data with IBKR's retry pattern.
        First request often returns metadata only, subsequent requests return actual data.
        """
        for attempt in range(max_retries):
            # print(f"DEBUG: Market data attempt {attempt + 1}/{max_retries} for conid {conid}")
            
            try:
                market_data = self.client.live_marketdata_snapshot(conids=[conid], fields=fields)
                # print(f"DEBUG: Attempt {attempt + 1} result: {market_data}")
                
                if market_data and hasattr(market_data, 'data') and market_data.data:
                    raw_data = market_data.data
                    if isinstance(raw_data, list) and len(raw_data) > 0:
                        data = raw_data[0]
                        if isinstance(data, dict):
                            available_fields = list(data.keys())
                            # print(f"DEBUG: Attempt {attempt + 1} fields: {available_fields}")
                            
                            # Check if we got actual market data (not just metadata)
                            has_pricing_data = any(field in available_fields for field in ['31', '84', '86', '88'])
                            metadata_only = len(available_fields) <= 3 and all(field in ['conid', 'conidEx', '_updated'] for field in available_fields)
                            
                            if has_pricing_data or not metadata_only:
                                # print(f"DEBUG: Got market data on attempt {attempt + 1}")
                                return data
                            elif attempt < max_retries - 1:
                                print(f"DEBUG: Got metadata only, will retry...")
                                import time
                                time.sleep(1)  # Wait before retry
                                
            except Exception as e:
                print(f"DEBUG: Market data attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)
        
        print(f"DEBUG: All market data attempts failed for conid {conid}")
        return {}

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions for the active account"""
        if not self._current_account_id:
            self.switch_account()
        
        positions_response = self.client.positions().data
        
        if not isinstance(positions_response, list):
            return []
        
        return positions_response
    
    def get_formatted_positions(self) -> List[Dict[str, Any]]:
        """Get positions formatted for frontend consumption"""
        positions = self.get_positions()
        formatted_positions = []
        
        for pos in positions:
            if isinstance(pos, dict):
                formatted_position = {
                    "conid": pos.get("conid"),
                    "symbol": pos.get("contractDesc"),
                    "position": pos.get("position"),
                    "avgCost": pos.get("avgCost"),
                    "avgPrice": pos.get("avgPrice"),
                    "currentPrice": pos.get("mktPrice"),
                    "marketValue": pos.get("mktValue"),
                    "unrealizedPnl": pos.get("unrealizedPnl"),
                    "realizedPnl": pos.get("realizedPnl"),
                    "currency": pos.get("currency"),
                    "secType": pos.get("assetClass"),
                    "description": pos.get("contractDesc"),
                    "unrealizedPnlPct": (pos.get("unrealizedPnl", 0) / abs(pos.get("mktValue", 1))) * 100 if pos.get("mktValue") else 0,
                    "dailyPnl": pos.get("unrealizedPnl", 0),
                    "priceChange": pos.get("mktPrice", 0) - pos.get("avgPrice", 0) if pos.get("mktPrice") and pos.get("avgPrice") else 0
                }
                formatted_positions.append(formatted_position)
        
        return formatted_positions
    
    def find_position_by_conid(self, conid: int) -> Optional[Dict[str, Any]]:
        """Find a specific position by contract ID"""
        try:
            target = str(conid) if conid is not None else None
        except Exception:
            target = None

        positions = self.get_positions() or []
        for pos in positions:
            try:
                pos_conid = pos.get('conid') or pos.get('contractId') or pos.get('conId')
                pos_conid_str = str(pos_conid) if pos_conid is not None else None
                # position quantity may be under different keys or types
                qty = pos.get('position') if 'position' in pos else pos.get('qty') if 'qty' in pos else pos.get('quantity') if 'quantity' in pos else None
                try:
                    qty_val = int(qty)
                except Exception:
                    try:
                        qty_val = int(float(qty))
                    except Exception:
                        qty_val = 0

                if target and pos_conid_str and pos_conid_str == target and qty_val != 0:
                    return pos
            except Exception:
                # ignore and continue
                continue
        return None
    
    def subscribe_orders(self):
        """Subscribe to orders WebSocket channel

        Best-effort: ensure the underlying client and ws_client are using the
        configured account before subscribing. Some ibind variants require the
        websocket session to be tied to the same account as the REST client; if
        the accounts differ we may see warnings and no order events for the
        expected account. This helper will attempt several safe methods to
        align the account.
        """
        # Ensure our main client and ws client are using the currently-selected account
        try:
            if self._current_account_id:
                try:
                    # Switch the REST client first (no-op if already set)
                    self.client.switch_account(self._current_account_id)
                except Exception:
                    # Ignore failures but continue to attempt to align ws_client
                    logger.debug("IBKRService.subscribe_orders: failed to switch REST client account")

                # Attempt to inform the websocket client about the desired account.
                # Different ibind/ws_client versions expose different methods; try a few common names.
                if hasattr(self, 'ws_client') and self.ws_client:
                    for method_name in ('switch_account', 'set_account', 'set_current_account', 'change_account', 'set_account_id'):
                        try:
                            meth = getattr(self.ws_client, method_name, None)
                            if callable(meth):
                                try:
                                    meth(self._current_account_id)
                                    logger.info(f"IBKRService: instructed ws_client to use account {self._current_account_id} via {method_name}")
                                    break
                                except Exception:
                                    # try next
                                    continue
                        except Exception:
                            continue

        except Exception:
            # best-effort only
            pass

        # If the ws_client appears to still be tied to a different account, attempt
        # a best-effort recreate so the ws session is created with the correct account.
        try:
            # Try to read common attributes that indicate the ws client's current account
            current_ws_account = None
            if hasattr(self, 'ws_client') and self.ws_client:
                for attr in ('account_id', 'acctId', 'account', 'current_account', 'accountId'):
                    try:
                        val = getattr(self.ws_client, attr, None)
                        if val:
                            current_ws_account = str(val)
                            break
                    except Exception:
                        continue

            # If we know the ws client account and it doesn't match, or if the ibind
            # library previously warned about needing a switch, re-create the ws client.
            if self._current_account_id and current_ws_account and str(self._current_account_id) != str(current_ws_account):
                logger.info(f"IBKRService: ws_client account ({current_ws_account}) != desired ({self._current_account_id}), recreating ws_client")
                try:
                    # Try graceful shutdown if supported
                    for stop_method in ('stop', 'close', 'shutdown', 'disconnect'):
                        try:
                            meth = getattr(self.ws_client, stop_method, None)
                            if callable(meth):
                                try:
                                    meth()
                                except Exception:
                                    pass
                        except Exception:
                            continue

                    # Recreate a new ws client bound to the current REST client/account
                    try:
                        self.ws_client = IbkrWsClient(ibkr_client=self.client, start=True)
                        logger.info(f"IBKRService: recreated ws_client for account {self._current_account_id}")
                    except Exception as e:
                        logger.debug(f"IBKRService: failed to recreate ws_client: {e}")
                except Exception:
                    pass

        except Exception:
            # best-effort only
            pass

        # Finally subscribe to the orders channel
        self.ws_client.subscribe(channel=IbkrWsKey.ORDERS.channel)
    
    def unsubscribe_orders(self):
        """Unsubscribe from orders WebSocket channel"""
        self.ws_client.unsubscribe(IbkrWsKey.ORDERS)
    
    def get_orders_data(self):
        """Get orders data from WebSocket"""
        # Optional temporary verbose logging for websocket orders messages.
        # Enable by setting environment variable LOG_WS_ORDERS=1. This is
        # intended as an easy-to-remove diagnostic; it will log every orders
        # message we pop from the websocket queue.
        env_log_ws = str(os.getenv('LOG_WS_ORDERS', '')).strip() in ('1', 'true', 'yes')
        # Use runtime toggle if enabled, otherwise fall back to env var
        log_ws = bool(getattr(self, '_runtime_log_ws_orders', False)) or env_log_ws

        try:
            if not hasattr(self, 'ws_client') or not self.ws_client:
                logger.info("IBKRService.get_orders_data: no ws_client available")
                return None

            # If the ws client has an empty queue, log that explicitly for diagnostics
            try:
                empty = self.ws_client.empty(IbkrWsKey.ORDERS)
            except Exception as e:
                logger.debug(f"IBKRService.get_orders_data: error checking empty(): {e}")
                empty = True

            if empty:
                # Frequent empty polls are normal when there are no order updates.
                # Log at DEBUG so normal INFO logs aren't flooded.
                logger.debug("IBKRService.get_orders_data: orders queue empty")
                return None

            data = self.ws_client.get(IbkrWsKey.ORDERS)
            if log_ws:
                try:
                    # Use info level so messages are easy to find in logs.
                    logger.info("WS_ORDER_MSG: %s", json.dumps(data, default=str))
                except Exception:
                    logger.info("WS_ORDER_MSG (raw): %s", repr(data))
            return data
        except Exception as e:
            # Keep behavior non-fatal; log and return None
            logger.debug(f"get_orders_data exception: {e}")
        return None

    def set_runtime_ws_logging(self, enabled: bool) -> bool:
        """Enable or disable runtime websocket orders logging without needing a process restart."""
        try:
            self._runtime_log_ws_orders = bool(enabled)
            return True
        except Exception:
            return False

    def _auto_confirm_websocket_prompts(self, max_checks: int = 6, wait: float = 0.5) -> list:
        """
        Poll the websocket notifications queue for any prompt-style messages and reply to them.

        This helps reconcile interactive prompts that may arrive via websocket (e.g. Price Management
        Algo questions) by issuing the same reply via the REST reply endpoint. Returns a list of
        confirmation attempts performed.
        """
        confirmations = []
        # Nothing to do if no websocket client
        if not hasattr(self, 'ws_client') or not self.ws_client:
            return confirmations

        try:
            import time
            checks = 0
            while checks < max_checks:
                # If there are no notifications, wait a bit and retry - sometimes the WS message arrives shortly after REST returns
                if self.ws_client.empty(IbkrWsKey.NOTIFICATIONS):
                    time.sleep(wait)
                    checks += 1
                    continue

                # Drain available notifications
                try:
                    notif = self.ws_client.get(IbkrWsKey.NOTIFICATIONS)
                except Exception:
                    break

                # Notifications may be a single dict or a list
                items = []
                if isinstance(notif, list):
                    items = notif
                elif isinstance(notif, dict):
                    items = [notif]
                else:
                    # unknown shape - skip
                    checks += 1
                    continue

                for item in items:
                    try:
                        # Some notifications use 'prompt': True and 'messageId' or 'id'
                        is_prompt = bool(item.get('prompt') or item.get('prompt', False))
                        if not is_prompt:
                            # also tolerate certain notification types that include messageId and prompt-like content
                            # e.g., messageType 'NOTIFICATIONS' with messageId and prompt flag
                            is_prompt = 'messageId' in item and item.get('prompt', False)

                        if not is_prompt:
                            continue

                        reply_id = item.get('messageId') or item.get('id') or item.get('replyId')
                        if not reply_id:
                            # Some websocket messages embed nested payloads
                            if 'data' in item and isinstance(item['data'], dict):
                                reply_id = item['data'].get('messageId') or item['data'].get('id')

                        if not reply_id:
                            continue

                        # Attempt to reply with confirmed=True
                        try:
                            resp = self.client.reply(reply_id=reply_id, confirmed=True)
                            confirmations.append({'reply_id': reply_id, 'result': getattr(resp, 'data', resp)})
                        except Exception as e:
                            confirmations.append({'reply_id': reply_id, 'error': str(e)})
                    except Exception:
                        # ignore per-item errors
                        continue

                # Short pause before checking for further notifications
                time.sleep(wait)
                checks += 1

        except Exception:
            # best-effort only
            pass

        return confirmations
    
    def place_trailing_limit_order(self, conid: int, quantity: float, trailing_amount: float, limit_offset: float = 0.01) -> Dict[str, Any]:
        """Place a trailing limit sell order with confirmation loop handling - supports extended hours"""
        if not self._current_account_id:
            self.switch_account()

        # Get current position to determine initial limit price
        position = self.find_position_by_conid(conid)
        if not position:
            raise Exception(f"No position found for conid {conid}")
        
        current_price = position.get("mktPrice", 0)
        if not current_price:
            raise Exception(f"Unable to get current market price for conid {conid}")

        # Calculate initial limit price (current price minus trailing amount)
        initial_limit_price = round(current_price - trailing_amount, 2)

        # Create trailing limit order request
        # For TRAILLMT orders, we need both price (initial limit) and aux_price (limit offset)
        order_request = OrderRequest(
            conid=conid,
            side="SELL",
            quantity=abs(quantity),  # Ensure positive quantity for sell order
            order_type="TRAILLMT",  # Trailing limit order
            acct_id=self._current_account_id,
            trailing_amt=trailing_amount,
            trailing_type="amt",  # Amount-based trailing (vs percentage)
            price=initial_limit_price,  # Initial limit price
            aux_price=limit_offset,  # Limit price offset from trailing stop price
            tif="GTC",  # Good Till Cancelled
            outside_rth=True  # Allow extended hours trading for limit orders
        )

        try:
            # Prepare answers for known confirmation dialogs
            answers = {
                "You are about to submit a stop order. Please be aware of the various stop order types available and the risks associated with each one.Are you sure you want to submit this order?": True,
                "This security has limited liquidity. If you choose to trade this security, there is a heightened risk that you may not be able to close your position at the time you wish, at a price you wish, and/or without incurring a loss. Confirm that you understand the risks of trading illiquid securities.Are you sure you want to submit this order?": True
            }
            
            # Initial order placement with predefined answers
            result = self.client.place_order(
                order_request=order_request,
                answers=answers,
                account_id=self._current_account_id
            )
            
            # Handle confirmation loop
            max_confirmations = 5  # Prevent infinite loops
            confirmation_count = 0
            
            while confirmation_count < max_confirmations:
                response_data = result.data if hasattr(result, 'data') else result
                
                # Check if response contains confirmation requirement
                if isinstance(response_data, dict) and 'id' in response_data:
                    # Check if this is a confirmation request (usually has message field)
                    if 'message' in response_data or any(key in response_data for key in ['warning', 'confirm', 'question']):
                        confirmation_id = response_data['id']
                        
                        print(f"Order confirmation required: {response_data.get('message', 'Confirmation needed')}")
                        
                        # Reply with confirmation (True to accept)
                        result = self.client.reply(reply_id=confirmation_id, confirmed=True)
                        confirmation_count += 1
                        
                        # Continue loop to check if more confirmations are needed
                        continue
                    else:
                        # Response has ID but no confirmation fields - likely successful order
                        break
                elif isinstance(response_data, list) and len(response_data) > 0:
                    # Sometimes responses come as lists
                    first_item = response_data[0]
                    if isinstance(first_item, dict) and 'id' in first_item:
                        if 'message' in first_item or any(key in first_item for key in ['warning', 'confirm', 'question']):
                            confirmation_id = first_item['id']
                            
                            print(f"Order confirmation required: {first_item.get('message', 'Confirmation needed')}")
                            
                            result = self.client.reply(reply_id=confirmation_id, confirmed=True)
                            confirmation_count += 1
                            continue
                        else:
                            break
                else:
                    # No confirmation needed, order placed successfully
                    break
            
            if confirmation_count >= max_confirmations:
                raise Exception(f"Too many confirmation rounds ({max_confirmations}), order may not have been placed")
            
            final_response = result.data if hasattr(result, 'data') else result

            # Add confirmation metadata to response
            if isinstance(final_response, dict):
                final_response['confirmations_processed'] = confirmation_count
            elif isinstance(final_response, list) and len(final_response) > 0:
                final_response[0]['confirmations_processed'] = confirmation_count

            return final_response
        except Exception as e:
            raise Exception(f"Failed to place trailing limit order: {str(e)}")
        finally:
            # Best-effort: reconcile any websocket prompts that may have arrived asynchronously
            try:
                self._auto_confirm_websocket_prompts()
            except Exception:
                pass

    def place_trailing_stop_order(self, conid: int, quantity: float, trailing_amount: float) -> Dict[str, Any]:
        """Place a trailing stop sell order with confirmation loop handling"""
        if not self._current_account_id:
            self.switch_account()

        # Create trailing stop order request
        order_request = OrderRequest(
            conid=conid,
            side="SELL",
            quantity=abs(quantity),  # Ensure positive quantity for sell order
            order_type="TRAIL",
            acct_id=self._current_account_id,
            trailing_amt=trailing_amount,
            trailing_type="amt",  # Amount-based trailing (vs percentage)
            tif="GTC",  # Good Till Cancelled
            outside_rth=False  # Only during regular trading hours - IBKR rejects True for trailing stops
        )

        try:
            # Prepare answers for known confirmation dialogs
            answers = {
                "You are about to submit a stop order. Please be aware of the various stop order types available and the risks associated with each one.Are you sure you want to submit this order?": True,
                "This security has limited liquidity. If you choose to trade this security, there is a heightened risk that you may not be able to close your position at the time you wish, at a price you wish, and/or without incurring a loss. Confirm that you understand the risks of trading illiquid securities.Are you sure you want to submit this order?": True
            }
            
            # Initial order placement with predefined answers
            result = self.client.place_order(
                order_request=order_request,
                answers=answers,
                account_id=self._current_account_id
            )
            
            # Handle confirmation loop
            max_confirmations = 5  # Prevent infinite loops
            confirmation_count = 0
            
            while confirmation_count < max_confirmations:
                response_data = result.data if hasattr(result, 'data') else result
                
                # Check if response contains confirmation requirement
                if isinstance(response_data, dict) and 'id' in response_data:
                    # Check if this is a confirmation request (usually has message field)
                    if 'message' in response_data or any(key in response_data for key in ['warning', 'confirm', 'question']):
                        confirmation_id = response_data['id']
                        
                        print(f"Order confirmation required: {response_data.get('message', 'Confirmation needed')}")
                        
                        # Reply with confirmation (True to accept)
                        result = self.client.reply(reply_id=confirmation_id, confirmed=True)
                        confirmation_count += 1
                        
                        # Continue loop to check if more confirmations are needed
                        continue
                    else:
                        # Response has ID but no confirmation fields - likely successful order
                        break
                elif isinstance(response_data, list) and len(response_data) > 0:
                    # Sometimes responses come as lists
                    first_item = response_data[0]
                    if isinstance(first_item, dict) and 'id' in first_item:
                        if 'message' in first_item or any(key in first_item for key in ['warning', 'confirm', 'question']):
                            confirmation_id = first_item['id']
                            
                            print(f"Order confirmation required: {first_item.get('message', 'Confirmation needed')}")
                            
                            result = self.client.reply(reply_id=confirmation_id, confirmed=True)
                            confirmation_count += 1
                            continue
                        else:
                            break
                else:
                    # No confirmation needed, order placed successfully
                    break
            
            if confirmation_count >= max_confirmations:
                raise Exception(f"Too many confirmation rounds ({max_confirmations}), order may not have been placed")
            
            final_response = result.data if hasattr(result, 'data') else result

            # Add confirmation metadata to response
            if isinstance(final_response, dict):
                final_response['confirmations_processed'] = confirmation_count
            elif isinstance(final_response, list) and len(final_response) > 0:
                final_response[0]['confirmations_processed'] = confirmation_count

            return final_response
        except Exception as e:
            raise Exception(f"Failed to place trailing stop order: {str(e)}")
        finally:
            # Best-effort WS prompt reconciliation
            try:
                self._auto_confirm_websocket_prompts()
            except Exception:
                pass
    
    def place_order_with_confirmations(self, order_request: OrderRequest) -> Dict[str, Any]:
        """Generic order placement method that handles confirmation loops"""
        if not self._current_account_id:
            self.switch_account()

        error_msg = None
        try:
            # Place the order and handle any REST-driven confirmations
            print("📤 Placing order and handling confirmations...")
            result = self.client.place_order(order_request=order_request, answers={}, account_id=self._current_account_id)

            max_confirmations = 10
            confirmation_count = 0
            confirmations_log = []

            while confirmation_count < max_confirmations:
                response_data = result.data if hasattr(result, 'data') else result
                print(f"🔍 Response {confirmation_count}: {response_data}")

                confirmation_id = None
                message = "Confirmation needed"

                if isinstance(response_data, dict) and 'id' in response_data:
                    confirmation_id = response_data['id']
                    message = response_data.get('message', response_data.get('messageHeader', 'Confirmation needed'))
                elif isinstance(response_data, list) and len(response_data) > 0:
                    first_item = response_data[0]
                    if isinstance(first_item, dict) and 'id' in first_item:
                        confirmation_id = first_item['id']
                        message = first_item.get('message', first_item.get('messageHeader', 'Confirmation needed'))

                if confirmation_id:
                    print(f"🔔 Confirmation {confirmation_count + 1}: {message}")
                    confirmations_log.append({'step': confirmation_count + 1, 'message': message, 'id': confirmation_id})

                    print(f"📤 Sending reply with confirmed=True for ID: {confirmation_id}")
                    result = self.client.reply(reply_id=confirmation_id, confirmed=True)
                    confirmation_count += 1
                    continue

                # No confirmation ID found -> done
                print("✅ No confirmation needed, order completed successfully")
                break

            if confirmation_count >= max_confirmations:
                print(f"⚠️ Reached max confirmations ({max_confirmations}), but order may still have been placed")

            final_response = result.data if hasattr(result, 'data') else result

            if isinstance(final_response, dict):
                final_response['confirmations_processed'] = confirmation_count
                final_response['confirmations_log'] = confirmations_log
            elif isinstance(final_response, list) and len(final_response) > 0 and isinstance(final_response[0], dict):
                final_response[0]['confirmations_processed'] = confirmation_count
                final_response[0]['confirmations_log'] = confirmations_log
            else:
                final_response = {'order_response': final_response, 'confirmations_processed': confirmation_count, 'confirmations_log': confirmations_log}

            return final_response

        except Exception as e:
            error_msg = str(e)

        finally:
            # Best-effort: reconcile websocket prompts that may have arrived asynchronously
            try:
                self._auto_confirm_websocket_prompts()
            except Exception:
                pass

        # If IBKR raised a 'No answer found for question' error, try re-placing with the extracted question text
        if error_msg and "No answer found for question" in error_msg:
            print(f"🔍 IBKR asking for confirmation: {error_msg}")
            question = None
            if 'question: "' in error_msg:
                question_start = error_msg.find('question: "') + len('question: "')
                question_end = error_msg.find('"', question_start)
                if question_end != -1:
                    question = error_msg[question_start:question_end]
                    print(f"🎯 Extracted exact question: {question}")
            elif '"' in error_msg:
                quote_start = error_msg.find('"')
                if quote_start != -1:
                    quote_end = error_msg.rfind('"')
                    if quote_end > quote_start:
                        question = error_msg[quote_start+1:quote_end]
                        print(f"🎯 Extracted full question: {question}")

            if question:
                print("🔄 Retrying order placement with exact question answer...")
                try:
                    exact_answers = {question: True}
                    result = self.client.place_order(order_request=order_request, answers=exact_answers, account_id=self._current_account_id)
                    print("✅ Order placed successfully with exact question match!")
                    final_response = result.data if hasattr(result, 'data') else result

                    if isinstance(final_response, dict):
                        final_response['auto_confirmed_question'] = question
                    elif isinstance(final_response, list) and len(final_response) > 0 and isinstance(final_response[0], dict):
                        final_response[0]['auto_confirmed_question'] = question
                    else:
                        final_response = {'order_response': final_response, 'auto_confirmed_question': question}

                    return final_response
                except Exception as retry_error:
                    print(f"❌ Retry with exact question also failed: {retry_error}")

        if error_msg:
            raise Exception(f"Failed to place order: {error_msg}")
    
    def get_option_contract_details(self, symbol: str, strike: float, right: str, expiry: str) -> Optional[Dict[str, Any]]:
        """Get option contract details for a given symbol/strike/right/expiry.

        Returns a dict with keys: symbol, strike, right, expiry, conid, exchange, currency, description, full_name, search_method
        or None if not found.
        """
        try:
            print(f"DEBUG: Getting option contract details for {symbol} {strike}{right} {expiry}")

            # Find underlying conid via STK search first, fallback to OPT search
            search_result = self.client.search_contract_by_symbol(symbol=symbol, sec_type='STK')
            conid = None
            if search_result and hasattr(search_result, 'data') and search_result.data:
                data = search_result.data
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    conid = data[0].get('conid')
                elif isinstance(data, dict):
                    conid = data.get('conid')

            if not conid:
                opt_search = self.client.search_contract_by_symbol(symbol=symbol, sec_type='OPT')
                if opt_search and hasattr(opt_search, 'data') and opt_search.data:
                    data = opt_search.data
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and 'conid' in item:
                                conid = item.get('conid')
                                break
                            if isinstance(item, dict) and 'contracts' in item and isinstance(item.get('contracts'), list) and item.get('contracts'):
                                c = item.get('contracts')[0]
                                if isinstance(c, dict) and c.get('conid'):
                                    conid = c.get('conid')
                                    break

            if not conid:
                print(f"DEBUG: Could not determine underlying conid for {symbol}")
                return None

            # If expiry not provided, pick the closest available expiration
            if not expiry:
                try:
                    expiry = self._get_closest_expiration(symbol)
                    print(f"DEBUG: No expiry provided, using closest expiry {expiry}")
                except Exception:
                    expiry = None

            # Normalize expiry formats into YYYYMMDD where possible.
            # Accepts: M/D, M/D/YY, M/D/YYYY, YYYYMMDD, YYYYMM, etc.
            if expiry:
                try:
                    # M/D or M/D/YY or M/D/YYYY -> YYYYMMDD
                    if '/' in expiry:
                        parts = expiry.split('/')
                        if len(parts) >= 2:
                            month = parts[0].zfill(2)
                            day = parts[1].zfill(2)
                            # Year may be provided
                            if len(parts) == 3 and parts[2]:
                                year_part = parts[2]
                                if len(year_part) == 2:
                                    year = '20' + year_part
                                else:
                                    year = year_part
                            else:
                                # Infer year: current year, roll to next year if date already passed
                                from datetime import datetime
                                now = datetime.utcnow()
                                year = str(now.year)
                                try:
                                    m = int(month); d = int(day)
                                    if (m, d) < (now.month, now.day):
                                        year = str(now.year + 1)
                                except Exception:
                                    pass
                            expiry = f"{year}{month}{day}"
                    else:
                        # Numeric forms: YYYYMMDD (8), YYYYMM (6) -> convert YYYYMM to YYYYMM01
                        if expiry.isdigit():
                            if len(expiry) == 6:
                                expiry = expiry + '01'
                            elif len(expiry) == 8:
                                # already YYYYMMDD
                                pass
                            else:
                                # leave as-is; downstream checks may fail
                                pass
                    print(f"DEBUG: Normalized expiry to {expiry}")
                except Exception as ne:
                    print(f"DEBUG: Could not normalize expiry '{expiry}': {ne}")

            # Format expiry to IBKR month token (e.g., SEP25)
            formatted_month = None
            try:
                if expiry:
                    year = expiry[:4]
                    month = expiry[4:6]
                    months_map = {
                        '01': 'JAN', '02': 'FEB', '03': 'MAR', '04': 'APR',
                        '05': 'MAY', '06': 'JUN', '07': 'JUL', '08': 'AUG',
                        '09': 'SEP', '10': 'OCT', '11': 'NOV', '12': 'DEC'
                    }
                    month_str = months_map.get(month, month)
                    formatted_month = f"{month_str}{year[2:]}"
                else:
                    formatted_month = None
            except Exception:
                formatted_month = None

            # Preserve decimal formatting for strikes
            strike_param = str(int(strike)) if float(strike).is_integer() else str(strike)

            # Try secdef/info for this conid/month/strike/right
            try:
                secdef_result = self.client.search_secdef_info_by_conid(conid=str(conid), sec_type='OPT', month=formatted_month, strike=strike_param, right=right)
            except Exception:
                # fallback to unstruck if needed
                try:
                    secdef_result = self.client.search_secdef_info_by_conid(conid=str(conid), sec_type='OPT', month=formatted_month)
                except Exception:
                    secdef_result = None

            if not secdef_result or not hasattr(secdef_result, 'data') or not secdef_result.data:
                print(f"DEBUG: secdef/info returned no data for {symbol} {strike_param} {formatted_month}")
                return None

            secdata = secdef_result.data
            contract_entry = None
            if isinstance(secdata, list):
                for cand in secdata:
                    if isinstance(cand, dict) and cand.get('maturityDate') == expiry:
                        contract_entry = cand
                        break
                if not contract_entry and len(secdata) > 0 and isinstance(secdata[0], dict):
                    contract_entry = secdata[0]
            elif isinstance(secdata, dict):
                contract_entry = secdata

            if not contract_entry:
                print(f"DEBUG: No contract entry found in secdef data for {symbol}")
                return None

            result = {
                'symbol': symbol,
                'strike': float(strike),
                'right': right,
                'expiry': expiry,
                'conid': contract_entry.get('conid') or contract_entry.get('id'),
                'exchange': contract_entry.get('exchange'),
                'currency': contract_entry.get('currency', 'USD'),
                'description': contract_entry.get('description') or contract_entry.get('desc') or '',
                'full_name': contract_entry.get('desc2') or contract_entry.get('description') or f"{symbol} {strike_param}{right} {expiry}",
                'search_method': 'ibkr_chain_strike_probe'
            }

            print(f"DEBUG: IBKR contract details formatted: {result}")
            return result

        except Exception as e:
            print(f"DEBUG: Error in get_option_contract_details: {e}")
            import traceback
            print(traceback.format_exc())
            return None
    
    def get_option_market_data(self, contract_details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get market data for an option contract using correct IBKR API methods
        
        Args:
            contract_details: Contract details from get_option_contract_details
            
        Returns:
            Market data or None
        """
        try:
            print(f"DEBUG: get_option_market_data called with: {contract_details}")
            
            conid = contract_details.get("conid")
            if not conid:
                print(f"DEBUG: No conid in contract details: {contract_details}")
                return None
                
            print(f"DEBUG: IBKR getting market data for conid: {conid}")
            print(f"DEBUG: Current account ID: {self._current_account_id}")
            
            # Run market data diagnostics on first call
            if not hasattr(self, '_diagnostics_run'):
                self.diagnose_market_data_connection()
                self._diagnostics_run = True
            
            # Method 1: Try live_marketdata_snapshot (correct method name from API docs)
            try:
                print(f"DEBUG: Starting live_marketdata_snapshot call...")
                
                # According to IBKR docs, we need to call /iserver/accounts first for market data
                # Let's ensure we're authenticated and have account access
                if not self._current_account_id:
                    print(f"DEBUG: No current account ID, calling switch_account()")
                    self.switch_account()
                    print(f"DEBUG: After switch_account, current account ID: {self._current_account_id}")
                
                # Extended field codes for comprehensive market data
                # Field codes: 31=Last, 84=Bid, 86=Ask, 88=Volume, 70=High, 71=Low, 82=Change, 83=Change%, 85=Close, 87=OpenInterest(for options)
                fields = ["31", "84", "86", "88", "70", "71", "82", "83", "85", "87"]
                
                print(f"DEBUG: Requesting market data with fields: {fields}")
                
                # First, try to ensure we have accounts access (required per documentation)
                try:
                    # Use the method that matches the working endpoint /v1/api/iserver/accounts
                    accounts_result = self.client.accounts()
                    print(f"✅ Pre-flight accounts check successful: {accounts_result.data.get('selectedAccount', 'Unknown')}")
                    
                    # Check market data permissions in the account info
                    if accounts_result.data and 'allowFeatures' in accounts_result.data:
                        features = accounts_result.data['allowFeatures']
                        print(f"DEBUG: Account features: {list(features.keys())}")
                        
                        # Check for market data related permissions
                        if 'allowEventContract' in features:
                            print(f"DEBUG: Event contract permission: {features['allowEventContract']}")
                        if 'snapshotRefreshTimeout' in features:
                            print(f"DEBUG: Snapshot refresh timeout: {features['snapshotRefreshTimeout']}")
                        if 'allowedAssetTypes' in features:
                            print(f"DEBUG: Allowed asset types: {features['allowedAssetTypes']}")
                        if 'liteUser' in features:
                            print(f"DEBUG: Lite user: {features['liteUser']}")
                        if 'isPaper' in accounts_result.data:
                            print(f"DEBUG: Paper account: {accounts_result.data['isPaper']}")
                        if 'isFT' in accounts_result.data:
                            print(f"DEBUG: Financial advisor: {accounts_result.data['isFT']}")
                        
                        # Check if this is a paper account which may have limited market data
                        is_paper = accounts_result.data.get('isPaper', False)
                        if is_paper:
                            print(f"⚠️  PAPER ACCOUNT DETECTED - Market data may be limited or delayed")
                        
                        # Check market data timeout setting
                        timeout = features.get('snapshotRefreshTimeout', 30)
                        print(f"DEBUG: Market data snapshot timeout: {timeout} seconds")
                        
                except Exception as e:
                    print(f"❌ Pre-flight accounts check failed: {str(e)}")
                    # Try alternative method
                    try:
                        accounts_result = self.client.portfolio_accounts()
                        print(f"✅ Pre-flight accounts check (alternative) successful: {len(accounts_result.data) if accounts_result.data else 0} accounts")
                    except Exception as e2:
                        print(f"❌ Alternative pre-flight check failed: {str(e2)}")
                    # Continue anyway, might still work
                
                # Note: According to documentation, for derivative contracts, 
                # secdef/search should be called first (we already did this in get_contract_details)
                
                # Main market data request - this is the correct method per documentation
                market_data = self.client.live_marketdata_snapshot(conids=[str(conid)], fields=fields)
                print(f"DEBUG: live_marketdata_snapshot result: {market_data}")
                
                # Check if we need to establish subscription first
                if (market_data and hasattr(market_data, 'data') and market_data.data and 
                    isinstance(market_data.data, list) and len(market_data.data) > 0):
                    first_response = market_data.data[0]
                    response_fields = list(first_response.keys())
                    
                    # If we only get metadata fields, we need to try subscription approach
                    if set(response_fields) <= {'_updated', 'conidEx', 'conid'}:
                        print(f"DEBUG: Only metadata received, trying subscription approach...")
                        
                        # Try to establish streaming subscription first
                        try:
                            # Some IBKR APIs require streaming subscription to be established first
                            streaming_result = self.client.live_marketdata_snapshot(conids=[str(conid)], fields=["31"])  # Just last price
                            print(f"DEBUG: Initial streaming subscription result: {streaming_result}")
                            
                            # Wait a moment for subscription to establish
                            import time
                            time.sleep(1)
                            
                            # Now try full market data request again
                            market_data = self.client.live_marketdata_snapshot(conids=[str(conid)], fields=fields)
                            print(f"DEBUG: Market data after subscription: {market_data}")
                            
                        except Exception as sub_e:
                            print(f"DEBUG: Subscription establishment failed: {sub_e}")
                
                # Use our enhanced retry method to handle IBKR's subscription pattern
                data = self._request_market_data_with_retry(str(conid), fields, max_retries=3)
                
                if data and isinstance(data, dict):
                    print(f"DEBUG: Final market data fields: {list(data.keys())}")
                    
                    # If we only got field 31 (last price), try regulatory snapshot for full data
                    available_fields = list(data.keys())
                    has_bid_ask = '84' in available_fields or '86' in available_fields
                    
                    if not has_bid_ask and '31' in available_fields:
                        print(f"DEBUG: Only got last price, trying historical market data for recent prices...")
                        try:
                            # Get historical data (last few bars) to get recent pricing
                            historical_data = self.client.historical_data(
                                conid=str(conid),
                                period="1d",  # Last day
                                bar="1h"      # 1-hour bars
                            )
                            print(f"DEBUG: Historical data result: {historical_data}")
                            
                            if historical_data and hasattr(historical_data, 'data') and historical_data.data:
                                hist_data = historical_data.data
                                print(f"DEBUG: Historical data type: {type(hist_data)}")
                                
                                # Historical data usually comes as list of bars
                                if isinstance(hist_data, list) and len(hist_data) > 0:
                                    # Get the most recent bar (last trading session)
                                    recent_bar = hist_data[-1]
                                    print(f"DEBUG: Most recent bar: {recent_bar}")
                                    
                                    if isinstance(recent_bar, dict):
                                        # Extract OHLC data from historical bar
                                        close_price = recent_bar.get('c', recent_bar.get('close'))
                                        high_price = recent_bar.get('h', recent_bar.get('high'))
                                        low_price = recent_bar.get('l', recent_bar.get('low'))
                                        open_price = recent_bar.get('o', recent_bar.get('open'))
                                        volume = recent_bar.get('v', recent_bar.get('volume'))
                                        
                                        print(f"DEBUG: Historical OHLC - O: {open_price}, H: {high_price}, L: {low_price}, C: {close_price}, V: {volume}")
                                        
                                        # Update data with historical fields if we have valid prices
                                        if close_price and float(close_price) > 0:
                                            # Use close as both last and fallback for bid/ask
                                            data['31'] = str(close_price)  # Last
                                            data['85'] = str(close_price)  # Close
                                            
                                            if high_price and float(high_price) > 0:
                                                data['70'] = str(high_price)  # High
                                            if low_price and float(low_price) > 0:
                                                data['71'] = str(low_price)   # Low
                                            if open_price and float(open_price) > 0:
                                                data['87'] = str(open_price)  # Open
                                            if volume:
                                                data['88'] = volume           # Volume
                                            
                                            print(f"DEBUG: Updated data with historical prices: {list(data.keys())}")
                                            
                                elif isinstance(hist_data, dict):
                                    # Sometimes historical data comes as single dict
                                    print(f"DEBUG: Historical data fields: {list(hist_data.keys())}")
                                    
                                    # Look for recent price data in various formats
                                    if 'data' in hist_data and isinstance(hist_data['data'], list) and len(hist_data['data']) > 0:
                                        recent_bar = hist_data['data'][-1]
                                        close_price = recent_bar.get('c', recent_bar.get('close'))
                                        if close_price and float(close_price) > 0:
                                            data['31'] = str(close_price)
                                            data['85'] = str(close_price)
                                            print(f"DEBUG: Updated with nested historical close: {close_price}")
                                            
                        except Exception as e:
                            print(f"DEBUG: Historical data fallback failed: {e}")
                            # If historical data fails, we'll use what we have or fallback to estimates later
                    
                    # Extract and clean all price fields
                    def clean_price(price_str):
                            """Clean price string by removing prefixes and converting to float"""
                            if price_str == "N/A" or price_str is None:
                                return "N/A"
                            if isinstance(price_str, (int, float)):
                                # Check for invalid IBKR values
                                if price_str <= 0 or price_str == -1.0:
                                    return "N/A"
                                return price_str
                            if isinstance(price_str, str):
                                # Remove common prefixes: C (close), B (bid), A (ask), L (last)
                                clean_str = price_str
                                if clean_str.startswith(('C', 'B', 'A', 'L')):
                                    clean_str = clean_str[1:]
                                try:
                                    value = float(clean_str)
                                    # Check for invalid IBKR values
                                    if value <= 0 or value == -1.0:
                                        return "N/A"
                                    return value
                                except (ValueError, TypeError):
                                    return "N/A"
                            return "N/A"
                    
                    # Extract and clean all fields
                    bid = clean_price(data.get("84", "N/A"))
                    ask = clean_price(data.get("86", "N/A")) 
                    last = clean_price(data.get("31", "N/A"))
                    volume = data.get("88", "N/A")
                    high = clean_price(data.get("70", "N/A"))
                    low = clean_price(data.get("71", "N/A"))
                    change = clean_price(data.get("82", "N/A"))
                    change_pct = data.get("83", "N/A")
                    close = clean_price(data.get("85", "N/A"))
                    open_interest = data.get("87", "N/A")  # Field 87 is Open Interest for options
                    
                    print(f"DEBUG: Cleaned prices - Bid: {bid}, Ask: {ask}, Last: {last}, Volume: {volume}")
                    
                    result = {
                        "bid": bid,
                        "ask": ask,
                        "last": last,
                        "volume": volume,
                        "high": high,
                        "low": low,
                        "change": change,
                        "change_pct": change_pct,
                        "close": close,
                        "open_interest": open_interest  # Now properly mapped as open interest
                    }
                    
                    # Calculate spread if bid and ask are available and numeric
                    if (result["bid"] != "N/A" and result["ask"] != "N/A" and 
                        isinstance(result["bid"], (int, float)) and isinstance(result["ask"], (int, float))):
                        try:
                            spread = float(result["ask"]) - float(result["bid"])
                            result["spread"] = round(spread, 2)
                            print(f"DEBUG: Calculated spread: {result['spread']}")
                        except (ValueError, TypeError):
                            result["spread"] = "N/A"
                    else:
                        result["spread"] = "N/A"
                        print(f"DEBUG: Could not calculate spread - Bid: {result['bid']}, Ask: {result['ask']}")
                    
                    # Paper account fallback: estimate bid/ask from last price if missing
                    if (result["bid"] == "N/A" or result["ask"] == "N/A") and result["last"] != "N/A":
                        try:
                            last_price = float(result["last"])
                            # Estimate typical SPX option spread based on option price
                            if last_price > 5:
                                spread_estimate = 0.10  # $0.10 spread for higher priced options
                            elif last_price > 1:
                                spread_estimate = 0.05  # $0.05 spread for mid-priced options
                            else:
                                spread_estimate = 0.05  # $0.05 minimum spread
                            
                            estimated_bid = round(last_price - (spread_estimate / 2), 2)
                            estimated_ask = round(last_price + (spread_estimate / 2), 2)
                            
                            # Only use estimates if we don't have real data
                            if result["bid"] == "N/A":
                                result["bid"] = estimated_bid
                            if result["ask"] == "N/A":
                                result["ask"] = estimated_ask
                            if result["spread"] == "N/A":
                                result["spread"] = spread_estimate
                            
                            print(f"DEBUG: Paper account fallback - Estimated bid/ask from last price {last_price} -> Bid: {result['bid']}, Ask: {result['ask']}, Spread: {result['spread']}")
                            result["data_source"] = "live_snapshot_with_estimates"
                            
                        except (ValueError, TypeError) as e:
                            print(f"DEBUG: Could not estimate bid/ask from last price: {e}")
                    
                    # Mark data source if not already set
                    if "data_source" not in result:
                        result["data_source"] = "live_snapshot"
                    
                    print(f"DEBUG: IBKR market data formatted: {result}")
                    return result
                    
            except Exception as e:
                print(f"DEBUG: live_marketdata_snapshot failed: {e}")
                import traceback
                print(f"DEBUG: Snapshot traceback: {traceback.format_exc()}")
            
            # Method 2: Try different quote method if snapshot fails
            try:
                print(f"DEBUG: Trying alternative quote method...")
                
                # Try the marketdata/unsubscribe first to reset, then resubscribe
                try:
                    unsub_result = self.client.marketdata_unsubscribe_all()
                    print(f"DEBUG: Unsubscribe all result: {unsub_result}")
                except Exception as e:
                    print(f"DEBUG: Unsubscribe failed: {e}")
                
                # Try requesting market data via different endpoint
                try:
                    import time
                    time.sleep(1)  # Brief pause
                    
                    # Try snapshot again with fewer fields (sometimes this helps)
                    market_data = self.client.live_marketdata_snapshot(conids=[str(conid)], fields=["31", "84", "86"])
                    print(f"DEBUG: Simplified snapshot: {market_data}")
                    
                    if market_data and hasattr(market_data, 'data') and market_data.data:
                        data = market_data.data
                        if isinstance(data, list) and len(data) > 0:
                            data = data[0]
                        if isinstance(data, dict) and ('31' in data or '84' in data):
                            print(f"DEBUG: Got market data after retry: {list(data.keys())}")
                            return data
                            
                except Exception as e:
                    print(f"DEBUG: Alternative snapshot method failed: {e}")
                
            except Exception as e:
                print(f"DEBUG: Alternative quote method failed: {e}")
            
            # Method 3: Historical data fallback (FREE alternative to regulatory snapshot)
            # Provides last known trading session prices when live data unavailable
            try:
                print(f"DEBUG: Trying historical market data fallback...")
                
                # Try different historical data approaches
                historical_approaches = [
                    # Approach 1: Very recent intraday data
                    {"period": "1d", "bar": "1h", "desc": "1-hour bars for last day"},
                    # Approach 2: Daily data 
                    {"period": "2d", "bar": "1d", "desc": "Daily bars for last 2 days"},
                    # Approach 3: Wider time range
                    {"period": "1w", "bar": "1d", "desc": "Daily bars for last week"},
                ]
                
                for i, approach in enumerate(historical_approaches, 1):
                    try:
                        print(f"DEBUG: Historical approach {i}/3: {approach['desc']}")
                        
                        # Use the correct method name from ibind library
                        historical_data = self.client.marketdata_history_by_conid(
                            conid=str(conid),
                            period=approach["period"],
                            bar=approach["bar"]
                        )
                        print(f"DEBUG: Historical approach {i} result: {historical_data}")
                        
                        if historical_data and hasattr(historical_data, 'data') and historical_data.data:
                            hist_data = historical_data.data
                            print(f"DEBUG: Historical data type: {type(hist_data)}, content: {hist_data}")
                            
                            # Historical data usually comes as list of bars or dict with data
                            bars = None
                            if isinstance(hist_data, list) and len(hist_data) > 0:
                                bars = hist_data
                            elif isinstance(hist_data, dict):
                                # Sometimes historical data comes wrapped in a data structure
                                if 'data' in hist_data:
                                    bars = hist_data['data']
                                elif 'bars' in hist_data:
                                    bars = hist_data['bars']
                                else:
                                    # Maybe the dict itself contains the bar data
                                    bars = [hist_data]
                            
                            if bars and len(bars) > 0:
                                # Get the most recent bar (last trading session)
                                recent_bar = bars[-1]
                                print(f"DEBUG: Most recent bar from approach {i}: {recent_bar}")
                                
                                if isinstance(recent_bar, dict):
                                    # Extract OHLC data - try multiple field name formats
                                    close_price = (recent_bar.get('c') or recent_bar.get('close') or 
                                                 recent_bar.get('Close') or recent_bar.get('CLOSE'))
                                    high_price = (recent_bar.get('h') or recent_bar.get('high') or 
                                                recent_bar.get('High') or recent_bar.get('HIGH'))
                                    low_price = (recent_bar.get('l') or recent_bar.get('low') or 
                                               recent_bar.get('Low') or recent_bar.get('LOW'))
                                    open_price = (recent_bar.get('o') or recent_bar.get('open') or 
                                                recent_bar.get('Open') or recent_bar.get('OPEN'))
                                    volume = (recent_bar.get('v') or recent_bar.get('volume') or 
                                            recent_bar.get('Volume') or recent_bar.get('VOLUME'))
                                    
                                    print(f"DEBUG: Historical OHLC from approach {i} - O: {open_price}, H: {high_price}, L: {low_price}, C: {close_price}, V: {volume}")
                                    
                                    # If we have valid pricing data, use it
                                    if close_price and (isinstance(close_price, (int, float)) or 
                                                       (isinstance(close_price, str) and close_price.replace('.', '').replace('-', '').isdigit())):
                                        try:
                                            close_val = float(close_price)
                                            if close_val > 0:
                                                print(f"✅ SUCCESS: Historical approach {i} provided valid close price: {close_val}")
                                                
                                                # Build result using historical data
                                                result = {
                                                    "bid": "N/A",
                                                    "ask": "N/A", 
                                                    "last": close_val,
                                                    "volume": volume if volume else "N/A",
                                                    "high": float(high_price) if high_price and str(high_price).replace('.', '').replace('-', '').isdigit() else "N/A",
                                                    "low": float(low_price) if low_price and str(low_price).replace('.', '').replace('-', '').isdigit() else "N/A",
                                                    "open": float(open_price) if open_price and str(open_price).replace('.', '').replace('-', '').isdigit() else "N/A",
                                                    "change": "N/A",
                                                    "change_pct": "N/A",
                                                    "close": close_val,
                                                    "spread": "N/A",
                                                    "data_source": f"historical_{approach['bar']}_{approach['period']}"
                                                }
                                                
                                                # Estimate bid/ask from close price for options
                                                if close_val > 5:
                                                    spread_est = 0.10  # $0.10 spread for higher priced options
                                                elif close_val > 1:
                                                    spread_est = 0.05  # $0.05 spread for mid-priced options
                                                else:
                                                    spread_est = 0.05  # $0.05 minimum spread
                                                
                                                result["bid"] = round(close_val - (spread_est / 2), 2)
                                                result["ask"] = round(close_val + (spread_est / 2), 2)
                                                result["spread"] = spread_est
                                                
                                                print(f"DEBUG: Historical data result: {result}")
                                                return result
                                                
                                        except (ValueError, TypeError) as e:
                                            print(f"DEBUG: Could not convert close price to float: {e}")
                            
                            print(f"DEBUG: Historical approach {i} did not provide usable data")
                        else:
                            print(f"DEBUG: Historical approach {i} returned no data")
                            
                    except Exception as e:
                        print(f"DEBUG: Historical approach {i} failed: {e}")
                        continue
                
                print(f"DEBUG: All historical data approaches failed")
                        
            except Exception as e:
                print(f"DEBUG: Historical data fallback failed: {e}")
                import traceback
                print(f"DEBUG: Historical traceback: {traceback.format_exc()}")
            
            print(f"DEBUG: No market data found for conid: {conid}")
            
            # Final fallback: Return a result indicating contract found but no pricing data
            # This still provides value as we have the contract details
            print(f"⚠️  MARKET DATA UNAVAILABLE: Contract verified but no pricing data accessible")
            print(f"📋 Contract Status: IBKR contract ID {conid} exists and is valid")
            print(f"🔧 Possible causes: Market data permissions, account data subscriptions, market hours, or data licensing")
            
            # Return a minimal result that indicates the contract exists but no pricing
            fallback_result = {
                "bid": "N/A - No market data access",
                "ask": "N/A - No market data access", 
                "last": "N/A - No market data access",
                "volume": "N/A",
                "high": "N/A",
                "low": "N/A",
                "change": "N/A",
                "change_pct": "N/A",
                "close": "N/A",
                "open": "N/A",
                "spread": "N/A",
                "data_source": "contract_verified_no_pricing",
                "contract_verified": True,
                "conid": conid,
                "note": "Contract exists in IBKR system but market data unavailable"
            }
            
            print(f"DEBUG: Returning fallback result with contract verification: {fallback_result}")
            return fallback_result
            
        except Exception as e:
            print(f"DEBUG: Error getting market data: {e}")
            import traceback
            print(f"DEBUG: Full traceback: {traceback.format_exc()}")
            return None
    
    def find_option_contract(self, ticker: str, option_type: str, expiration_date: str, 
                           strike_price: str, action: str) -> Dict[str, Any]:
        """
        Find option contract for Real Day Trading alerts with intelligent defaults
        
        Args:
            ticker: Stock ticker (e.g., "AAPL")
            option_type: "CALL" or "PUT"
            expiration_date: "8/29" format or "closest"
            strike_price: "245" or "closest_itm_long"/"closest_itm_short"
            action: "LONG" or "SHORT" for ITM logic
            
        Returns:
            Dict with contract details and lookup results
        """
        try:
            print(f"DEBUG: Finding option contract for {ticker} {option_type}")
            print(f"DEBUG: Expiration: {expiration_date}, Strike: {strike_price}, Action: {action}")
            
            result = {
                "success": False,
                "ticker": ticker,
                "option_type": option_type,
                "requested_expiration": expiration_date,
                "requested_strike": strike_price,
                "action": action
            }
            
            # Convert option type to IBKR format
            right = "C" if option_type.upper() == "CALL" else "P"
            
            # Handle expiration date
            if expiration_date == "closest":
                # For now, use a default - this should be enhanced to find actual closest expiration
                expiry = self._get_closest_expiration(ticker)
                result["used_expiration"] = expiry
                result["expiration_source"] = "closest_available"
            else:
                # Convert M/D format to YYYYMMDD
                expiry = self._convert_date_format(expiration_date)
                result["used_expiration"] = expiry
                result["expiration_source"] = "user_specified"
            
            # Handle strike price
            if strike_price.startswith("closest_itm_"):
                # Get current stock price and find closest ITM strike
                strike = self._get_closest_itm_strike(ticker, action, option_type, expiry)
                result["used_strike"] = strike
                result["strike_source"] = "closest_itm"
            else:
                # Use provided strike
                try:
                    strike = float(strike_price)
                    result["used_strike"] = strike
                    result["strike_source"] = "user_specified"
                except ValueError:
                    result["error"] = f"Invalid strike price: {strike_price}"
                    return result
            
            # Get contract details from IBKR
            contract_details = self.get_option_contract_details(
                symbol=ticker,
                strike=strike,
                right=right,
                expiry=expiry
            )
            
            if contract_details:
                result["success"] = True
                result["contract_details"] = contract_details
                result["conid"] = contract_details.get("conid")
                
                # Get market data for the contract
                market_data = self.get_option_market_data(contract_details)
                if market_data:
                    result["market_data"] = market_data
                else:
                    result["market_data_warning"] = "Could not retrieve market data"
                    
            else:
                result["error"] = "Contract not found in IBKR"
                
            return result
            
        except Exception as e:
            print(f"ERROR: find_option_contract failed: {e}")
            import traceback
            print(f"DEBUG: Full traceback: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "ticker": ticker,
                "option_type": option_type
            }
    
    def _get_closest_expiration(self, ticker: str) -> str:
        """Get closest available expiration date by querying IBKR option chain.

        Strategy:
        - Use search_contract_by_symbol(..., sec_type='OPT') to find underlying conid(s)
        - Extract month tokens from returned entries (sections[*].months or item.months)
        - For each month token call search_secdef_info_by_conid to retrieve detailed defs
        - Collect maturityDate values, pick the earliest date >= today
        - Fall back to next Friday if nothing found
        """
        from datetime import datetime, timedelta
        # Quick detection: if this ticker offers daily/weekly expirations, return the nearest one immediately.
        try:
            short_detect = self.detect_short_dated_expirations(ticker, lookahead_days=10, conid_probe_count=3)
            if short_detect:
                # if 1DTE available, prefer it; then nearest weekly
                if short_detect.get('has_daily') and short_detect.get('nearest_daily'):
                    d = short_detect['nearest_daily']
                    print(f"DEBUG: Detected 1DTE for {ticker}: {d}")
                    return d.strftime('%Y%m%d')
                if short_detect.get('has_weekly') and short_detect.get('nearest_weekly'):
                    d = short_detect['nearest_weekly']
                    print(f"DEBUG: Detected weekly expiry for {ticker}: {d}")
                    return d.strftime('%Y%m%d')
        except Exception:
            # detection is best-effort; on error, continue with full chain probing
            pass
        try:
            print(f"DEBUG: Finding closest expiration for {ticker} from IBKR chain")
            # Get option-related search results
            search_result = self.client.search_contract_by_symbol(symbol=ticker, sec_type='OPT')
            months_tokens = set()
            conids = []

            if search_result and hasattr(search_result, 'data') and search_result.data:
                data = search_result.data
                # data may be a list of dicts
                if isinstance(data, list):
                    for item in data:
                        try:
                            if isinstance(item, dict):
                                # record conid if present
                                if 'conid' in item:
                                    conids.append(item.get('conid'))
                                elif 'contracts' in item and isinstance(item.get('contracts'), list) and item.get('contracts'):
                                    c = item.get('contracts')[0]
                                    if isinstance(c, dict) and c.get('conid'):
                                        conids.append(c.get('conid'))

                                # extract months token from top-level months or sections
                                months_field = item.get('months')
                                if months_field and isinstance(months_field, str):
                                    for m in months_field.split(';'):
                                        tok = m.strip()
                                        if tok:
                                            months_tokens.add(tok)

                                sections = item.get('sections') or []
                                if isinstance(sections, list):
                                    for sec in sections:
                                        if isinstance(sec, dict):
                                            m2 = sec.get('months') or sec.get('months')
                                            if m2 and isinstance(m2, str):
                                                for m in m2.split(';'):
                                                    tok = m.strip()
                                                    if tok:
                                                        months_tokens.add(tok)
                        except Exception:
                            continue

            # If we didn't find conids or months tokens, fall back to next Friday
            if not months_tokens or not conids:
                print(f"DEBUG: No months tokens or conids found for {ticker}, falling back")
                today = datetime.now()
                days_ahead = 4 - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                next_friday = today + timedelta(days_ahead)
                return next_friday.strftime('%Y%m%d')

            # Use a simple per-instance cache to avoid repeated heavy work for the same ticker
            if not hasattr(self, '_closest_expiry_cache'):
                self._closest_expiry_cache = {}
            if ticker and ticker in self._closest_expiry_cache:
                cached = self._closest_expiry_cache.get(ticker)
                if cached:
                    print(f"DEBUG: Returning cached closest expiration for {ticker}: {cached}")
                    return cached

            # For each conid and month token, request strikes first and then probe secdef/info
            # but dramatically limit probes: pick at most 3 strikes per month (closest-to-market, first, last)
            # and enforce a global probe cap. This reduces the number of secdef calls while still
            # finding authoritative maturity dates in most cases.
            maturity_dates = set()
            MAX_PROBES_PER_MONTH = 3
            GLOBAL_PROBE_CAP = 30
            probes_used = 0

            # Get an estimate of the current stock price once to pick the most relevant strike
            market_price = None
            try:
                market_price = self.get_current_stock_price(ticker) if ticker else None
            except Exception:
                market_price = None

            # Decide on a single month token to probe to avoid querying every month in the chain.
            # Preference order:
            # 1) If months_tokens contains the current month token, use it
            # 2) If today is the last day of the month and months_tokens contains next month, use next month
            # 3) Otherwise fall back to the first available month token reported by the chain
            from calendar import monthrange
            today_dt = datetime.now()
            # Build month tokens like 'SEP25'
            cur_month_tok = today_dt.strftime('%b').upper() + today_dt.strftime('%y')
            # Next month handling
            next_month_dt = (today_dt.replace(day=1) + timedelta(days=32)).replace(day=1)
            next_month_tok = next_month_dt.strftime('%b').upper() + next_month_dt.strftime('%y')

            target_months = []
            if months_tokens:
                if cur_month_tok in months_tokens:
                    target_months = [cur_month_tok]
                else:
                    # determine if today is the last day of the month
                    last_day = monthrange(today_dt.year, today_dt.month)[1]
                    if today_dt.day >= last_day and next_month_tok in months_tokens:
                        target_months = [next_month_tok]
                    else:
                        # fallback to first available month token
                        target_months = [sorted(months_tokens)[0]]
            else:
                target_months = []

            # Choose a single primary conid to probe (avoid iterating every matching underlying)
            chosen_conid = None
            if conids:
                # Prefer the first reported conid (search results typically list primary exchange first)
                chosen_conid = conids[0]
                print(f"DEBUG: Using primary conid for probing: {chosen_conid}")
            else:
                chosen_conid = None

            if chosen_conid is None:
                # no conid available - fall back to next Friday
                days_ahead = 4 - datetime.now().weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                next_friday = datetime.now() + timedelta(days_ahead)
                return next_friday.strftime('%Y%m%d')

            # Probe only the chosen conid for the target months
            for month_tok in target_months:
                if probes_used >= GLOBAL_PROBE_CAP:
                    print(f"DEBUG: Global probe cap reached ({GLOBAL_PROBE_CAP}), stopping further secdef calls")
                    break
                try:
                    strikes_result = None
                    try:
                        strikes_result = self.client.search_strikes_by_conid(conid=str(chosen_conid), sec_type='OPT', month=month_tok)
                    except Exception:
                        strikes_result = None

                    strikes_list = []

                    # First, attempt a single unstruck secdef/info call for this month.
                    # This often returns weekly expirations (maturityDate) without needing
                    # to probe many strikes. Count it against the global probe cap.
                    if probes_used < GLOBAL_PROBE_CAP:
                        try:
                            probes_used += 1
                            secdef_all = self.client.search_secdef_info_by_conid(conid=str(chosen_conid), sec_type='OPT', month=month_tok)
                            if secdef_all and hasattr(secdef_all, 'data') and secdef_all.data:
                                secdata = secdef_all.data
                                if isinstance(secdata, list):
                                    for cand in secdata:
                                        if isinstance(cand, dict) and cand.get('maturityDate'):
                                            maturity_dates.add(cand.get('maturityDate'))
                                elif isinstance(secdata, dict) and secdata.get('maturityDate'):
                                    maturity_dates.add(secdata.get('maturityDate'))
                                # If we found maturity dates via the unstruck call, no need to sample strikes
                                if maturity_dates:
                                    # Early exit for this month if we've already gathered usable dates
                                    continue
                        except Exception:
                            # If the API rejects unstruck calls (400), fall back to strike sampling below
                            pass

                    if strikes_result and hasattr(strikes_result, 'data') and strikes_result.data:
                        sd = strikes_result.data
                        if isinstance(sd, dict):
                            if 'call' in sd and isinstance(sd['call'], list):
                                strikes_list.extend(sd['call'])
                            if 'put' in sd and isinstance(sd['put'], list):
                                strikes_list.extend(sd['put'])
                        elif isinstance(sd, list):
                            for it in sd:
                                if isinstance(it, dict) and 'strike' in it:
                                    try:
                                        strikes_list.append(float(it['strike']))
                                    except Exception:
                                        continue
                                elif isinstance(it, (int, float, str)):
                                    try:
                                        strikes_list.append(float(it))
                                    except Exception:
                                        continue

                    # pick a small, high-quality sample of strikes to probe
                    sample = []
                    if strikes_list:
                        strikes_list = sorted(list({float(s) for s in strikes_list}))
                        n = len(strikes_list)
                        # prefer strike closest to market price if available
                        if market_price is not None:
                            try:
                                closest = min(strikes_list, key=lambda s: abs(s - float(market_price)))
                                sample.append(closest)
                            except Exception:
                                pass
                        # always include first and last as backups
                        if n > 0:
                            if strikes_list[0] not in sample:
                                sample.append(strikes_list[0])
                        if n > 1:
                            if strikes_list[-1] not in sample:
                                sample.append(strikes_list[-1])

                        # trim to MAX_PROBES_PER_MONTH
                        sample = sample[:MAX_PROBES_PER_MONTH]

                        # probe secdef info only for this small sample
                        for strike_val in sample:
                            if probes_used >= GLOBAL_PROBE_CAP:
                                break
                            try:
                                probes_used += 1
                                # Preserve decimal strikes (e.g., 187.5) when formatting the strike parameter
                                strike_param = str(int(strike_val)) if float(strike_val).is_integer() else str(strike_val)
                                secdef = self.client.search_secdef_info_by_conid(conid=str(chosen_conid), sec_type='OPT', month=month_tok, strike=strike_param)
                                if secdef and hasattr(secdef, 'data') and secdef.data:
                                    secdata = secdef.data
                                    if isinstance(secdata, list):
                                        for cand in secdata:
                                            if isinstance(cand, dict) and cand.get('maturityDate'):
                                                maturity_dates.add(cand.get('maturityDate'))
                                    elif isinstance(secdata, dict) and secdata.get('maturityDate'):
                                        maturity_dates.add(secdata.get('maturityDate'))
                            except Exception:
                                # skip problematic strikes
                                continue
                    else:
                        # No strikes available: do a single lightweight secdef call as a last resort
                        if probes_used < GLOBAL_PROBE_CAP:
                            try:
                                probes_used += 1
                                secdef = self.client.search_secdef_info_by_conid(conid=str(chosen_conid), sec_type='OPT', month=month_tok)
                                if secdef and hasattr(secdef, 'data') and secdef.data:
                                    secdata = secdef.data
                                    if isinstance(secdata, list):
                                        for cand in secdata:
                                            if isinstance(cand, dict) and cand.get('maturityDate'):
                                                maturity_dates.add(cand.get('maturityDate'))
                                    elif isinstance(secdata, dict) and secdata.get('maturityDate'):
                                        maturity_dates.add(secdata.get('maturityDate'))
                            except Exception:
                                # expected in some environments; continue
                                continue
                except Exception:
                    # ignore and continue
                    continue

            # cache successful result to avoid repeated probing for same ticker
            today = datetime.now().date()
            parsed_dates = []
            for md in maturity_dates:
                try:
                    d = datetime.strptime(md, '%Y%m%d').date()
                    if d >= today:
                        parsed_dates.append(d)
                except Exception:
                    try:
                        d = datetime.fromisoformat(md).date()
                        if d >= today:
                            parsed_dates.append(d)
                    except Exception:
                        continue

            # If we have parsed dates, check for a near-term expiry within EARLY_WINDOW_DAYS.
            EARLY_WINDOW_DAYS = 7
            early_candidates = [d for d in parsed_dates if (d - today).days <= EARLY_WINDOW_DAYS]
            if early_candidates:
                chosen = min(early_candidates)
                result_exp = chosen.strftime('%Y%m%d')
                if ticker:
                    self._closest_expiry_cache[ticker] = result_exp
                return result_exp

            # No near-term expiry under the primary conid; try probing a few additional conids
            if conids and len(conids) > 1:
                ADDITIONAL_CONID_PROBES = 5
                probed = 0
                for extra_conid in conids[1:]:
                    if probed >= ADDITIONAL_CONID_PROBES or probes_used >= GLOBAL_PROBE_CAP:
                        break
                    probed += 1
                    print(f"DEBUG: Probing additional conid {extra_conid} for near-term expirations (probe {probed})")
                    # Try unstruck secdef for target months first
                    for month_tok in target_months:
                        if probes_used >= GLOBAL_PROBE_CAP:
                            break
                        try:
                            probes_used += 1
                            secdef_all = self.client.search_secdef_info_by_conid(conid=str(extra_conid), sec_type='OPT', month=month_tok)
                            if secdef_all and hasattr(secdef_all, 'data') and secdef_all.data:
                                secdata = secdef_all.data
                                if isinstance(secdata, list):
                                    for cand in secdata:
                                        if isinstance(cand, dict) and cand.get('maturityDate'):
                                            maturity_dates.add(cand.get('maturityDate'))
                                elif isinstance(secdata, dict) and secdata.get('maturityDate'):
                                    maturity_dates.add(secdata.get('maturityDate'))
                            # Check for near-term date
                            for md in list(maturity_dates):
                                try:
                                    d = datetime.strptime(md, '%Y%m%d').date()
                                    if d >= today and (d - today).days <= EARLY_WINDOW_DAYS:
                                        chosen = d
                                        result_exp = chosen.strftime('%Y%m%d')
                                        if ticker:
                                            self._closest_expiry_cache[ticker] = result_exp
                                        print(f"DEBUG: Found near-term expiry {result_exp} on conid {extra_conid}")
                                        return result_exp
                                except Exception:
                                    continue
                        except Exception:
                            # ignore and move to next conid
                            continue

                    # If unstruck didn't find near-term dates, try minimal strike sampling on this conid
                    try:
                        strikes_result = None
                        try:
                            strikes_result = self.client.search_strikes_by_conid(conid=str(extra_conid), sec_type='OPT', month=target_months[0])
                        except Exception:
                            strikes_result = None

                        strikes_list = []
                        if strikes_result and hasattr(strikes_result, 'data') and strikes_result.data:
                            sd = strikes_result.data
                            if isinstance(sd, dict):
                                if 'call' in sd and isinstance(sd['call'], list):
                                    strikes_list.extend(sd['call'])
                                if 'put' in sd and isinstance(sd['put'], list):
                                    strikes_list.extend(sd['put'])
                            elif isinstance(sd, list):
                                for it in sd:
                                    if isinstance(it, dict) and 'strike' in it:
                                        try:
                                            strikes_list.append(float(it['strike']))
                                        except Exception:
                                            continue
                                    elif isinstance(it, (int, float, str)):
                                        try:
                                            strikes_list.append(float(it))
                                        except Exception:
                                            continue

                        if strikes_list:
                            strikes_list = sorted(list({float(s) for s in strikes_list}))
                            # pick up to 2 strikes: closest to market and one extreme
                            sample = []
                            if market_price is not None:
                                try:
                                    sample.append(min(strikes_list, key=lambda s: abs(s - float(market_price))))
                                except Exception:
                                    pass
                            if len(strikes_list) > 0:
                                if strikes_list[0] not in sample:
                                    sample.append(strikes_list[0])
                            sample = sample[:2]

                            for strike_val in sample:
                                if probes_used >= GLOBAL_PROBE_CAP:
                                    break
                                try:
                                    probes_used += 1
                                    # Preserve decimal strikes when probing extra conids as well
                                    strike_param = str(int(strike_val)) if float(strike_val).is_integer() else str(strike_val)
                                    secdef = self.client.search_secdef_info_by_conid(conid=str(extra_conid), sec_type='OPT', month=target_months[0], strike=strike_param)
                                    if secdef and hasattr(secdef, 'data') and secdef.data:
                                        secdata = secdef.data
                                        if isinstance(secdata, list):
                                            for cand in secdata:
                                                if isinstance(cand, dict) and cand.get('maturityDate'):
                                                    maturity_dates.add(cand.get('maturityDate'))
                                        elif isinstance(secdata, dict) and secdata.get('maturityDate'):
                                            maturity_dates.add(secdata.get('maturityDate'))
                                        # Check for near-term date
                                        for md in list(maturity_dates):
                                            try:
                                                d = datetime.strptime(md, '%Y%m%d').date()
                                                if d >= today and (d - today).days <= EARLY_WINDOW_DAYS:
                                                    chosen = d
                                                    result_exp = chosen.strftime('%Y%m%d')
                                                    if ticker:
                                                        self._closest_expiry_cache[ticker] = result_exp
                                                    print(f"DEBUG: Found near-term expiry {result_exp} on conid {extra_conid} via strike sampling")
                                                    return result_exp
                                            except Exception:
                                                continue
                                except Exception:
                                    continue
                    except Exception:
                        continue

            # If no near-term expirations were found after probing extra conids, fall back to earliest parsed date if present
            if parsed_dates:
                chosen = min(parsed_dates)
                result_exp = chosen.strftime('%Y%m%d')
                if ticker:
                    self._closest_expiry_cache[ticker] = result_exp
                return result_exp

            # Fallback to next Friday (and cache)
            days_ahead = 4 - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_friday = datetime.now() + timedelta(days_ahead)
            result_exp = next_friday.strftime('%Y%m%d')
            if ticker:
                self._closest_expiry_cache[ticker] = result_exp
            return result_exp

            # Parse and pick earliest maturityDate >= today
            parsed_dates = []
            today = datetime.now().date()
            for md in maturity_dates:
                try:
                    # Expecting YYYYMMDD
                    d = datetime.strptime(md, '%Y%m%d').date()
                    if d >= today:
                        parsed_dates.append(d)
                except Exception:
                    # try ISO format fallback
                    try:
                        d = datetime.fromisoformat(md).date()
                        if d >= today:
                            parsed_dates.append(d)
                    except Exception:
                        continue

            if parsed_dates:
                chosen = min(parsed_dates)
                return chosen.strftime('%Y%m%d')

            # Fallback to next Friday
            days_ahead = 4 - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_friday = datetime.now() + timedelta(days_ahead)
            return next_friday.strftime('%Y%m%d')

        except Exception as e:
            print(f"DEBUG: Error while finding closest expiration for {ticker}: {e}")
            today = datetime.now()
            days_ahead = 4 - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_friday = today + timedelta(days_ahead)
            return next_friday.strftime('%Y%m%d')
    
    def _convert_date_format(self, date_str: str) -> str:
        """Convert M/D format to YYYYMMDD format"""
        try:
            from datetime import datetime
            
            # Split M/D
            month, day = date_str.split('/')
            current_year = datetime.now().year
            
            # Pad with zeros if needed
            month = month.zfill(2)
            day = day.zfill(2)
            
            return f"{current_year}{month}{day}"
            
        except Exception as e:
            print(f"ERROR: Could not convert date {date_str}: {e}")
            # Fallback to closest expiration
            return self._get_closest_expiration("")
    
    def get_current_stock_price(self, ticker: str) -> float:
        """
        Get current stock price using existing market data infrastructure
        """
        try:
            print(f"DEBUG: Getting current stock price for {ticker}")
            
            # Get stock contract details first
            contracts = self.client.search_contract_by_symbol(symbol=ticker, sec_type="STK")
            if not contracts or not contracts.data:
                print(f"ERROR: Could not find stock contract for {ticker}")
                return None
                
            # Get the first contract (usually the primary exchange)
            stock_contract = contracts.data[0]
            conid = stock_contract.get('conid')
            
            if not conid:
                print(f"ERROR: No contract ID found for {ticker}")
                return None
                
            print(f"DEBUG: Found stock contract ID {conid} for {ticker}")
            
            # Use existing market data method to get current price (field 31 = last price)
            market_data = self._request_market_data_with_retry(str(conid), ["31"], max_retries=3)
            
            if market_data and "31" in market_data:
                current_price = float(market_data["31"])
                print(f"DEBUG: Current price for {ticker}: ${current_price}")
                return current_price
            else:
                print(f"ERROR: No price data found for {ticker}")
                return None
                
        except Exception as e:
            print(f"ERROR: Could not get current stock price for {ticker}: {e}")
            return None

    async def get_stock_conid(self, ticker: str) -> Optional[int]:
        """
        Get stock CONID by ticker symbol
        """
        try:
            logger.debug(f"Getting stock CONID for {ticker}")
            
            # Search for stock contract
            contracts = self.client.search_contract_by_symbol(symbol=ticker, sec_type="STK")
            if not contracts or not contracts.data:
                logger.debug(f"No stock contract found for {ticker}")
                return None
                
            # Get the first contract (usually the primary exchange)
            stock_contract = contracts.data[0]
            conid = stock_contract.get('conid')
            
            if conid:
                logger.debug(f"Found stock CONID {conid} for {ticker}")
                return int(conid)
            else:
                logger.debug(f"No CONID in contract data for {ticker}")
                return None
                
        except Exception as e:
            logger.debug(f"Error getting stock CONID for {ticker}: {e}")
            return None

    async def get_index_conid(self, symbol: str) -> Optional[int]:
        """
        Get index CONID by symbol (e.g., SPX)
        """
        try:
            logger.debug(f"Getting index CONID for {symbol}")
            
            # Search for index contract (use IND sec_type for indices)
            contracts = self.client.search_contract_by_symbol(symbol=symbol, sec_type="IND")
            if not contracts or not contracts.data:
                logger.debug(f"No index contract found for {symbol}")
                return None
                
            # Get the first contract
            index_contract = contracts.data[0]
            conid = index_contract.get('conid')
            
            if conid:
                logger.debug(f"Found index CONID {conid} for {symbol}")
                return int(conid)
            else:
                logger.debug(f"No CONID in contract data for {symbol}")
                return None
                
        except Exception as e:
            logger.debug(f"Error getting index CONID for {symbol}: {e}")
            return None

    async def get_option_conid(self, ticker: str, strike: float, side: str, expiry: str) -> Optional[int]:
        """
        Get option contract CONID for a given ticker/strike/side/expiry
        
        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            strike: Strike price (e.g., 175.0)
            side: 'CALL' or 'PUT'
            expiry: Expiry date in various formats (e.g., '10/25', '1025', 'OCT25')
        
        Returns:
            Option contract CONID or None if not found
        """
        try:
            logger.debug(f"Getting option CONID for {ticker} {strike}{side[0]} {expiry}")
            
            # Convert side to IBKR format
            right = "C" if side.upper() == "CALL" else "P"
            
            # Use existing method to get contract details
            contract_details = self.get_option_contract_details(
                symbol=ticker,
                strike=strike,
                right=right,
                expiry=expiry
            )
            
            if contract_details and 'conid' in contract_details:
                conid = contract_details['conid']
                logger.debug(f"Found option CONID {conid} for {ticker} {strike}{right} {expiry}")
                return int(conid)
            else:
                logger.debug(f"No option contract found for {ticker} {strike}{right} {expiry}")
                return None
                
        except Exception as e:
            logger.debug(f"Error getting option CONID for {ticker} {strike}{side} {expiry}: {e}")
            return None

    def detect_short_dated_expirations(self, ticker: str, lookahead_days: int = 10, conid_probe_count: int = 5, months_probe_count: int = 3) -> dict:
        """
        Heuristic detection of daily/weekly expirations for a ticker.

        Strategy:
        - Use search_contract_by_symbol to find a few conids
        - For each conid, call search_secdef_info_by_conid for the current month (unstruck)
        - Collect maturityDate values and classify any maturities within `lookahead_days` as daily/weekly

        Returns dict with keys: has_daily, has_weekly, nearest_daily (date), nearest_weekly (date)
        """
        from datetime import datetime, timedelta
        try:
            print(f"DEBUG: Detecting short-dated expirations for {ticker}")
            res = {"has_daily": False, "has_weekly": False, "nearest_daily": None, "nearest_weekly": None}

            search_result = self.client.search_contract_by_symbol(symbol=ticker, sec_type='OPT')
            conids = []
            months_tokens = []
            if search_result and hasattr(search_result, 'data') and search_result.data:
                data = search_result.data
                if isinstance(data, list):
                    for item in data:
                        try:
                            if isinstance(item, dict):
                                # collect conids
                                if 'conid' in item:
                                    conids.append(item.get('conid'))
                                elif 'contracts' in item and isinstance(item.get('contracts'), list) and item.get('contracts'):
                                    c = item.get('contracts')[0]
                                    if isinstance(c, dict) and c.get('conid'):
                                        conids.append(c.get('conid'))
                                # collect months tokens if present
                                if 'months' in item and item.get('months'):
                                    mt = item.get('months')
                                    if isinstance(mt, str):
                                        # months string like 'SEP25;OCT25;...'
                                        months_tokens.extend([t for t in mt.split(';') if t])
                                    elif isinstance(mt, list):
                                        months_tokens.extend([t for t in mt if t])
                        except Exception:
                            continue

            if not conids:
                return res

            # determine months to probe: prefer months_tokens from chain, fallback to current month
            if months_tokens:
                months_to_probe = months_tokens[:months_probe_count]
            else:
                months_to_probe = [datetime.now().strftime('%b').upper() + datetime.now().strftime('%y')]

            today = datetime.now().date()
            maturities = set()
            # probe each conid (up to conid_probe_count) and for each probe a few months
            for cid in conids[:conid_probe_count]:
                try:
                    for m in months_to_probe:
                        try:
                            secdef_all = self.client.search_secdef_info_by_conid(conid=str(cid), sec_type='OPT', month=m)
                            if secdef_all and hasattr(secdef_all, 'data') and secdef_all.data:
                                secdata = secdef_all.data
                                if isinstance(secdata, list):
                                    for cand in secdata:
                                        if isinstance(cand, dict) and cand.get('maturityDate'):
                                            maturities.add(cand.get('maturityDate'))
                                elif isinstance(secdata, dict) and secdata.get('maturityDate'):
                                    maturities.add(secdata.get('maturityDate'))
                        except Exception:
                            # try next month
                            continue
                except Exception:
                    continue

            # classify maturities
            daily_candidates = []
            weekly_candidates = []
            for md in maturities:
                try:
                    d = datetime.strptime(md, '%Y%m%d').date()
                except Exception:
                    try:
                        d = datetime.fromisoformat(md).date()
                    except Exception:
                        continue

                days_out = (d - today).days
                if 0 <= days_out <= 1:
                    daily_candidates.append(d)
                if 0 <= days_out <= lookahead_days:
                    weekly_candidates.append(d)

            if daily_candidates:
                res['has_daily'] = True
                res['nearest_daily'] = min(daily_candidates)
            if weekly_candidates:
                res['has_weekly'] = True
                res['nearest_weekly'] = min(weekly_candidates)

            return res
        except Exception as e:
            print(f"DEBUG: detect_short_dated_expirations error: {e}")
            return {"has_daily": False, "has_weekly": False, "nearest_daily": None, "nearest_weekly": None}

    def find_all_chain_maturities(self, ticker: str, max_conids: int = 50, max_months_per_item: int = 12) -> dict:
        """
        Diagnostic: enumerate chain conids/month tokens for a ticker and collect all maturityDate values.

        Returns dict: {
            'conids': [list of conids],
            'months_tokens': [list of tokens],
            'maturities': { conid: { month_token: [maturityDate,...], ... }, ... }
        }
        """
        out = {"conids": [], "months_tokens": [], "maturities": {}}
        try:
            search_result = self.client.search_contract_by_symbol(symbol=ticker, sec_type='OPT')
            items = []
            if search_result and hasattr(search_result, 'data') and search_result.data:
                data = search_result.data
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = [data]

            # collect conids and months tokens
            conids = []
            months = []
            for it in items:
                if isinstance(it, dict):
                    if 'conid' in it:
                        conids.append(it.get('conid'))
                    if 'contracts' in it and isinstance(it.get('contracts'), list):
                        for c in it.get('contracts'):
                            if isinstance(c, dict) and c.get('conid'):
                                conids.append(c.get('conid'))
                    if 'months' in it and it.get('months'):
                        mt = it.get('months')
                        if isinstance(mt, str):
                            months.extend([t for t in mt.split(';') if t])
                        elif isinstance(mt, list):
                            months.extend([t for t in mt if t])

            # de-dup and limit
            conids = list(dict.fromkeys([str(c) for c in conids]))[:max_conids]
            months = list(dict.fromkeys(months))[:max_months_per_item]
            out['conids'] = conids
            out['months_tokens'] = months

            for cid in conids:
                out['maturities'].setdefault(cid, {})
                # try each month token first with unstruck secdef/info
                for m in months:
                    try:
                        secdef_all = self.client.search_secdef_info_by_conid(conid=str(cid), sec_type='OPT', month=m)
                        if secdef_all and hasattr(secdef_all, 'data') and secdef_all.data:
                            secdata = secdef_all.data
                            collected = []
                            if isinstance(secdata, list):
                                for cand in secdata:
                                    if isinstance(cand, dict) and cand.get('maturityDate'):
                                        collected.append(cand.get('maturityDate'))
                            elif isinstance(secdata, dict) and secdata.get('maturityDate'):
                                collected.append(secdata.get('maturityDate'))
                            if collected:
                                out['maturities'][cid][m] = collected
                                continue
                    except Exception:
                        # ignore and proceed to try strikes
                        pass

                # if no maturities found via unstruck info, fetch a few strikes and call secdef/info with strike
                try:
                    strikes_res = self.client.search_strikes_by_conid(conid=str(cid), sec_type='OPT', month=months[0] if months else None)
                    strikes = []
                    if strikes_res and hasattr(strikes_res, 'data') and strikes_res.data:
                        sd = strikes_res.data
                        if isinstance(sd, list):
                            strikes = sd
                        elif isinstance(sd, dict) and 'strikes' in sd:
                            strikes = sd.get('strikes')
                    # sample up to 5 strikes
                    for s in (strikes[:5] if isinstance(strikes, list) else []):
                        try:
                            secdef = self.client.search_secdef_info_by_conid(conid=str(cid), sec_type='OPT', month=months[0] if months else None, strike=str(s))
                            if secdef and hasattr(secdef, 'data') and secdef.data:
                                secdata = secdef.data
                                collected = []
                                if isinstance(secdata, list):
                                    for cand in secdata:
                                        if isinstance(cand, dict) and cand.get('maturityDate'):
                                            collected.append(cand.get('maturityDate'))
                                elif isinstance(secdata, dict) and secdata.get('maturityDate'):
                                    collected.append(secdata.get('maturityDate'))
                                if collected:
                                    out['maturities'][cid].setdefault(f'strike_{s}', []).extend(collected)
                        except Exception:
                            continue
                except Exception:
                    continue

            return out
        except Exception as e:
            print(f"DEBUG: find_all_chain_maturities error: {e}")
            return out

    def get_available_strikes(self, ticker: str, expiry: str) -> list:
        """
        Get available option strikes for a ticker and expiration date
        
        Args:
            ticker: Stock symbol (e.g., "TSLA")
            expiry: Expiration date in YYYYMMDD format (e.g., "20250919")
            
        Returns:
            List of available strike prices as floats
        """
        try:
            print(f"DEBUG: Getting available strikes for {ticker} expiring {expiry}")
            
            # Get stock contract ID first
            contracts = self.client.search_contract_by_symbol(symbol=ticker, sec_type="STK")
            if not contracts or not contracts.data:
                print(f"ERROR: Could not find stock contract for {ticker}")
                return []
                
            stock_contract = contracts.data[0]
            conid = stock_contract.get('conid')
            
            if not conid:
                print(f"ERROR: No contract ID found for {ticker}")
                return []
                
            print(f"DEBUG: Found stock contract ID {conid} for {ticker}")
            
            # Convert YYYYMMDD to MMMYY format for IBKR API
            # e.g., "20250919" -> "SEP25"
            from datetime import datetime
            expiry_date = datetime.strptime(expiry, "%Y%m%d")
            month_abbr = expiry_date.strftime("%b").upper()  # SEP
            year_abbr = expiry_date.strftime("%y")  # 25
            month_year = f"{month_abbr}{year_abbr}"  # SEP25
            
            print(f"DEBUG: Converted expiry {expiry} to month format {month_year}")
            
            # Get available strikes using search_strikes_by_conid
            strikes_result = self.client.search_strikes_by_conid(
                conid=str(conid),
                sec_type="OPT",
                month=month_year
            )
            
            if strikes_result and hasattr(strikes_result, 'data') and strikes_result.data:
                print(f"DEBUG: Raw strikes result: {strikes_result.data}")
                
                # Extract strike prices from the response
                strikes = []
                strikes_data = strikes_result.data
                
                if isinstance(strikes_data, dict):
                    # Handle the case where data is a dict with 'call' and 'put' keys
                    if 'call' in strikes_data:
                        strikes.extend(strikes_data['call'])
                    if 'put' in strikes_data:
                        strikes.extend(strikes_data['put'])
                elif isinstance(strikes_data, list):
                    # Handle the case where data is a list of items
                    for item in strikes_data:
                        if isinstance(item, dict) and 'strike' in item:
                            strike = float(item['strike'])
                            strikes.append(strike)
                        elif isinstance(item, (str, int, float)):
                            # Sometimes strikes come as strings or numbers
                            try:
                                strike = float(item)
                                strikes.append(strike)
                            except ValueError:
                                continue
                
                strikes = sorted(list(set(strikes)))  # Remove duplicates and sort
                print(f"DEBUG: Available strikes for {ticker} {month_year}: {strikes}")
                return strikes
            else:
                print(f"ERROR: No strikes data found for {ticker} {month_year}")
                return []
                
        except Exception as e:
            print(f"ERROR: Could not get available strikes for {ticker}: {e}")
            return []

    def _get_closest_itm_strike(self, ticker: str, action: str, option_type: str, expiry: str = None) -> float:
        """
        Get closest ITM strike based on current stock price from available strikes
        
        Logic:
        - LONG calls: Strike below current price (ITM call)
        - SHORT puts: Strike above current price (ITM put)
        
        Args:
            ticker: Stock symbol (e.g., "TSLA")
            action: "LONG" or "SHORT"
            option_type: "CALL" or "PUT"
            expiry: Expiration date in YYYYMMDD format (optional, uses default if not provided)
        """
        try:
            # Get current stock price using existing infrastructure
            current_price = self.get_current_stock_price(ticker)
            
            if current_price is None:
                print(f"WARNING: Could not get current price for {ticker}, using default")
                return 100.0  # Fallback default
            
            print(f"DEBUG: Current {ticker} price: ${current_price}")
            
            # Use a default expiry if not provided (e.g., next month)
            if expiry is None:
                from datetime import datetime, timedelta
                next_month = datetime.now() + timedelta(days=30)
                expiry = next_month.strftime("%Y%m%d")
                print(f"DEBUG: Using default expiry: {expiry}")
            
            # Get available strikes for this ticker and expiration
            available_strikes = self.get_available_strikes(ticker, expiry)
            
            if not available_strikes:
                print(f"WARNING: No available strikes found for {ticker}, using calculated default")
                # Fall back to calculated strikes if we can't get available ones
                if action == "LONG" and option_type == "CALL":
                    return round(current_price * 0.95, 0)
                elif action == "SHORT" and option_type == "PUT":
                    return round(current_price * 1.05, 0)
                else:
                    return round(current_price, 0)
            
            print(f"DEBUG: Found {len(available_strikes)} available strikes")
            
            # Find the closest ITM strike from available strikes
            if action == "LONG" and option_type == "CALL":
                # For LONG calls, we want ITM (strike < current price)
                itm_strikes = [strike for strike in available_strikes if strike < current_price]
                if itm_strikes:
                    # Get the highest ITM strike (closest to current price)
                    closest_itm = max(itm_strikes)
                    print(f"DEBUG: LONG CALL closest ITM strike for {ticker}: ${closest_itm}")
                    return closest_itm
                else:
                    # No ITM strikes available, get the lowest available strike
                    closest_itm = min(available_strikes)
                    print(f"DEBUG: No ITM strikes available, using lowest: ${closest_itm}")
                    return closest_itm
                    
            elif action == "SHORT" and option_type == "PUT":
                # For SHORT puts, we want ITM (strike > current price)
                itm_strikes = [strike for strike in available_strikes if strike > current_price]
                if itm_strikes:
                    # Get the lowest ITM strike (closest to current price)
                    closest_itm = min(itm_strikes)
                    print(f"DEBUG: SHORT PUT closest ITM strike for {ticker}: ${closest_itm}")
                    return closest_itm
                else:
                    # No ITM strikes available, get the highest available strike
                    closest_itm = max(available_strikes)
                    print(f"DEBUG: No ITM strikes available, using highest: ${closest_itm}")
                    return closest_itm
                    
            else:
                # Default case - find strike closest to current price
                closest_strike = min(available_strikes, key=lambda x: abs(x - current_price))
                print(f"DEBUG: Default closest strike for {ticker}: ${closest_strike}")
                return closest_strike
                
        except Exception as e:
            print(f"ERROR: Could not get ITM strike for {ticker}: {e}")
            return 100.0  # Safe default


# Global instance
ibkr_service = IBKRService()
