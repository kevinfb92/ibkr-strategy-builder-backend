import sys
import traceback
sys.path.insert(0, r"c:\Users\kevin\Desktop\trading\stoqey\ibkr-strategy-builder-backend")

from app.services.ibkr_service import IBKRService


def main():
    conid = '803889028'
    try:
        svc = IBKRService()
    except Exception as e:
        print(f"Failed to init IBKRService: {e}")
        traceback.print_exc()
        return

    # Try multiple secdef/info parameter combinations
    attempts = [
        {'conid': conid},
        {'conid': conid, 'sec_type': 'OPT'},
        {'conid': conid, 'sec_type': 'OPT', 'month': 'SEP25', 'strike': '6500', 'right': 'P'},
    ]

    for params in attempts:
        try:
            print(f"---- Querying secdef.info with params: {params}")
            if 'sec_type' in params:
                res = svc.client.search_secdef_info_by_conid(conid=params['conid'], sec_type=params['sec_type'], month=params.get('month'), strike=params.get('strike'), right=params.get('right'))
            else:
                res = svc.client.search_secdef_info_by_conid(conid=params['conid'])

            print("RES repr:", repr(res))
            data = getattr(res, 'data', res)
            print("DATA TYPE:", type(data))
            print("DATA:")
            try:
                import json
                print(json.dumps(data, default=str, indent=2))
            except Exception:
                print(data)
        except Exception as e:
            print(f"secdef.info query failed for {params}: {e}")
            traceback.print_exc()


if __name__ == '__main__':
    main()
