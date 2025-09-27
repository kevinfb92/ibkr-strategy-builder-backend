#!/usr/bin/env python3
"""
Show exactly how the Discord link formatting looks with Option 2
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.lite_telegram_service import LiteTelegramService

def test_discord_formatting():
    """Test Discord link formatting locally"""
    print("🔧 Testing Discord Link Formatting - Option 2 (Compact)")
    print("=" * 60)
    
    # Initialize service
    bot_token = "8331227211:AAHfYne1uCNrm58FoBHpsU8tD95ETepP_VY"
    service = LiteTelegramService(bot_token)
    
    # Test message with Discord link (like your example)
    original_message = "🌟demspxslayer-and-leaps: 6655P at 2.45 @everyone Size right. Could move fast.\nSee it here: https://discord.com/channels/718624848812834903/1407764518301335562/1419694213884547132"
    
    print("📝 Original Message:")
    print("-" * 40)
    print(original_message)
    print("-" * 40)
    
    # Test Discord link cleaning
    cleaned_message = service.clean_discord_links(original_message)
    
    print("\n🔧 After Discord Link Cleaning (Option 2 - Compact):")
    print("-" * 40)
    print(cleaned_message)
    print("-" * 40)
    
    # Test full message formatting
    processed_data = {
        'ticker': 'SPX',
        'is_alert': True,
        'sentiment': 'bullish',
        'conid': 416904,
        'portal_url': service.generate_ibkr_portal_url(416904),
        'alert_details': {
            'strike': '6655',
            'side': 'P'
        }
    }
    
    formatted_message = service.format_lite_message(
        "demslayer-spx-alerts",
        "OWLS Capital",
        original_message,
        processed_data
    )
    
    print("\n📋 Complete Formatted Telegram Message:")
    print("=" * 60)
    print(formatted_message)
    print("=" * 60)
    
    print("\n✅ Key Improvements:")
    print("   🔗 Discord link is now compact and clickable")
    print("   📏 Message is much shorter and cleaner")  
    print("   🎯 Includes SPX options chain link")
    print("   📱 Better mobile readability")

if __name__ == "__main__":
    test_discord_formatting()
