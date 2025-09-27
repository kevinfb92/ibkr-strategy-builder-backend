import importlib.machinery, importlib.util, json, sys, types

# helper to load a module from path into sys.modules with a given name
def load_mod(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod

# create package placeholders
sys.modules['app'] = types.ModuleType('app')
sys.modules['app.services'] = types.ModuleType('app.services')

# load dependencies
load_mod('app.services.ibkr_service', r'app/services/ibkr_service.py')
load_mod('app.services.contract_storage', r'app/services/contract_storage.py')

# now load handler
mod = load_mod('app.services.handlers.robin_da_hood_handler', r'app/services/handlers/robin_da_hood_handler.py')

h = mod.RobinDaHoodHandler()
res = h.process_notification(title='owls blabla', message='robindahood-alert\n\n ts omg SPY goinnng', subtext='')
print(json.dumps(res, indent=2))
