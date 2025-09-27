from app.services.ibkr_service import IBKRService

if __name__ == '__main__':
    svc = IBKRService()
    out = svc.find_all_chain_maturities('TXN')
    import json
    print(json.dumps(out, indent=2))
