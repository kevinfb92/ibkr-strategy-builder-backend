import asyncio
from app.services.notification_service import NotificationService

ns = NotificationService()
message = "Doing a rare reversal trade, taking the loss on $TXN long (-$8.40) and shorting it at $199.06"
asyncio.run(ns.process_notification("Real day trading", message, ""))
print('Runner finished')
