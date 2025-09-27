"""
Lightweight fake IBKRService for unit tests.

Provides a FakeIBKR class with methods used by the code under test:
- get_positions
- get_formatted_positions
- get_option_contract_details
- get_option_market_data
- place_order_with_confirmations

Usage:
    from tests.helpers.fake_ibkr import FakeIBKR
    fake = FakeIBKR()
    fake.add_position({...})

Tests can monkeypatch the real IBKRService with FakeIBKR via conftest fixture.
"""

from typing import List, Dict, Any
import uuid

class FakeIBKR:
    def __init__(self):
        # positions stored as list of dicts
        self._positions: List[Dict[str, Any]] = []
        # simple mapping for option contract details
        self._contract_db: Dict[str, Dict[str, Any]] = {}
        # placed orders log
        self.orders: List[Dict[str, Any]] = []

    def reset(self):
        self._positions = []
        self._contract_db = {}
        self.orders = []

    def add_position(self, pos: Dict[str, Any]):
        # pos should include keys: symbol, position, secType/assetClass, contractDesc (optional), mktValue, unrealizedPnl, realizedPnl, avgPrice, currentPrice
        self._positions.append(pos)

    def set_contract(self, key: str, contract: Dict[str, Any]):
        self._contract_db[key] = contract

    def get_positions(self) -> List[Dict[str, Any]]:
        return list(self._positions)

    def get_formatted_positions(self) -> List[Dict[str, Any]]:
        # Return positions in the 'formatted' style used by the app
        formatted = []
        for p in self._positions:
            formatted.append({
                'symbol': p.get('symbol'),
                'secType': p.get('secType') or p.get('assetClass'),
                'position': p.get('position', 0),
                'unrealizedPnl': p.get('unrealizedPnl'),
                'realizedPnl': p.get('realizedPnl'),
                'marketValue': p.get('mktValue') or p.get('marketValue'),
                'avgPrice': p.get('avgPrice'),
                'currentPrice': p.get('mktPrice') or p.get('currentPrice'),
                'description': p.get('contractDesc') or p.get('description')
            })
        return formatted

    def get_option_contract_details(self, symbol=None, strike=None, right=None, expiry=None):
        key = f"{symbol}:{expiry}:{strike}:{right}"
        return self._contract_db.get(key)

    def get_option_market_data(self, contract):
        # simple fake bid/ask/last
        if not contract:
            return None
        return {
            'bid': contract.get('bid', 1.0),
            'ask': contract.get('ask', 1.5),
            'last': contract.get('last', 1.25),
            'open_interest': contract.get('open_interest', 0)
        }

    def place_order_with_confirmations(self, order_request):
        # simulate filling immediately for tests
        order_id = str(uuid.uuid4())[:8]
        # the order_request may be a dict or object; normalize
        if hasattr(order_request, 'to_dict'):
            o = order_request.to_dict()
        elif isinstance(order_request, dict):
            o = dict(order_request)
        else:
            # best effort: extract attributes
            o = {k: getattr(order_request, k) for k in dir(order_request) if not k.startswith('_') and not callable(getattr(order_request, k))}

        result = {
            'order_id': order_id,
            'filled_quantity': o.get('quantity', o.get('filled_quantity', 0)),
            'status': 'FILLED'
        }
        self.orders.append({'order': o, 'result': result})

        # If it's a close, update positions accordingly (decrement matching positions)
        try:
            if o.get('is_close'):
                qty = int(o.get('quantity', 0))
                # naive: reduce first matching option position by qty
                for p in self._positions:
                    sym = p.get('symbol') or p.get('contractDesc') or ''
                    if o.get('symbol') and o.get('symbol').upper() in (sym or '').upper():
                        pos_qty = int(p.get('position', 0))
                        new_qty = pos_qty - qty
                        p['position'] = new_qty
                        break
        except Exception:
            pass

        return result
