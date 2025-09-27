import sys
import json
sys.path.insert(0, r"c:\Users\kevin\Desktop\trading\stoqey\ibkr-strategy-builder-backend")

from app.services.ibkr_service import IBKRService


def main():
    svc = IBKRService()
    print("Calling svc.search_contract_by_symbol(symbol='AAPL', sec_type='OPT')...")
    try:
        res = svc.search_contract_by_symbol(symbol='AAPL', sec_type='OPT')
        print("repr(res):", repr(res))
        data = getattr(res, 'data', None)
        print("type(data):", type(data))
        try:
            print(json.dumps(data, default=str, indent=2))
        except Exception:
            print(data)
    except Exception as e:
        print("search_contract_by_symbol failed:", e)


if __name__ == '__main__':
    main()
