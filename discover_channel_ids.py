#!/usr/bin/env python3
"""
Script to help discover the correct channel IDs by monitoring bot updates
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def discover_channel_ids():
    """Monitor bot updates to discover channel IDs"""
    print("🔍 Channel ID Discovery Tool")
    print("=" * 50)
    print("This tool will help you find the correct channel IDs.")
    print("\nInstructions:")
    print("1. After running this script, go to each of your channels")
    print("2. Send a message like 'test' in each channel")
    print("3. The script will show you the correct channel IDs")
    print("4. Press Ctrl+C to stop when done")
    print("\n" + "=" * 50)
    
    try:
        from telegram import Bot
        
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            print("❌ TELEGRAM_BOT_TOKEN not found in .env")
            return
            
        bot = Bot(token=bot_token)
        
        # Get bot info
        bot_info = await bot.get_me()
        print(f"🤖 Monitoring updates for bot: @{bot_info.username}")
        print(f"   Bot ID: {bot_info.id}")
        
        print("\n⏳ Waiting for channel messages...")
        print("   → Go to your 'Buy Alerts' channel and send: test buy")
        print("   → Go to your 'Updates' channel and send: test update")
        print("   → Press Ctrl+C when done\n")
        
        last_update_id = None
        
        while True:
            try:
                # Get updates
                updates = await bot.get_updates(offset=last_update_id, timeout=1)
                
                for update in updates:
                    last_update_id = update.update_id + 1
                    
                    # Check if it's a channel post
                    if update.channel_post:
                        message = update.channel_post
                        chat = message.chat
                        
                        print(f"📢 Channel Message Detected:")
                        print(f"   Channel ID: {chat.id}")
                        print(f"   Channel Title: {chat.title}")
                        print(f"   Channel Type: {chat.type}")
                        print(f"   Message: {message.text}")
                        print(f"   Date: {message.date}")
                        print()
                        
                        # Suggest which channel this might be based on message content
                        if message.text and 'buy' in message.text.lower():
                            print(f"   🚨 This looks like your BUY ALERTS channel!")
                            print(f"   → Set TELEGRAM_BUY_ALERTS_CHAT_ID={chat.id}")
                        elif message.text and 'update' in message.text.lower():
                            print(f"   📈 This looks like your UPDATES channel!")
                            print(f"   → Set TELEGRAM_UPDATES_CHAT_ID={chat.id}")
                        
                        print("-" * 50)
                    
                    # Also check regular messages (in case it's a group)
                    elif update.message:
                        message = update.message
                        chat = message.chat
                        
                        if chat.type in ['channel', 'supergroup']:
                            print(f"💬 Group/Channel Message:")
                            print(f"   Chat ID: {chat.id}")
                            print(f"   Chat Title: {chat.title}")
                            print(f"   Chat Type: {chat.type}")
                            print(f"   Message: {message.text}")
                            print(f"   From: {message.from_user.first_name if message.from_user else 'Unknown'}")
                            print("-" * 50)
                
                await asyncio.sleep(1)
                
            except KeyboardInterrupt:
                print("\n✅ Monitoring stopped by user")
                break
            except Exception as e:
                print(f"⚠️  Error getting updates: {e}")
                await asyncio.sleep(2)
                
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(discover_channel_ids())
    except KeyboardInterrupt:
        print("\n👋 Exiting...")