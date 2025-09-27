import json
from app.services.ibkr_service import IBKRService


def probe():
    svc = IBKRService()
    client = svc.client
    conid = '13096'
    month = 'SEP25'

    print('=== Calling secdef/info for conid', conid, 'month', month)
    try:
        info = client.search_secdef_info_by_conid(conid=conid, sec_type='OPT', month=month)
        print(json.dumps({'raw_info': getattr(info, 'data', None)}, indent=2, default=str))
    except Exception as e:
        print('ERROR secdef/info unstruck with month:', e)

    print('\n=== Calling secdef/strikes for conid', conid, 'month', month)
    try:
        strikes_res = client.search_strikes_by_conid(conid=conid, sec_type='OPT', month=month)
        strikes_data = getattr(strikes_res, 'data', None)
        print(json.dumps({'raw_strikes': strikes_data}, indent=2, default=str))
    except Exception as e:
        print('ERROR secdef/strikes:', e)
        strikes_data = None

    # try to get ATM and probe by strike
    try:
        price = svc.get_current_stock_price('TXN')
        print('\nCurrent price:', price)
    except Exception:
        price = None

    strikes_list = []
    if isinstance(strikes_data, dict):
        # some mock responses put strikes under 'strikes'
        strikes_list = strikes_data.get('strikes') or strikes_data.get('call') or strikes_data.get('put') or []
    elif isinstance(strikes_data, list):
        strikes_list = strikes_data

    if strikes_list:
        # convert to numbers and find closest to price
        try:
            strikes_f = [float(s) for s in strikes_list]
        except Exception:
            strikes_f = []
        if strikes_f:
            if price is None:
                atm = strikes_f[len(strikes_f)//2]
            else:
                atm = min(strikes_f, key=lambda x: abs(x - price))
            print('Selected ATM strike:', atm)

            for right in ['C', 'P']:
                print(f"\n--- Calling secdef/info with strike={atm} right={right}")
                try:
                    info2 = client.search_secdef_info_by_conid(conid=conid, sec_type='OPT', month=month, strike=str(int(atm)), right=right)
                    print(json.dumps({'right': right, 'raw_info': getattr(info2, 'data', None)}, indent=2, default=str))
                except Exception as e:
                    print('ERROR secdef/info struck:', e)
        else:
            print('No numeric strikes parsed.')
    else:
        print('No strikes list available to probe.')


if __name__ == '__main__':
    probe()
