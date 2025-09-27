import asyncio, json
from app.services.telegram_service import TelegramService

# Build a message_info that resembles what Telegram callback provides
message_info = {
    'alerter': 'RobinDaHood',
    'processed_data': {
        'contract_details': {
            'conid': 807283860,
            'symbol': 'SPY'
        },
        'ticker': 'SPY',
        'option_contracts': [
            {'conid': 807283860, 'quantity': 1, 'position': 1, 'currentPrice': 0.01}
        ]
    },
    'quantity': 1,
}

async def run():
    svc = TelegramService()
    res = await svc._process_place_trail(message_info)
    print('Result:', json.dumps(res))

if __name__ == '__main__':
    asyncio.run(run())
