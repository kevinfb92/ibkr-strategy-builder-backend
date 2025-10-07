#!/usr/bin/env python3
"""
Script to update telegram service calls to use dual-channel system
"""
import re

def update_lite_handlers():
    """Update lite_handlers.py to use dual-channel telegram system"""
    
    file_path = "app/services/handlers/lite_handlers.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern 1: Update _send_buy_telegram methods to use send_buy_alert
    # Find pattern: result = await telegram_service.send_lite_alert(telegram_message)
    # In _send_buy_telegram methods
    buy_pattern = r'(async def _send_buy_telegram.*?)(result = await telegram_service\.send_lite_alert\(telegram_message\))'
    
    def replace_buy_alert(match):
        method_part = match.group(1)
        return method_part + "result = await telegram_service.send_buy_alert(telegram_message)"
    
    content = re.sub(buy_pattern, replace_buy_alert, content, flags=re.DOTALL)
    
    # Pattern 2: Update _send_update_telegram methods to use send_update_message
    update_pattern = r'(async def _send_update_telegram.*?)(result = await telegram_service\.send_lite_alert\(telegram_message\))'
    
    def replace_update_alert(match):
        method_part = match.group(1)
        return method_part + "result = await telegram_service.send_update_message(telegram_message)"
    
    content = re.sub(update_pattern, replace_update_alert, content, flags=re.DOTALL)
    
    # Write back the updated content
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Updated lite_handlers.py to use dual-channel telegram system")
    print("   - _send_buy_telegram methods now use send_buy_alert()")
    print("   - _send_update_telegram methods now use send_update_message()")

if __name__ == "__main__":
    update_lite_handlers()