#!/usr/bin/env python3

"""
Fix script to:
1. Add formatted expiry dates to UPDATE messages 
2. Convert full URLs to compact HTML links
"""

import os
import re

def fix_update_messages_and_links():
    """Fix expiry formatting and link display in all handlers"""
    
    handlers_file = "app/services/handlers/lite_handlers.py"
    
    if not os.path.exists(handlers_file):
        print(f"❌ File not found: {handlers_file}")
        return False
    
    # Read the current file
    with open(handlers_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Fixing UPDATE message expiry formatting and link display...")
    print("=" * 60)
    
    # Fix 1: Add formatted expiry to UPDATE messages
    update_pattern = r"telegram_message \+= f\"{emoji} {ticker} - {details\['strike'\]}{details\['side'\]} - {details\['expiry'\]} 🔗 Option Quote \({quote_link}\)\\n\""
    update_replacement = """formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{emoji} {ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\\n\""""
    
    # Count matches
    update_matches = len(re.findall(update_pattern, content))
    print(f"Found {update_matches} UPDATE message lines to fix")
    
    # Apply fix for UPDATE messages
    updated_content = re.sub(update_pattern, update_replacement, content)
    
    # Fix 2: Convert BUY message links to HTML format
    # Pattern for BUY messages with full URL links
    buy_patterns = [
        # Option Chain links
        (r'telegram_message \+= f" Option Chain \(\{chain_link\}\)"',
         'telegram_message += f"  <a href=\'{chain_link}\'>Option Chain</a>"'),
        
        # Option Quote links  
        (r'telegram_message \+= f" \| 🔗 Option Quote \(\{quote_link\}\)"',
         'telegram_message += f" | <a href=\'{quote_link}\'>🔗 Option Quote</a>"'),
    ]
    
    buy_changes = 0
    for pattern, replacement in buy_patterns:
        old_count = len(re.findall(pattern, updated_content))
        updated_content = re.sub(pattern, replacement, updated_content)
        new_count = len(re.findall(pattern, updated_content))
        changes = old_count - new_count
        buy_changes += changes
        if changes > 0:
            print(f"Fixed {changes} BUY message link patterns")
    
    total_changes = update_matches + buy_changes
    
    if updated_content == content:
        print("❌ No changes made - trying line-by-line approach")
        
        # Line by line approach for UPDATE messages
        lines = content.split('\n')
        updated_lines = []
        changes_made = 0
        
        for i, line in enumerate(lines):
            # Check for UPDATE message pattern
            if 'telegram_message += f"{emoji} {ticker} - {details[\'strike\']}{details[\'side\']} - {details[\'expiry\']} 🔗 Option Quote ({quote_link})' in line:
                # Replace with formatted version
                updated_lines.append('                    # Format expiry date for readability')
                updated_lines.append('                    formatted_expiry = _format_expiry_for_display(details[\'expiry\'])')
                updated_lines.append('                    ')
                updated_lines.append('                    telegram_message += f"{emoji} {ticker} - {details[\'strike\']}{details[\'side\']} - {formatted_expiry}  <a href=\'{quote_link}\'>🔗 Option Quote</a>\\n"')
                changes_made += 1
            # Check for BUY message patterns
            elif 'Option Chain ({chain_link})' in line:
                updated_lines.append(line.replace('Option Chain ({chain_link})', '<a href=\\'{chain_link}\\'>Option Chain</a>'))
                changes_made += 1
            elif '🔗 Option Quote ({quote_link})' in line:
                updated_lines.append(line.replace('🔗 Option Quote ({quote_link})', '<a href=\\'{quote_link}\\'>🔗 Option Quote</a>'))
                changes_made += 1
            else:
                updated_lines.append(line)
        
        updated_content = '\n'.join(updated_lines)
        print(f"✅ Made {changes_made} changes using line-by-line method")
        total_changes = changes_made
    else:
        print(f"✅ Made {total_changes} changes using regex method")
    
    if total_changes == 0:
        print("❌ No changes made")
        return False
    
    # Write the updated file
    with open(handlers_file, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print(f"✅ Updated {handlers_file}")
    
    # Verify the changes
    with open(handlers_file, 'r', encoding='utf-8') as f:
        verify_content = f.read()
    
    formatted_expiry_in_updates = verify_content.count('formatted_expiry = _format_expiry_for_display(details[\'expiry\'])')
    html_links = verify_content.count('<a href=')
    raw_links = verify_content.count('({quote_link})')
    
    print(f"\nVerification:")
    print(f"  Formatted expiry in UPDATE messages: {formatted_expiry_in_updates}")
    print(f"  HTML links: {html_links}")
    print(f"  Raw links remaining: {raw_links}")
    
    if formatted_expiry_in_updates > 0 and html_links > 0:
        print("✅ Both fixes applied successfully!")
        return True
    else:
        print("❌ Some fixes may not have been applied")
        return False

if __name__ == "__main__":
    print("UPDATE MESSAGE EXPIRY FORMATTING & LINK COMPACTING FIX")
    print("=" * 60)
    
    success = fix_update_messages_and_links()
    
    if success:
        print("\n🎉 SUCCESS! Fixed both issues:")
        print("\n✅ UPDATE messages now format expiry dates:")
        print("   0929 → Sep 29, 1025 → Oct 25")
        print("\n✅ Links are now compact HTML format:")
        print("   Before: 🔗 Option Quote (https://very-long-url...)")
        print("   After:  🔗 Option Quote (clickable link)")
        print("\nYour Telegram messages will now be clean and compact!")
    else:
        print("\n❌ Fix failed - please check the output above")