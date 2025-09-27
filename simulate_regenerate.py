import asyncio
import json
from app.services.telegram_service import TelegramService

class MockBot:
    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        class R: pass
        r = R()
        r.message_id = 11111
        return r

async def main():
    svc = TelegramService(bot_token='fake')
    svc.bot = MockBot()
    processed_data = {
        'contract_details': {
            'symbol': 'SPY',
            'strike': 655.0,
            'right': 'C',
            'expiry': '20250910',
        },
        'spread_info': {
            'bid': 0.1,
            'ask': 0.11,
            'last': 0.1,
            'open_interest': '330K'
        },
        'ibkr_position_size': 0
    }

    result = await svc.send_trading_alert('robindahood-alerts', 'robindahood-alerts SPY 655C', '', '', processed_data)
    mid = result.get('message_id')
    print('Sent message id', mid)
    # Simulate pressing a quantity + button which updates quantity and regenerates message
    msg_info = svc.pending_messages.get(mid)
    print('Pending message stored keys:', list(msg_info.keys()))
    regenerated = svc._regenerate_alert_text_with_action(msg_info, 'OPEN', lightweight=True)
    print('---- REGENERATED HTML ----')
    print(regenerated)

if __name__ == '__main__':
    asyncio.run(main())
