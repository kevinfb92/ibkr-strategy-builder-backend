import os
os.environ['PENNY_MONITOR_STORAGE'] = 'penny_stock_orders.test.json'

from app.services.penny_stock_watcher import penny_stock_watcher
from app.services.penny_stock_monitor import penny_stock_monitor
import time, json

# Clear monitor state
penny_stock_monitor._data = {}
# persist
penny_stock_monitor._save()

rec = {
    'parent_order_id': 'parent-123',
    'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
    'status': 'OPEN',
    'limit_sell': None,
    'stop_loss': None,
}
# insert via public API
penny_stock_monitor.add_orders([{'ticker': 'ABC', 'orders': [rec], 'minimum_variation': 0.001}])

msg = {
    'data': {
        'parentOrderId': 'parent-123',
        'orderId': 'child-xyz',
        'status': 'FILLED',
        'filled': 1,
        'avgPrice': 0.5,
    }
}

penny_stock_watcher._handle_order_message(msg)
updated = penny_stock_monitor.get_order('parent-123')
print('status =', updated['status'])
print('last_update =', json.dumps(updated.get('last_update'), indent=2))
