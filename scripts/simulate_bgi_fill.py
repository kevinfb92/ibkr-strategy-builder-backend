import os
os.environ['PENNY_MONITOR_STORAGE'] = 'penny_stock_orders.json'
from app.services.penny_stock_watcher import penny_stock_watcher
from app.services.penny_stock_monitor import penny_stock_monitor
import json

# Simulate IBKR message referencing parent 851924817
msg = {'data': {'parentOrderId': '851924817', 'orderId': 'child-fill-1', 'status': 'FILLED', 'filled': 1, 'avgPrice': 0.5}}

penny_stock_watcher._handle_order_message(msg)
updated = penny_stock_monitor.get_order('851924817')
print('updated status =', updated.get('status') if updated else None)
print(json.dumps(updated.get('last_update', {}), indent=2))
