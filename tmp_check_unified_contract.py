from app.services.handlers.demslayer_spx_alerts_handler import DemslayerSpxAlertsHandler
from app.services.telegram_service import TelegramService

h = DemslayerSpxAlertsHandler()
res = h.process_notification('owls blabla','demslayer-spx-alerts 6500P','')
proc = res['data']

svc = TelegramService(bot_token='fake')
formatted, enhanced = svc._format_contract_display(proc.get('ticker'), '', 'demslayer-spx-alerts', proc)
print('Formatted ticker:', formatted)
print('Enhanced info:', enhanced)
