import sys
sys.path.insert(0, r'c:/Users/kevin/Desktop/trading/stoqey/ibkr-strategy-builder-backend')
from app.routers.internal_router import ibkr_positions
try:
    res = ibkr_positions()
    print('OK, endpoint callable, sample count:', res.get('count'))
except Exception as e:
    print('ERROR calling endpoint:', e)
