#!/usr/bin/env python3
"""
Test script to verify bot permissions and channel access
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def verify_bot_access():
    """Verify bot can access the channels"""
    print("🔍 Verifying Bot Channel Access")
    print("=" * 40)
    
    try:
        from telegram import Bot
        
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        buy_alerts_chat_id = os.getenv("TELEGRAM_BUY_ALERTS_CHAT_ID")
        updates_chat_id = os.getenv("TELEGRAM_UPDATES_CHAT_ID")
        
        print(f"Bot Token: {bot_token[:10]}...")
        print(f"Buy Alerts Chat ID: {buy_alerts_chat_id}")
        print(f"Updates Chat ID: {updates_chat_id}")
        
        bot = Bot(token=bot_token)
        
        # Test buy alerts channel
        print(f"\n🚨 Testing Buy Alerts Channel ({buy_alerts_chat_id})...")
        try:
            chat_info = await bot.get_chat(chat_id=int(buy_alerts_chat_id))
            print(f"✅ Channel found: {chat_info.title}")
            print(f"   Type: {chat_info.type}")
            
            # Try to get chat member info (bot permissions)
            try:
                member = await bot.get_chat_member(chat_id=int(buy_alerts_chat_id), user_id=bot.id)
                print(f"   Bot status: {member.status}")
                if hasattr(member, 'can_post_messages'):
                    print(f"   Can post messages: {member.can_post_messages}")
            except Exception as e:
                print(f"   Permission check failed: {e}")
                
        except Exception as e:
            print(f"❌ Buy alerts channel error: {e}")
        
        # Test updates channel
        print(f"\n📈 Testing Updates Channel ({updates_chat_id})...")
        try:
            chat_info = await bot.get_chat(chat_id=int(updates_chat_id))
            print(f"✅ Channel found: {chat_info.title}")
            print(f"   Type: {chat_info.type}")
            
            # Try to get chat member info (bot permissions)
            try:
                member = await bot.get_chat_member(chat_id=int(updates_chat_id), user_id=bot.id)
                print(f"   Bot status: {member.status}")
                if hasattr(member, 'can_post_messages'):
                    print(f"   Can post messages: {member.can_post_messages}")
            except Exception as e:
                print(f"   Permission check failed: {e}")
                
        except Exception as e:
            print(f"❌ Updates channel error: {e}")
            
        # Get bot info
        print(f"\n🤖 Bot Information...")
        try:
            bot_info = await bot.get_me()
            print(f"Bot Username: @{bot_info.username}")
            print(f"Bot ID: {bot_info.id}")
            print(f"Bot Name: {bot_info.first_name}")
        except Exception as e:
            print(f"❌ Bot info error: {e}")
            
    except Exception as e:
        print(f"❌ General error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_bot_access())