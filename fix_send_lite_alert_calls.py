#!/usr/bin/env python3

"""
Fix script to correct send_lite_alert method calls
"""

import os
import re

def fix_send_lite_alert_calls():
    """Update all send_lite_alert calls to use correct signature"""
    
    handlers_file = "app/services/handlers/lite_handlers.py"
    
    if not os.path.exists(handlers_file):
        print(f"❌ File not found: {handlers_file}")
        return False
    
    # Read the current file
    with open(handlers_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Fixing send_lite_alert method calls...")
    print("=" * 50)
    
    # Pattern to find the incorrect calls
    pattern = r'result = await telegram_service\.send_lite_alert\(\s*alerter_name=self\.alerter_name,\s*message=telegram_message,\s*ticker=ticker\s*\)'
    replacement = 'result = await telegram_service.send_lite_alert(telegram_message)'
    
    # Count current occurrences
    matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
    print(f"Found {len(matches)} incorrect send_lite_alert calls")
    
    # Replace the pattern
    updated_content = re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)
    
    if updated_content == content:
        # Try alternative pattern without specific whitespace
        pattern2 = r'await telegram_service\.send_lite_alert\(\s*alerter_name=.*?\n.*?ticker=.*?\n.*?\)'
        replacement2 = 'await telegram_service.send_lite_alert(telegram_message)'
        
        updated_content = re.sub(pattern2, replacement2, content, flags=re.MULTILINE | re.DOTALL)
    
    if updated_content == content:
        # Try line by line replacement
        lines = content.split('\n')
        updated_lines = []
        i = 0
        changes_made = 0
        
        while i < len(lines):
            line = lines[i]
            if 'result = await telegram_service.send_lite_alert(' in line:
                # Look for the multi-line call
                if 'alerter_name=' in line or (i + 1 < len(lines) and 'alerter_name=' in lines[i + 1]):
                    # Replace the multi-line call
                    updated_lines.append('            result = await telegram_service.send_lite_alert(telegram_message)')
                    changes_made += 1
                    # Skip the next lines that are part of this call
                    while i + 1 < len(lines) and ('alerter_name=' in lines[i + 1] or 'message=' in lines[i + 1] or 'ticker=' in lines[i + 1] or ')' in lines[i + 1]):
                        i += 1
                        if ')' in lines[i]:
                            break
                else:
                    updated_lines.append(line)
            else:
                updated_lines.append(line)
            i += 1
        
        updated_content = '\n'.join(updated_lines)
        print(f"✅ Made {changes_made} replacements using line-by-line method")
    else:
        changes_made = len(matches)
        print(f"✅ Made {changes_made} replacements using regex method")
    
    if updated_content == content:
        print("❌ No changes made - pattern not found")
        return False
    
    # Write the updated file
    with open(handlers_file, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print(f"✅ Updated {handlers_file}")
    
    # Verify the changes
    with open(handlers_file, 'r', encoding='utf-8') as f:
        verify_content = f.read()
    
    correct_calls = verify_content.count('send_lite_alert(telegram_message)')
    incorrect_calls = verify_content.count('send_lite_alert(\n                alerter_name=')
    
    print(f"\nVerification:")
    print(f"  Correct calls: send_lite_alert(telegram_message): {correct_calls}")
    print(f"  Incorrect calls remaining: {incorrect_calls}")
    
    if incorrect_calls == 0 and correct_calls > 0:
        print("✅ All send_lite_alert calls fixed!")
        return True
    else:
        print("❌ Some issues remain")
        return False

if __name__ == "__main__":
    print("SEND_LITE_ALERT METHOD SIGNATURE FIX")
    print("=" * 60)
    
    success = fix_send_lite_alert_calls()
    
    if success:
        print("\n🎉 SUCCESS! All send_lite_alert calls now use correct signature")
        print("\nCalls now look like:")
        print("  result = await telegram_service.send_lite_alert(telegram_message)")
        print("\nInstead of:")
        print("  result = await telegram_service.send_lite_alert(")
        print("      alerter_name=self.alerter_name,")
        print("      message=telegram_message,")
        print("      ticker=ticker")
        print("  )")
    else:
        print("\n❌ Fix failed - please check the output above")