import json
from app.services.ibkr_service import IBKRService


def run_probe():
    svc = IBKRService()
    client = svc.client
    conid = '13096'
    months = ['SEP25', '202509']

    print('Fetching strikes for conid', conid, 'month SEP25')
    try:
        strikes_res = client.search_strikes_by_conid(conid=conid, sec_type='OPT', month='SEP25')
        strikes = getattr(strikes_res, 'data', None)
    except Exception as e:
        print('ERROR fetching strikes:', e)
        return

    # normalize strikes list
    strikes_list = []
    if isinstance(strikes, dict):
        strikes_list = strikes.get('call') or strikes.get('strikes') or strikes.get('put') or []
    elif isinstance(strikes, list):
        strikes_list = strikes

    if not strikes_list:
        print('No strikes list available')
        return

    # take first up to 8 strikes
    sample = strikes_list[:8]
    # build candidate strings
    candidates = []
    for s in sample:
        # use the exact representation from the API
        candidates.append(str(s))
        # common variations
        try:
            f = float(s)
            candidates.append(f"{f:.1f}")
            candidates.append(f"{f:.2f}")
            candidates.append(str(int(f)))
        except Exception:
            pass

    # dedupe while preserving order
    seen = set()
    cand_list = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        cand_list.append(c)

    print('Will probe candidate strikes:', cand_list)

    found_any = False
    for month in months:
        for strike in cand_list:
            for right in ['C', 'P']:
                print(f"\nTrying conid={conid} month={month} strike='{strike}' right={right}")
                try:
                    res = client.search_secdef_info_by_conid(conid=conid, sec_type='OPT', month=month, strike=strike, right=right)
                    data = getattr(res, 'data', None)
                    if data:
                        # print brief summary
                        print('Got data:', json.dumps(data, indent=2, default=str))
                        # check for expirations / maturityDate / contracts
                        matched = False
                        if isinstance(data, dict):
                            if 'expirations' in data and data.get('expirations'):
                                print('Found expirations field:', data.get('expirations'))
                                matched = True
                            if 'maturityDate' in data and data.get('maturityDate'):
                                print('Found maturityDate:', data.get('maturityDate'))
                                matched = True
                            # some servers return a list of contracts
                            if 'contracts' in data and data.get('contracts'):
                                print('Found contracts list with length', len(data.get('contracts')))
                                matched = True
                        elif isinstance(data, list) and data:
                            print('Received list response length', len(data))
                            matched = True

                        if matched:
                            found_any = True
                            print('\n=== MATCH - stopping early ===')
                            return
                        else:
                            print('No expirations/maturities/contracts in response')
                    else:
                        print('Empty data in response')
                except Exception as e:
                    print('ERROR calling secdef/info:', e)

    if not found_any:
        print('\nNo expirations found for sampled strikes/months/rights under conid', conid)


if __name__ == '__main__':
    run_probe()
