import sys
import datetime
from types import SimpleNamespace

sys.path.insert(0, r"c:\Users\kevin\Desktop\trading\stoqey\ibkr-strategy-builder-backend")

from app.services.ibkr_service import IBKRService


def parse_date_like(s):
    # handle YYYYMMDD or YYYY-MM-DD
    try:
        if '-' in s:
            return datetime.datetime.fromisoformat(s).date()
        if len(s) == 8:
            return datetime.date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    except Exception:
        return None
    return None


def find_underlying_conid(svc, symbol):
    # Use the service wrapper which normalizes client kw names
    try:
        res = svc.search_contract_by_symbol(symbol=symbol)
        if res and hasattr(res, 'data') and res.data:
            rows = res.data if isinstance(res.data, list) else [res.data]
            for r in rows:
                if isinstance(r, dict) and r.get('conid'):
                    return r.get('conid')
    except Exception:
        pass
    return None


def main():
    svc = IBKRService()

    symbol = 'SPX'
    print(f"Looking up underlying conid for {symbol}...")
    underlying = find_underlying_conid(svc, symbol)
    print(f"Underlying conid: {underlying}")

    # Fetch option search results
    print("Fetching option search results (best-effort)...")
    try:
        opt_search = svc.search_contract_by_symbol(symbol=symbol, sec_type='OPT')
    except Exception as e:
        print(f"Option search failed: {e}")
        opt_search = None

    candidates = []
    if opt_search and hasattr(opt_search, 'data') and opt_search.data:
        rows = opt_search.data if isinstance(opt_search.data, list) else [opt_search.data]
        for r in rows:
            if not isinstance(r, dict):
                continue
            # Expect keys like 'expiry', 'strike', 'right', 'conid'
            if 'expiry' in r and 'strike' in r and 'conid' in r:
                exp_date = parse_date_like(r.get('expiry'))
                if not exp_date:
                    continue
                if exp_date < datetime.date.today():
                    continue
                candidates.append({
                    'conid': r.get('conid'),
                    'expiry': exp_date,
                    'strike': float(r.get('strike') or 0),
                    'right': r.get('right')
                })

    if not candidates:
        print("No option candidates found via search_contract_by_symbol; trying contract details via secdef/info for a known conid if available.")

    # Group by expiry and pick the nearest expiry
    if candidates:
        candidates.sort(key=lambda x: (x['expiry'], abs(x['strike'])))
        nearest_exp = min(candidates, key=lambda x: x['expiry'])['expiry']
        # Filter to nearest expiry
        nearest = [c for c in candidates if c['expiry'] == nearest_exp]

        # Determine underlying price for ITM decision
        underlying_price = None
        try:
            if underlying:
                md = svc.client.live_marketdata_snapshot(conids=[str(underlying)], fields=['31'])
                if md and hasattr(md, 'data') and md.data and isinstance(md.data, list):
                    ud = md.data[0]
                    if '31' in ud:
                        underlying_price = float(ud['31'])
        except Exception:
            underlying_price = None

        print(f"Nearest expiry: {nearest_exp} underlying_price={underlying_price}")

        # Prefer ITM options: for PUT, ITM if strike > underlying_price; for CALL ITM if strike < underlying_price
        def is_itm(c):
            if underlying_price is None:
                return False
            if not c['right']:
                return False
            r = c['right'].upper()
            if r.startswith('P'):
                return c['strike'] > underlying_price
            if r.startswith('C'):
                return c['strike'] < underlying_price
            return False

        itm = [c for c in nearest if is_itm(c)]
        chosen = None
        if itm:
            # pick the one with smallest distance to ITM boundary
            itm.sort(key=lambda x: abs(x['strike'] - underlying_price))
            chosen = itm[0]
        else:
            # fallback: pick the closest strike to midpoint of bid/ask or underlying
            nearest.sort(key=lambda x: abs(x['strike'] - (underlying_price or 0)))
            chosen = nearest[0]

        print(f"Chosen option candidate: {chosen}")
        conid = chosen['conid']
    else:
        print("No candidates discovered. Exiting.")
        return

    # Dump secdef/info for chosen conid
    print(f"Querying secdef/info for conid {conid}...")
    try:
        sec = svc.client.search_secdef_info_by_conid(conid=str(conid))
        print("secdef result:", getattr(sec, 'data', sec))
    except Exception as e:
        print(f"secdef/info call failed: {e}")

    # Discover mintick and aligned price
    min_tick = svc._get_min_tick_for_conid(str(conid))
    print(f"Discovered min_tick={min_tick}")

    target_price = 4.525
    aligned = svc.get_aligned_price(str(conid), target_price, side='BUY')
    print(f"target={target_price} aligned(BUY)={aligned}")


if __name__ == '__main__':
    main()
