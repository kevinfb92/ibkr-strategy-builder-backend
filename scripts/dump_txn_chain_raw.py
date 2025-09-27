import json
from app.services.ibkr_service import IBKRService


def dump_raw_chain(ticker: str = 'TXN'):
    svc = IBKRService()
    client = svc.client

    print('=== Calling /iserver/secdef/search for', ticker)
    try:
        res = client.search_contract_by_symbol(symbol=ticker, sec_type='OPT')
        data = getattr(res, 'data', None)
        print(json.dumps({'raw_search': data}, indent=2, default=str))
    except Exception as e:
        print('ERROR calling secdef/search:', e)
        return

    # collect conids from the raw search response
    conids = set()
    try:
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            items = []

        for it in items:
            if not isinstance(it, dict):
                continue
            if 'conid' in it:
                conids.add(str(it.get('conid')))
            if 'contracts' in it and isinstance(it.get('contracts'), list):
                for c in it.get('contracts'):
                    if isinstance(c, dict) and c.get('conid'):
                        conids.add(str(c.get('conid')))
            # sometimes months tokens are in `months` key; print if present
            if 'months' in it and it.get('months'):
                print('found months token in search item:', it.get('months'))
    except Exception as e:
        print('ERROR parsing search result:', e)

    print('\n=== Found conids:', list(conids))

    # For each conid call unstruck secdef/info (no month/strike)
    for cid in list(conids):
        print('\n--- Calling /iserver/secdef/info unstruck for conid', cid)
        try:
            info = client.search_secdef_info_by_conid(conid=cid, sec_type='OPT')
            print(json.dumps({'conid': cid, 'raw_info': getattr(info, 'data', None)}, indent=2, default=str))
        except Exception as e:
            print('ERROR calling secdef/info for conid', cid, e)


if __name__ == '__main__':
    dump_raw_chain('TXN')
