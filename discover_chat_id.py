"""
Simple script to discover your Telegram chat ID
Run this script and then send /start to your bot
"""
import asyncio
import logging
from app.services.telegram_chat_discovery import chat_discovery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    """Run the chat discovery bot"""
    print("=" * 60)
    print("🤖 TELEGRAM CHAT ID DISCOVERY")
    print("=" * 60)
    print("1. Make sure your bot is created (@BotFather)")
    print("2. Start this script")
    print("3. Go to your bot and send /start")
    print("4. Your chat ID will be displayed and saved")
    print("=" * 60)
    print()
    print("Starting discovery bot... Press Ctrl+C to stop")
    print()
    
    try:
        await chat_discovery.run_discovery()
    except KeyboardInterrupt:
        print("\n👋 Discovery bot stopped")
        print("\nDiscovered chats:")
        for username, info in chat_discovery.get_all_discovered_chats().items():
            print(f"  👤 {username}: Chat ID = {info['chat_id']}")

if __name__ == "__main__":
    asyncio.run(main())
