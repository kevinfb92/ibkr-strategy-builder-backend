import json
from app.services.ibkr_service import IBKRService


def expand_probe(target_date='20250905'):
    svc = IBKRService()
    client = svc.client

    print('=== Fetch raw secdef/search for TXN')
    try:
        search = client.search_contract_by_symbol(symbol='TXN', sec_type='OPT')
        data = getattr(search, 'data', None)
        print('Raw search retrieved')
    except Exception as e:
        print('ERROR fetching secdef/search:', e)
        return

    # extract conids and months tokens
    items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
    conids = []
    months_tokens = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if 'conid' in it:
            conids.append(str(it.get('conid')))
        if 'contracts' in it and isinstance(it.get('contracts'), list):
            for c in it.get('contracts'):
                if isinstance(c, dict) and c.get('conid'):
                    conids.append(str(c.get('conid')))
        if 'months' in it and it.get('months'):
            mt = it.get('months')
            if isinstance(mt, str):
                months_tokens.extend([t for t in mt.split(';') if t])
            elif isinstance(mt, list):
                months_tokens.extend([t for t in mt if t])

    # dedupe
    conids = list(dict.fromkeys(conids))
    months_tokens = list(dict.fromkeys(months_tokens))

    print('Conids found:', conids)
    print('Month tokens found:', months_tokens)

    # prefer SEP25 if present
    months_to_try = []
    if 'SEP25' in months_tokens:
        months_to_try.append('SEP25')
    if '202509' not in months_to_try:
        months_to_try.append('202509')

    # iterate conids
    for cid in conids:
        print('\n--- probing conid', cid)
        for month in months_to_try:
            print(' month:', month)
            # fetch strikes
            try:
                strikes_res = client.search_strikes_by_conid(conid=cid, sec_type='OPT', month=month)
                strikes_data = getattr(strikes_res, 'data', None)
            except Exception as e:
                print('  ERROR fetching strikes for', cid, month, e)
                continue

            strikes_list = []
            if isinstance(strikes_data, dict):
                strikes_list = strikes_data.get('call') or strikes_data.get('strikes') or strikes_data.get('put') or []
            elif isinstance(strikes_data, list):
                strikes_list = strikes_data

            if not strikes_list:
                print('  no strikes for', cid, month)
                continue

            print(f'  probing {len(strikes_list)} strikes (may sample all)')
            # iterate all strikes but cap to avoid runaway (set high default)
            for s in strikes_list:
                cand_strs = []
                cand_strs.append(str(s))
                try:
                    f = float(s)
                    cand_strs.append(f"{f:.1f}")
                    cand_strs.append(f"{f:.2f}")
                    cand_strs.append(str(int(f)))
                except Exception:
                    pass
                # dedupe
                seen = set()
                cand_strs = [c for c in cand_strs if not (c in seen or seen.add(c))]

                for cs in cand_strs:
                    for right in ['C', 'P']:
                        try:
                            res = client.search_secdef_info_by_conid(conid=cid, sec_type='OPT', month=month, strike=cs, right=right)
                            data = getattr(res, 'data', None)
                        except Exception as e:
                            # print minimal error for trace
                            # print('   err', e)
                            continue

                        if not data:
                            continue

                        # look for target_date in various shapes
                        found = False
                        if isinstance(data, dict):
                            # check expirations
                            exps = data.get('expirations') or data.get('expiration') or data.get('maturityDate')
                            if isinstance(exps, list) and target_date in exps:
                                print('\n+++ FOUND', target_date, 'in conid', cid, 'month', month, 'strike', cs, 'right', right)
                                print('response snippet:', json.dumps(data, indent=2, default=str))
                                return
                            if isinstance(exps, str) and exps == target_date:
                                print('\n+++ FOUND', target_date, 'in conid', cid, 'month', month, 'strike', cs, 'right', right)
                                print('response snippet:', json.dumps(data, indent=2, default=str))
                                return
                            # check list of contracts
                            if 'contracts' in data and isinstance(data.get('contracts'), list):
                                for c in data.get('contracts'):
                                    if isinstance(c, dict) and c.get('maturityDate') == target_date:
                                        print('\n+++ FOUND', target_date, 'in conid', cid, 'month', month, 'strike', cs, 'right', right)
                                        print('contract:', json.dumps(c, indent=2, default=str))
                                        return
                        elif isinstance(data, list):
                            for entry in data:
                                if isinstance(entry, dict) and entry.get('maturityDate') == target_date:
                                    print('\n+++ FOUND', target_date, 'in conid', cid, 'month', month, 'strike', cs, 'right', right)
                                    print('entry:', json.dumps(entry, indent=2, default=str))
                                    return
                        # else continue
    print('\nCompleted probe: target date not found in scanned conids/months/strikes')


if __name__ == '__main__':
    expand_probe()
