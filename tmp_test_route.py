import asyncio
from app.services.alerter_manager import alerter_manager

async def run():
    res = await alerter_manager.process_notification('ALERT', 'robindahood-alerts SPY 640C...', '')
    print(res)

if __name__ == '__main__':
    asyncio.run(run())
