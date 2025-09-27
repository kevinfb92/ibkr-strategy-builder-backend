#!/usr/bin/env python3
"""
Send a direct test message to Telegram bot to show Discord link formatting
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.lite_telegram_service import LiteTelegramService

async def send_direct_telegram_test():
    """Send a direct message to Telegram to test Discord link formatting"""
    print("📤 Sending direct test message to Telegram bot...")
    print("=" * 50)
    
    # Initialize Telegram service
    bot_token = "8331227211:AAHfYne1uCNrm58FoBHpsU8tD95ETepP_VY"
    service = LiteTelegramService(bot_token)
    
    # Test message with Discord link (like your example)
    original_message = "🌟demspxslayer-and-leaps: 6655P at 2.45 @everyone Size right. Could move fast.\nSee it here: https://discord.com/channels/718624848812834903/1407764518301335562/1419694213884547132"
    
    # Processed data for demslayer alert
    processed_data = {
        'ticker': 'SPX',
        'is_alert': True,
        'is_bullish': True,
        'sentiment': 'bullish',
        'conid': 416904,  # Static SPX conid
        'alert_details': {
            'strike': '6655',
            'side': 'P',
            'price': '2.45'
        },
        'alerter': 'demslayer-spx-alerts',
        'lite_mode': True
    }
    
    print(f"📋 Sending test message:")
    print(f"   Alert Type: demslayer-spx-alerts")
    print(f"   Discord Link: Will be compacted")
    print(f"   SPX Options: Will include chain link")
    
    try:
        # Send the message directly through Telegram service
        result = await service.send_trading_alert(
            alerter_name="demslayer-spx-alerts",
            title="📧 TEST: Discord Link Formatting",
            message=original_message,
            processed_data=processed_data
        )
        
        print(f"\n✅ Message sent to Telegram!")
        print(f"   Success: {result.get('success', False)}")
        print(f"   Message ID: {result.get('message_id', 'N/A')}")
        
        if result.get('success'):
            print(f"\n📱 Check your Telegram bot now!")
            print(f"   - Should show 'DEMSLAYER-SPX-ALERTS ALERT'")
            print(f"   - Discord link should be: [🔗 Discord](url)")
            print(f"   - Should include SPX options chain link")
            print(f"   - Much cleaner than before!")
        else:
            print(f"\n❌ Message failed to send:")
            print(f"   Error: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(send_direct_telegram_test())
