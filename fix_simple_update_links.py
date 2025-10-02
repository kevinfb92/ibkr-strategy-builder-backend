#!/usr/bin/env python3

"""
Fix script to add formatted expiry dates to UPDATE messages and compact links
"""

import os

def fix_update_and_links():
    """Fix expiry formatting and link display"""
    
    handlers_file = "app/services/handlers/lite_handlers.py"
    
    if not os.path.exists(handlers_file):
        print(f"❌ File not found: {handlers_file}")
        return False
    
    # Read the current file
    with open(handlers_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Fixing UPDATE message expiry formatting and link display...")
    print("=" * 60)
    
    # Fix UPDATE messages - add expiry formatting and HTML links
    old_update_line = 'telegram_message += f"{emoji} {ticker} - {details[\'strike\']}{details[\'side\']} - {details[\'expiry\']} 🔗 Option Quote ({quote_link})\\n"'
    
    new_update_block = '''# Format expiry date for readability
                    formatted_expiry = _format_expiry_for_display(details['expiry'])
                    
                    telegram_message += f"{emoji} {ticker} - {details['strike']}{details['side']} - {formatted_expiry}  <a href='{quote_link}'>🔗 Option Quote</a>\\n"'''
    
    # Count and replace UPDATE messages
    update_count = content.count(old_update_line)
    updated_content = content.replace(old_update_line, new_update_block)
    
    print(f"Fixed {update_count} UPDATE message lines")
    
    # Fix BUY message links - Option Chain
    old_chain_link = 'telegram_message += f"  Option Chain ({chain_link})"'
    new_chain_link = 'telegram_message += f"  <a href=\'{chain_link}\'>Option Chain</a>"'
    
    chain_count = updated_content.count(old_chain_link)
    updated_content = updated_content.replace(old_chain_link, new_chain_link)
    
    print(f"Fixed {chain_count} Option Chain links")
    
    # Fix BUY message links - Option Quote  
    old_quote_link = 'telegram_message += f" | 🔗 Option Quote ({quote_link})"'
    new_quote_link = 'telegram_message += f" | <a href=\'{quote_link}\'>🔗 Option Quote</a>"'
    
    quote_count = updated_content.count(old_quote_link)
    updated_content = updated_content.replace(old_quote_link, new_quote_link)
    
    print(f"Fixed {quote_count} Option Quote links")
    
    total_changes = update_count + chain_count + quote_count
    
    if total_changes == 0:
        print("❌ No changes made - patterns not found")
        return False
    
    # Write the updated file
    with open(handlers_file, 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print(f"✅ Updated {handlers_file}")
    
    # Verify the changes
    with open(handlers_file, 'r', encoding='utf-8') as f:
        verify_content = f.read()
    
    html_links = verify_content.count('<a href=')
    formatted_expiry_in_updates = verify_content.count('formatted_expiry = _format_expiry_for_display(details[')
    
    print(f"\nVerification:")
    print(f"  Total changes made: {total_changes}")
    print(f"  HTML links now: {html_links}")
    print(f"  Formatted expiry in updates: {formatted_expiry_in_updates}")
    
    if html_links > 0 and formatted_expiry_in_updates > 0:
        print("✅ Both fixes applied successfully!")
        return True
    else:
        print("❌ Some fixes may not have been applied")
        return False

if __name__ == "__main__":
    print("UPDATE MESSAGE & LINK FORMATTING FIX")
    print("=" * 50)
    
    success = fix_update_and_links()
    
    if success:
        print("\n🎉 SUCCESS! Fixed both issues:")
        print("\n✅ UPDATE messages now format expiry dates")
        print("✅ All links are now compact HTML format")
        print("\nMessages will show:")
        print("  • Dates: 0929 → Sep 29")
        print("  • Links: Clickable text instead of full URLs")
    else:
        print("\n❌ Fix incomplete - check output above")