import importlib.machinery, importlib.util, json
path = r"app/services/contract_storage.py"
loader = importlib.machinery.SourceFileLoader('contract_storage_test', path)
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
cs = mod.contract_storage
res = cs.get_contract('robindahood-alerts')
print('FOUND:' if res else 'NOT FOUND')
if res:
    print(json.dumps(res, indent=2))
