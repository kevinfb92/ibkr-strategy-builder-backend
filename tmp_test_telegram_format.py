from app.services.telegram_service import TelegramService

if __name__ == '__main__':
    svc = TelegramService(bot_token='fake')
    processed_data = {
        'ibkr_contract_result': {
            'contract_details': {
                'symbol': 'TSLA',
                'strike': 345.0,
                'right': 'C',
                'expiry': '20250912',
                'conid': 803403154,
                'full_name': "SEP 12 '25 345 Call"
            },
            'market_data': {
                'bid': 6.6, 'ask': 6.7, 'last': 6.65, 'open_interest': '11.2K'
            }
        }
    }
    formatted, info = svc._format_contract_display('TSLA', '', 'Real Day Trading', processed_data)
    print('formatted:', formatted)
    print('info:', info)
