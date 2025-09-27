from app.services.handlers.demslayer_spx_alerts_handler import DemslayerSpxAlertsHandler
from app.services.telegram_service import TelegramService

# Create handler and processed data
h = DemslayerSpxAlertsHandler()
res = h.process_notification('owls blabla','demslayer-spx-alerts 6500P','')
processed = res['data']

# Instantiate TelegramService but stub bot.send_message to capture HTML
svc = TelegramService(bot_token='fake')
class DummyMsg:
    def __init__(self):
        self.message_id = 12345

class DummyBot:
    def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        print('--- Rendered HTML ---')
        print(text)
        return DummyMsg()

svc.bot = DummyBot()

import asyncio
async def run():
    out = await svc.send_trading_alert('demslayer-spx-alerts', processed['original_message'], ticker=processed.get('ticker'), additional_info='', processed_data=processed)
    print('\n--- send_trading_alert result ---')
    print(out)

asyncio.get_event_loop().run_until_complete(run())
