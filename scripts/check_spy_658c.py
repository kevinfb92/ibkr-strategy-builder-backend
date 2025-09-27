import sys, traceback
sys.path.insert(0, r"c:\Users\kevin\Desktop\trading\stoqey\ibkr-strategy-builder-backend")
from app.services.ibkr_service import IBKRService

def main():
    symbol = 'SPY'
    strike = 658.0
    right = 'C'
    expiry = '9/16'

    try:
        svc = IBKRService()
    except Exception as e:
        print(f"Failed to init IBKRService: {e}")
        traceback.print_exc()
        return

    try:
        details = svc.get_option_contract_details(symbol=symbol, strike=strike, right=right, expiry=expiry)
        print("get_option_contract_details ->", details)
    except Exception as e:
        print(f"get_option_contract_details failed: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    main()
