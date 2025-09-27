import importlib.machinery, importlib.util, sys, types
# Load telegram_service module with package stub
sys.modules['app'] = types.ModuleType('app')
sys.modules['app.services'] = types.ModuleType('app.services')
loader = importlib.machinery.SourceFileLoader('app.services.telegram_service', 'app/services/telegram_service.py')
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = mod
loader.exec_module(mod)
TelegramService = mod.TelegramService
svc = TelegramService(bot_token='dummy')
# sample option contract row (as produced by handlers)
row = {
    'symbol': 'SPY    SEP2025 658 C [SPY   250915C00658000 100]',
    'ticker': 'SPY',
    'strike': 658.0,
    'side': 'CALL',
    'quantity': 1
}
fmt, extra = svc._format_contract_display(row.get('symbol'), additional_info='', alerter_name='robindahood-alerts', processed_data={'contract_details': None})
print('FORMATTED:', fmt)
