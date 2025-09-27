import json
from app.services.ibkr_service import IBKRService


def probe():
    svc = IBKRService()
    client = svc.client
    conid = '13096'
    month_tokens = ['SEP25', '202509']

    print('=== Fetch strikes (SEP25) ===')
    try:
        strikes_res = client.search_strikes_by_conid(conid=conid, sec_type='OPT', month='SEP25')
        strikes_data = getattr(strikes_res, 'data', None)
        print(json.dumps({'raw_strikes': strikes_data}, indent=2, default=str))
    except Exception as e:
        print('ERROR fetching strikes:', e)
        return

    strikes_list = []
    if isinstance(strikes_data, dict):
        strikes_list = strikes_data.get('call') or strikes_data.get('strikes') or strikes_data.get('put') or []
    elif isinstance(strikes_data, list):
        strikes_list = strikes_data

    # build candidate strike strings from first few strikes
    candidates = []
    for s in strikes_list[:6]:
        # preserve formatting as in API
        candidates.append(str(s))
        # add variations
        candidates.append(f"{s:.1f}")
        candidates.append(f"{s:.2f}")
        # integer form
        try:
            candidates.append(str(int(s)))
        except Exception:
            pass

    # dedupe
    seen = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]
    print('\nCandidate strikes to try:', candidates)

    for m in month_tokens:
        for cand in candidates:
            for right in ['C', 'P']:
                params = {'conid': conid, 'sectype': 'OPT', 'month': m, 'strike': cand, 'right': right}
                print('\n--> Trying', params)
                try:
                    r = client.search_secdef_info_by_conid(**params)
                    data = getattr(r, 'data', None)
                    print('RESPONSE:', json.dumps({'params': params, 'data': data}, indent=2, default=str))
                except Exception as e:
                    print('ERROR for params', params, e)


if __name__ == '__main__':
    probe()
