import sys
import json

sys.path.insert(0, r"c:\Users\kevin\Desktop\trading\stoqey\ibkr-strategy-builder-backend")

from app.services.ibkr_service import IBKRService


def dump(conid):
    svc = IBKRService()
    print(f"Querying secdef/info for conid={conid}")
    try:
        res = svc.client.search_secdef_info_by_conid(conid=str(conid))
        print("repr(res):", repr(res))
        try:
            data = res.data
        except Exception:
            data = None
        print("data type:", type(data))
        print(json.dumps(data, default=str, indent=2))
    except Exception as e:
        print(f"secdef/info call failed: {e}")


if __name__ == '__main__':
    # Real conids from logs
    for c in ('803889028', '803296959'):
        dump(c)
