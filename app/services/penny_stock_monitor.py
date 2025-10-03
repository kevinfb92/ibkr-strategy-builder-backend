import os
import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class PennyStockMonitor:
    """Simple JSON-backed storage for penny stock opening orders.

    Stores records keyed by order_id with ticker and metadata.
    The storage file can be overridden via the PENNY_MONITOR_STORAGE environment variable
    (useful for tests/dev to avoid clobbering the production file).
    """

    def __init__(self, storage_file: str | None = None):
        # Allow override by environment variable for test/dev isolation
        chosen = storage_file or os.environ.get('PENNY_MONITOR_STORAGE') or 'penny_stock_orders.json'
        self.storage_path = Path(chosen)
        self.lock = Lock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.storage_path.exists():
                with self.storage_path.open("r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                    # Support two on-disk shapes:
                    # 1) legacy flat mapping: { parent_id: {..parent record..}, ... }
                    # 2) per-ticker mapping: { TICKER: { 'ticker': TICKER, 'minimum_variation': x, 'orders': [..] }, ... }
                    if isinstance(raw, dict):
                        # detect legacy flat shape by checking keys for 'parent_order_id' presence
                        some_vals = list(raw.values())
                        if some_vals and isinstance(some_vals[0], dict) and 'parent_order_id' in some_vals[0]:
                            # migrate legacy flat -> per-ticker grouped
                            migrated: Dict[str, Dict[str, Any]] = {}
                            for parent_id, rec in raw.items():
                                ticker = (rec.get('ticker') or '').upper() or 'UNKNOWN'
                                t = migrated.setdefault(ticker, {'ticker': ticker, 'minimum_variation': rec.get('minimum_variation', 0.001), 'orders': []})
                                t['orders'].append(rec)
                            self._data = migrated
                        else:
                            # assume already per-ticker mapping
                                    self._data = raw
                                    # Normalize any legacy `freeRunner` keys to `free_runner` in loaded records
                                    try:
                                        for tinfo in self._data.values():
                                            for o in (tinfo.get('orders') or []):
                                                if 'freeRunner' in o and 'free_runner' not in o:
                                                    o['free_runner'] = bool(o.pop('freeRunner'))
                                    except Exception:
                                        pass
                    else:
                        # unexpected format, start empty
                        self._data = {}
                    # report approximate count of parent orders
                    total = sum(len(v.get('orders') or []) for v in self._data.values())
                    logger.debug(f"Loaded penny stock monitor data: {total} parent orders across {len(self._data)} tickers")
        except Exception as e:
            logger.exception(f"Failed to load {self.storage_path}: {e}")
            self._data = {}

    def _save(self) -> None:
        try:
            # Ensure parent orders are stored grouped by ticker (new shape)
            with self.storage_path.open("w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, default=str)
        except Exception:
            logger.exception(f"Failed to save {self.storage_path}")

    def add_orders(self, orders: List[Dict[str, Any]]) -> List[str]:
        """Add multiple opening orders.

        New expected shape: a list where each item is a dict:
        {
            "ticker": "ABC",
            "orders": [
                {
                    "parent_order_id": "p1",
                    # optional
                    "limit_sell": {"order_id": "l1", "price": 1.23},
                    "stop_loss": {"order_id": "s1", "price": 0.9}
                },
                ...
            ]
        }

        We store each parent order keyed by its parent_order_id. Child orders (limit_sell/stop_loss)
        are embedded in that record for lookup/cleanup.

        Returns list of added parent_order_ids (duplicates ignored).
        """
        added: List[str] = []
        now = datetime.utcnow().isoformat()
        with self.lock:
            for item in orders:
                ticker = (item.get("ticker") or "").strip().upper()
                parents = item.get("orders") or []
                if not ticker or not isinstance(parents, list):
                    continue
                t = self._data.setdefault(ticker, {'ticker': ticker, 'minimum_variation': float(item.get('minimum_variation', 0.001)), 'orders': []})
                
                # Extract and store strategy-level fields at ticker root level
                if 'entry_price' in item:
                    try:
                        t['entry_price'] = None if item.get('entry_price') is None else float(item.get('entry_price'))
                    except Exception:
                        pass
                
                if 'freeRunner' in item:
                    try:
                        t['freeRunner'] = bool(item.get('freeRunner'))
                    except Exception:
                        pass
                elif 'free_runner' in item:
                    try:
                        t['free_runner'] = bool(item.get('free_runner'))
                    except Exception:
                        pass
                
                if 'price_targets' in item:
                    try:
                        targets = item.get('price_targets')
                        if isinstance(targets, list):
                            t['price_targets'] = [float(x) for x in targets if x is not None]
                        else:
                            t['price_targets'] = []
                    except Exception:
                        t['price_targets'] = []
                for parent in parents:
                    parent_id = parent.get("parent_order_id")
                    if parent_id is None:
                        continue
                    parent_id = str(parent_id)
                    # skip duplicates by parent_order_id
                    if any((o.get('parent_order_id') or o.get('parent') or '') == parent_id for o in t['orders']):
                        continue

                    # Normalize child orders
                    limit_sell = parent.get("limit_sell")
                    stop_loss = parent.get("stop_loss")

                    record: Dict[str, Any] = {
                        "ticker": ticker,
                        "parent_order_id": parent_id,
                        "created_at": parent.get('created_at') or now,
                        "status": parent.get('status') or "OPEN",
                        "limit_sell": None,
                        "stop_loss": None,
                        # Optional trading hints
                        "target_price": None,
                        "stop_loss_price": None,
                        "free_runner": False,
                        "minimum_variation": float(item.get('minimum_variation', 0.001)),
                    }

                    if isinstance(limit_sell, str) and limit_sell:
                        record["limit_sell"] = {"order_id": str(limit_sell)}
                    elif isinstance(limit_sell, dict):
                        record["limit_sell"] = limit_sell

                    if isinstance(stop_loss, str) and stop_loss:
                        record["stop_loss"] = {"order_id": str(stop_loss)}
                    elif isinstance(stop_loss, dict):
                        record["stop_loss"] = stop_loss

                    # Optional hint fields that may be present on the parent
                    try:
                        if 'target_price' in parent:
                            record['target_price'] = None if parent.get('target_price') is None else float(parent.get('target_price'))
                    except Exception:
                        record['target_price'] = None

                    try:
                        if 'stop_loss_price' in parent:
                            record['stop_loss_price'] = None if parent.get('stop_loss_price') is None else float(parent.get('stop_loss_price'))
                    except Exception:
                        record['stop_loss_price'] = None

                    try:
                        # Allow either camelCase `freeRunner` or snake_case `free_runner` in input
                        if 'freeRunner' in parent:
                            record['free_runner'] = bool(parent.get('freeRunner'))
                        elif 'free_runner' in parent:
                            record['free_runner'] = bool(parent.get('free_runner'))
                    except Exception:
                        record['free_runner'] = False

                    t['orders'].append(record)
                    added.append(parent_id)

            if added:
                self._save()

        return added

    def list_orders(self) -> List[Dict[str, Any]]:
        # Return flattened list of parent-order records across tickers
        with self.lock:
            out: List[Dict[str, Any]] = []
            for t, info in self._data.items():
                orders = info.get('orders') or []
                for o in orders:
                    out.append(o)
            return out

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            oid = str(order_id)
            for t, info in self._data.items():
                for o in (info.get('orders') or []):
                    if str(o.get('parent_order_id') or o.get('parent') or '') == oid:
                        return o
            return None

    def remove_order(self, order_id: str) -> bool:
        with self.lock:
            oid = str(order_id)
            changed = False
            for t, info in list(self._data.items()):
                orders = info.get('orders') or []
                new_orders = [o for o in orders if str(o.get('parent_order_id') or o.get('parent') or '') != oid]
                if len(new_orders) != len(orders):
                    info['orders'] = new_orders
                    changed = True
            if changed:
                self._save()
            return changed

    def update_order_status(self, order_id: str, status: str, details: dict = None) -> bool:
        """Update stored order status and persist extra details.

        Returns True when an existing record was updated.
        """
        with self.lock:
            oid = str(order_id)
            for t, info in self._data.items():
                for o in (info.get('orders') or []):
                    if str(o.get('parent_order_id') or o.get('parent') or '') == oid:
                        # Normalize status
                        try:
                            o['status'] = str(status).upper()
                        except Exception:
                            o['status'] = status

                        # Attach details
                        if details:
                            o.setdefault('last_update', {})
                            o['last_update'].update(details)
                            o['last_update']['updated_at'] = datetime.utcnow().isoformat()

                        # persist
                        self._save()
                        return True
            return False


penny_stock_monitor = PennyStockMonitor()
