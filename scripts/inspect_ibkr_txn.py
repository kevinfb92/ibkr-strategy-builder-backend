import sys, traceback, json
sys.path.insert(0, r"c:\Users\kevin\Desktop\trading\stoqey\ibkr-strategy-builder-backend")
from app.services.ibkr_service import IBKRService

def dump(obj):
    try:
        if obj is None:
            return 'None'
        if hasattr(obj, 'data'):
            return repr(obj.data)
        if isinstance(obj, (dict, list, str, int, float)):
            return json.dumps(obj, default=str)
        return repr(obj)
    except Exception as e:
        return f'<error serializing: {e}>'

svc = IBKRService()
print('IBKR base client:', svc.client)

try:
    print('\n--- search_contract_by_symbol OPT for TXN ---')
    opt_search = svc.client.search_contract_by_symbol(symbol='TXN', sec_type='OPT')
    print('raw:', repr(opt_search))
    print('data:', dump(opt_search))

    # Inspect entries if present
    entries = getattr(opt_search, 'data', None) or (opt_search.data if hasattr(opt_search, 'data') else None)
    if entries and isinstance(entries, list):
        for i, item in enumerate(entries[:5]):
            print(f'entry[{i}] type={type(item)} keys={list(item.keys()) if isinstance(item, dict) else None}')
            if isinstance(item, dict):
                for k in ('conid','months','sections','contracts','description'):
                    if k in item:
                        print(f'  {k}: {item.get(k)}')

    print('\n--- search_contract_by_symbol STK for TXN ---')
    stk_search = svc.client.search_contract_by_symbol(symbol='TXN', sec_type='STK')
    print('raw:', repr(stk_search))
    print('data:', dump(stk_search))
    stk_entries = getattr(stk_search, 'data', None)
    conid = None
    if stk_entries and isinstance(stk_entries, list) and len(stk_entries) > 0:
        first = stk_entries[0]
        if isinstance(first, dict):
            conid = first.get('conid') or (first.get('contracts')[0].get('conid') if first.get('contracts') else None)
            print('First STK entry keys:', list(first.keys()))
            print('First STK entry conid:', conid)

    months_tokens = set()
    if entries and isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict):
                m = item.get('months')
                if m and isinstance(m, str):
                    for tok in m.split(';'):
                        months_tokens.add(tok.strip())
                sections = item.get('sections') or []
                if isinstance(sections, list):
                    for sec in sections:
                        if isinstance(sec, dict):
                            m2 = sec.get('months')
                            if m2 and isinstance(m2, str):
                                for tok in m2.split(';'):
                                    months_tokens.add(tok.strip())

    print('\nDiscovered month tokens from OPT search:', months_tokens)

    # For each token, call search_secdef_info_by_conid using a conid
    sample_conid = None
    if entries and isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict):
                if 'conid' in item:
                    sample_conid = item.get('conid')
                    break
                if 'contracts' in item and isinstance(item.get('contracts'), list) and item.get('contracts'):
                    c = item.get('contracts')[0]
                    if isinstance(c, dict) and c.get('conid'):
                        sample_conid = c.get('conid')
                        break

    if sample_conid:
        print('\nUsing sample conid for secdef calls:', sample_conid)
        for tok in sorted(months_tokens):
            try:
                print(f'\n--- search_secdef_info_by_conid conid={sample_conid} month={tok} ---')
                secdef = svc.client.search_secdef_info_by_conid(conid=str(sample_conid), sec_type='OPT', month=tok)
                print('raw:', repr(secdef))
                print('data:', dump(secdef)[:4000])
            except Exception as e:
                print('secdef call error:', e)
                print(traceback.format_exc())

    # Try strikes for an available month if we have company conid from STK
    if conid and months_tokens:
        tok = sorted(months_tokens)[0]
        print(f'\n--- search_strikes_by_conid conid={conid} month={tok} ---')
        try:
            strikes = svc.client.search_strikes_by_conid(conid=str(conid), sec_type='OPT', month=tok)
            print('raw:', repr(strikes))
            print('data:', dump(strikes))
        except Exception as e:
            print('strikes call error:', e)
            print(traceback.format_exc())

except Exception as e:
    print('Unexpected error while inspecting IBKR:', e)
    print(traceback.format_exc())

print('\n--- done ---')
