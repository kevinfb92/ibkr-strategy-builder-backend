#!/usr/bin/env python3

"""
Fix script to update all lite handlers to use compact formatting
"""

import os
import re

def fix_handlers():
    """Update all lite handlers to use send_lite_alert instead of send_trading_alert"""
    
    handlers_file = "app/services/handlers/lite_handlers.py"
    
    if not os.path.exists(handlers_file):
        print(f"❌ File not found: {handlers_file}")
        return False
    
    # Read the current file
    with open(handlers_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Analyzing lite_handlers.py...")
    print("=" * 50)
    
    # Find all send_trading_alert calls and their line numbers
    lines = content.split('\n')
    alert_calls = []
    
    for i, line in enumerate(lines, 1):
        if 'await telegram_service.send_trading_alert(' in line:
            alert_calls.append((i, line.strip()))
    
    print(f"Found {len(alert_calls)} send_trading_alert calls:")
    for line_num, line_content in alert_calls:
        print(f"  Line {line_num}: {line_content}")
    
    print("\nReplacing with send_lite_alert...")
    
    # Replace all occurrences
    original_content = content
    updated_content = content.replace(
        'await telegram_service.send_trading_alert(',
        'await telegram_service.send_lite_alert('
    )
    
    if updated_content == original_content:
        print("❌ No changes made - no send_trading_alert calls found")
        return False
    
    # Count changes
    original_count = original_content.count('send_trading_alert(')
    updated_count = updated_content.count('send_trading_alert(')
    changes_made = original_count - updated_count
    
    print(f"✅ Made {changes_made} replacements")
    
    # Write the updated file
    with open(handlers_file, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print(f"✅ Updated {handlers_file}")
    
    # Verify the changes
    with open(handlers_file, 'r', encoding='utf-8') as f:
        verify_content = f.read()
    
    remaining_calls = verify_content.count('send_trading_alert(')
    lite_calls = verify_content.count('send_lite_alert(')
    
    print(f"\nVerification:")
    print(f"  send_trading_alert calls remaining: {remaining_calls}")
    print(f"  send_lite_alert calls now: {lite_calls}")
    
    if remaining_calls == 0 and lite_calls > 0:
        print("✅ All handlers successfully updated to use compact formatting!")
        return True
    else:
        print("❌ Some issues remain")
        return False

if __name__ == "__main__":
    print("LITE HANDLERS COMPACT FORMATTING FIX")
    print("=" * 60)
    
    success = fix_handlers()
    
    if success:
        print("\n🎉 SUCCESS! All lite handlers now use compact Telegram formatting")
        print("\nNext steps:")
        print("1. Test with a real alert: demspxslayer 6000C filled")
        print("2. Verify compact format in Telegram")
        print("3. Apply to other handlers if needed")
    else:
        print("\n❌ Fix failed - please check the output above")