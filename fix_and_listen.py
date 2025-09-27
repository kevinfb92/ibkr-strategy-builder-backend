#!/usr/bin/env python3
"""
Manually add the test message to pending messages and start bot listener
"""

import asyncio
import sys
import os
from datetime import datetime

# Add the app directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

import app.main as main_app

async def add_test_message_and_listen():
    """Add the test message and start listening"""
    
    print("================================================================================")
    print("🔧 FIXING PENDING MESSAGE AND STARTING BOT")
    print("================================================================================")
    
    # Get the global telegram service
    telegram_service = main_app.telegram_service
    
    if not telegram_service:
        print("❌ Telegram service not available")
        return
    
    # Add the missing message manually
    message_id = "46a6f94c"
    test_contract = {
        'strike': 5900,
        'side': 'PUT', 
        'expiry': '20250829'
    }
    
    test_spread = {
        'bid': 0.50,
        'ask': 0.75,
        'last': 0.60,
        'open_interest': '45.2K'
    }
    
    # Store the message data exactly as it should be
    telegram_service.pending_messages[message_id] = {
        "alerter": "demslayer-spx-alerts",
        "original_message": f"FINAL TEST: SPX {test_contract['strike']}{test_contract['side']} {test_contract['expiry'][-2:]} - Ready for automated order placement",
        "ticker": "",
        "additional_info": "",
        "processed_data": {
            'contract_details': test_contract,
            'spread_info': test_spread
        },
        "timestamp": datetime.now().isoformat(),
        "response": None
    }
    
    print(f"✅ Added message {message_id} to pending messages")
    print(f"📋 Contract: SPX {test_contract['strike']}{test_contract['side']} {test_contract['expiry']}")
    print(f"💰 Limit price: ${(test_spread['bid'] + test_spread['ask']) / 2}")
    print()
    
    print(f"📋 Current pending messages: {len(telegram_service.pending_messages)}")
    for msg_id, msg_data in telegram_service.pending_messages.items():
        alerter = msg_data.get('alerter', 'Unknown')
        timestamp = msg_data.get('timestamp', 'Unknown')
        print(f"   - {msg_id}: {alerter} ({timestamp})")
    
    print(f"\n🤖 Starting bot to listen for button presses...")
    print(f"📱 Press the BUY or SELL button in Telegram message #140")
    print(f"🚀 The system will now complete the full automation!")
    print(f"⏹️  Press Ctrl+C to stop the bot")
    print()
    
    try:
        await telegram_service.start_bot()
    except KeyboardInterrupt:
        print(f"\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Error running bot: {e}")

if __name__ == "__main__":
    asyncio.run(add_test_message_and_listen())
