import asyncio
import json
from app.services.telegram_service import TelegramService

class DummySent:
    def __init__(self):
        self.message_id = 99999

class MockBot:
    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        # Print the message to stdout so we can inspect it in the terminal run
        print("---- TELEGRAM MESSAGE (begin) ----")
        print(text)
        print("---- TELEGRAM MESSAGE (end) ----")
        class R: pass
        r = R()
        r.message_id = 99999
        return r

async def main():
    svc = TelegramService(bot_token='fake-token')
    # Inject a mock bot to avoid requiring python-telegram-bot
    svc.bot = MockBot()

    processed_data = {
        'contract_details': {
            'symbol': 'SPY',
            'strike': 655.0,
            'right': 'C',
            'expiry': '20250910',
            'conid': 810117576,
            'exchange': 'SMART',
            'currency': 'USD',
            'full_name': "SEP 10 '25 655 Call"
        },
        'spread_info': {
            'bid': 0.1,
            'ask': 0.11,
            'last': 0.1,
            'volume': '6,463',
            'high': 0.61,
            'low': 0.07,
            'change': 0.01,
            'change_pct': 11.11,
            'open_interest': '330K',
            'data_source': 'live_snapshot',
        },
        'ibkr_position_size': 0
    }

    result = await svc.send_trading_alert(
        alerter_name='robindahood-alerts',
        message='robindahood-alerts SPY 655C',
        ticker='',
        additional_info='',
        processed_data=processed_data
    )
    print('Result:', json.dumps(result, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
