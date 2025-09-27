from app.services.ibkr_service import IBKRService

if __name__ == '__main__':
    svc = IBKRService()
    print('--- START _get_closest_expiration(TXN) ---')
    res = svc._get_closest_expiration('TXN')
    print('--- RESULT:', res, '---')
