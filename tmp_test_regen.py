import importlib.machinery, importlib.util, sys, types
# load telegram service module
sys.modules['app'] = types.ModuleType('app')
sys.modules['app.services'] = types.ModuleType('app.services')
loader = importlib.machinery.SourceFileLoader('app.services.telegram_service', 'app/services/telegram_service.py')
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = mod
loader.exec_module(mod)
TelegramService = mod.TelegramService
svc = TelegramService(bot_token='dummy')
message_info = {
    'alerter': 'robindahood-alerts',
    'original_message': 'robindahood-alert ts SPY',
    'ticker': 'SPY',
    'quantity': 1,
    'processed_data': {
        'option_contracts': [
            {
                'symbol': 'SPY    SEP2025 658 C [SPY   250915C00658000 100]',
                'ticker': 'SPY',
                'strike': 658.0,
                'side': 'CALL',
                'quantity': 1,
                'unrealizedPnl': -57.32,
                'avgPrice': 1.508607,
                'currentPrice': 0.9354264
            }
        ],
        'ibkr_position_size': 1
    }
}
print(svc._regenerate_alert_text_with_action(message_info, action='close', lightweight=True))
