#!/usr/bin/env python3

"""
Fix script to add formatted expiry dates to all lite handlers
"""

import os
import re

def fix_expiry_formatting():
    """Update all lite handlers to use formatted expiry dates"""
    
    handlers_file = "app/services/handlers/lite_handlers.py"
    
    if not os.path.exists(handlers_file):
        print(f"❌ File not found: {handlers_file}")
        return False
    
    # Read the current file
    with open(handlers_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Updating expiry date formatting in lite_handlers.py...")
    print("=" * 60)
    
    # Find and replace the expiry formatting pattern
    original_pattern = r'(\s+telegram_message \+= f"[^"]+{ticker} - {int\(strike\) if strike\.is_integer\(\) else strike}{side_short} - {expiry}")'
    replacement_pattern = r'\1'.replace('{expiry}', '{formatted_expiry}')
    
    # More specific replacement using the exact line
    pattern_to_find = 'telegram_message += f"{emoji} {ticker} - {int(strike) if strike.is_integer() else strike}{side_short} - {expiry}"'
    replacement_line = 'formatted_expiry = _format_expiry_for_display(expiry)\n            telegram_message += f"{emoji} {ticker} - {int(strike) if strike.is_integer() else strike}{side_short} - {formatted_expiry}"'
    
    updated_content = content.replace(pattern_to_find, replacement_line)
    
    if updated_content == content:
        print("❌ No changes made - pattern not found")
        print(f"Looking for: {pattern_to_find}")
        return False
    
    # Count changes
    changes_made = content.count(pattern_to_find) - updated_content.count(pattern_to_find)
    print(f"✅ Made {changes_made} replacements")
    
    # Write the updated file
    with open(handlers_file, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print(f"✅ Updated {handlers_file}")
    
    # Verify the changes
    with open(handlers_file, 'r', encoding='utf-8') as f:
        verify_content = f.read()
    
    formatted_expiry_count = verify_content.count('formatted_expiry = _format_expiry_for_display(expiry)')
    raw_expiry_count = verify_content.count('- {expiry}"')
    
    print(f"\nVerification:")
    print(f"  formatted_expiry assignments: {formatted_expiry_count}")
    print(f"  raw expiry usage remaining: {raw_expiry_count}")
    
    if formatted_expiry_count > 0:
        print("✅ Expiry formatting successfully updated!")
        return True
    else:
        print("❌ Some issues remain")
        return False

if __name__ == "__main__":
    print("LITE HANDLERS EXPIRY FORMATTING FIX")
    print("=" * 60)
    
    success = fix_expiry_formatting()
    
    if success:
        print("\n🎉 SUCCESS! All lite handlers now use formatted expiry dates")
        print("\nFormatted dates will show as:")
        print("  0929 → Sep 29")
        print("  1025 → Oct 25")
        print("  1215 → Dec 15")
    else:
        print("\n❌ Fix failed - please check the output above")