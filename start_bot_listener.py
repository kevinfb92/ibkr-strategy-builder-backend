#!/usr/bin/env python3
"""
Start the bot listener to handle button presses
"""

import asyncio
import sys
import os

# Add the app directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

import app.main as main_app

async def start_button_listener():
    """Start the bot to listen for button presses"""
    
    print("================================================================================")
    print("🤖 STARTING TELEGRAM BOT LISTENER")
    print("================================================================================")
    
    # Get the global telegram service
    telegram_service = main_app.telegram_service
    
    if not telegram_service:
        print("❌ Telegram service not available")
        return
    
    print(f"📋 Current pending messages: {len(telegram_service.pending_messages)}")
    for msg_id, msg_data in telegram_service.pending_messages.items():
        alerter = msg_data.get('alerter', 'Unknown')
        timestamp = msg_data.get('timestamp', 'Unknown')
        print(f"   - {msg_id}: {alerter} ({timestamp})")
    
    print(f"\n🤖 Starting bot to listen for button presses...")
    print(f"📱 The bot is now ready to detect button presses")
    print(f"⏹️  Press Ctrl+C to stop the bot")
    print()
    
    try:
        await telegram_service.start_bot()
    except KeyboardInterrupt:
        print(f"\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error running bot: {e}")

if __name__ == "__main__":
    asyncio.run(start_button_listener())
