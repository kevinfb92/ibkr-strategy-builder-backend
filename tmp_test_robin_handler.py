import importlib.machinery, importlib.util, json, sys, types
path = r"app/services/handlers/robin_da_hood_handler.py"

# Create minimal package placeholders so relative imports succeed
pkg_app = types.ModuleType('app')
pkg_services = types.ModuleType('app.services')
pkg_handlers = types.ModuleType('app.services.handlers')
sys.modules['app'] = pkg_app
sys.modules['app.services'] = pkg_services
sys.modules['app.services.handlers'] = pkg_handlers

loader = importlib.machinery.SourceFileLoader('app.services.handlers.robin_da_hood_handler', path)
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = mod
loader.exec_module(mod)

handler_cls = mod.RobinDaHoodHandler
h = handler_cls()
res = h.process_notification(title='owls blabla', message='robindahood-alert\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n ts omg SPY goinnng', subtext='')
print(json.dumps(res, indent=2))
