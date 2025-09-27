#!/usr/bin/env python3

"""
Fix script to correct send_lite_alert calls by replacing the entire call blocks
"""

import os

def fix_send_lite_alert_calls_targeted():
    """Update all send_lite_alert calls using targeted replacements"""
    
    handlers_file = "app/services/handlers/lite_handlers.py"
    
    if not os.path.exists(handlers_file):
        print(f"❌ File not found: {handlers_file}")
        return False
    
    # Read the current file
    with open(handlers_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Fixing send_lite_alert method calls with targeted approach...")
    print("=" * 60)
    
    # Find and replace each multi-line send_lite_alert call
    old_pattern = """result = await telegram_service.send_lite_alert(
                alerter_name=self.alerter_name,
                message=telegram_message,
                ticker=""
            )"""
    
    new_pattern = """result = await telegram_service.send_lite_alert(telegram_message)"""
    
    # Count occurrences
    count_before = content.count('alerter_name=self.alerter_name,')
    
    # Replace the pattern
    updated_content = content.replace(old_pattern, new_pattern)
    
    # Also try with different ticker values
    patterns_to_replace = [
        ("""result = await telegram_service.send_lite_alert(
                alerter_name=self.alerter_name,
                message=telegram_message,
                ticker=""
            )""", """result = await telegram_service.send_lite_alert(telegram_message)"""),
        
        ("""result = await telegram_service.send_lite_alert(
                alerter_name=self.alerter_name,
                message=telegram_message,
                ticker=ticker
            )""", """result = await telegram_service.send_lite_alert(telegram_message)"""),
    ]
    
    changes_made = 0
    for old_pat, new_pat in patterns_to_replace:
        old_count = updated_content.count(old_pat)
        updated_content = updated_content.replace(old_pat, new_pat)
        new_count = updated_content.count(old_pat)
        changes_made += (old_count - new_count)
        if old_count > 0:
            print(f"✅ Replaced {old_count} occurrences of pattern")
    
    count_after = updated_content.count('alerter_name=self.alerter_name,')
    total_changes = count_before - count_after
    
    print(f"Total changes made: {total_changes}")
    
    if updated_content == content:
        print("❌ No changes made - trying line-by-line approach")
        
        # Line by line approach
        lines = content.split('\n')
        updated_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Check if this line starts a send_lite_alert call with wrong signature
            if 'result = await telegram_service.send_lite_alert(' in line and 'telegram_message)' not in line:
                # This is the start of a multi-line call - replace it
                updated_lines.append('            result = await telegram_service.send_lite_alert(telegram_message)')
                changes_made += 1
                
                # Skip the parameter lines
                i += 1
                while i < len(lines) and ('alerter_name=' in lines[i] or 'message=' in lines[i] or 'ticker=' in lines[i]):
                    i += 1
                
                # Skip the closing parenthesis line
                if i < len(lines) and ')' in lines[i] and 'return' not in lines[i]:
                    i += 1
                
                # Continue from the next line
                continue
            else:
                updated_lines.append(line)
            
            i += 1
        
        updated_content = '\n'.join(updated_lines)
        print(f"✅ Made {changes_made} replacements using line-by-line method")
    
    if updated_content == content:
        print("❌ No changes made")
        return False
    
    # Write the updated file
    with open(handlers_file, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print(f"✅ Updated {handlers_file}")
    
    # Verify the changes
    with open(handlers_file, 'r', encoding='utf-8') as f:
        verify_content = f.read()
    
    correct_calls = verify_content.count('send_lite_alert(telegram_message)')
    incorrect_calls = verify_content.count('alerter_name=self.alerter_name,')
    
    print(f"\nVerification:")
    print(f"  Correct calls: send_lite_alert(telegram_message): {correct_calls}")  
    print(f"  Incorrect parameter usage remaining: {incorrect_calls}")
    
    if incorrect_calls == 0:
        print("✅ All send_lite_alert calls fixed!")
        return True
    else:
        print("❌ Some incorrect calls may remain")
        return incorrect_calls < count_before  # Progress made

if __name__ == "__main__":
    print("TARGETED SEND_LITE_ALERT METHOD SIGNATURE FIX")
    print("=" * 60)
    
    success = fix_send_lite_alert_calls_targeted()
    
    if success:
        print("\n🎉 SUCCESS! Fixed send_lite_alert method calls")
        print("\nMethod calls now use the correct signature:")
        print("  result = await telegram_service.send_lite_alert(telegram_message)")
    else:
        print("\n⚠️ Some issues may remain - please check manually")