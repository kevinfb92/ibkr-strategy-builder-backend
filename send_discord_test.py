#!/usr/bin/env python3
"""
Send a test demslayer message with Discord link to see Option 2 formatting
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.alerter_manager import alerter_manager

async def send_test_discord_message():
    """Send a test demslayer message with Discord link to see the formatting"""
    print("📤 Sending test demslayer message with Discord link...")
    print("=" * 60)
    
    # Simulate the exact demslayer message from your example
    title = "OWLS Capital"
    message = "demslayer-spx-alerts: 🌟demspxslayer-and-leaps: 6655P at 2.45 @everyone Size right. Could move fast.\nSee it here: https://discord.com/channels/718624848812834903/1407764518301335562/1419694213884547132"
    subtext = "SPX"
    
    print(f"📋 Test Message Details:")
    print(f"   Title: {title}")
    print(f"   Message: {message[:50]}...")
    print(f"   Discord Link: Included")
    print(f"   Expected Format: Compact [🔗 Discord](url)")
    
    try:
        # Send through the alerter manager (this will trigger the demslayer handler)
        result = await alerter_manager.process_notification(title, message, subtext)
        
        print(f"\n✅ Message sent successfully!")
        print(f"   Result: {result.get('success', False)}")
        print(f"   Handler: {result.get('handler_used', 'unknown')}")
        print(f"   Telegram: {result.get('telegram_sent', {}).get('success', False)}")
        
        print(f"\n📱 Check your Telegram bot for the message!")
        print(f"   - Should show 'DEMSLAYER-SPX-ALERTS ALERT'")
        print(f"   - Discord link should be compact: [🔗 Discord](url)")
        print(f"   - Should include SPX options chain link")
        
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(send_test_discord_message())
