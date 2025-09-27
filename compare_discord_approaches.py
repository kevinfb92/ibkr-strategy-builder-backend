#!/usr/bin/env python3
"""
Alternative Discord link cleaning - compact instead of remove
"""

import re

def clean_discord_links_compact(message: str) -> str:
    """Compact Discord links instead of removing them"""
    # Pattern to match Discord links and the "See it here:" text
    discord_pattern = r'(\n?)See it here: (https://discord\.com/channels/\d+/\d+/\d+)'
    
    def replace_discord_link(match):
        newline = match.group(1)  # Preserve newline if it exists
        full_url = match.group(2)
        return f"{newline}[🔗 Discord]({full_url})"
    
    cleaned_message = re.sub(discord_pattern, replace_discord_link, message)
    return cleaned_message.strip()

def clean_discord_links_remove(message: str) -> str:
    """Remove Discord links completely"""
    # Pattern to match Discord links and the "See it here:" text
    discord_pattern = r'\n?See it here: https://discord\.com/channels/\d+/\d+/\d+'
    cleaned_message = re.sub(discord_pattern, '', message)
    return cleaned_message.strip()

# Test both approaches
test_message = """🌟demspxslayer-and-leaps: 6655P at 2.45 @everyone Size right. Could move fast.
See it here: https://discord.com/channels/718624848812834903/1407764518301335562/1419694213884547132"""

print("Original message:")
print(test_message)
print("\n" + "="*50)

print("\nOption 1 - Remove Discord links completely:")
print(clean_discord_links_remove(test_message))

print("\nOption 2 - Compact Discord links:")
print(clean_discord_links_compact(test_message))

print("\n" + "="*50)
print("Which approach do you prefer?")
print("1. Remove links completely (cleaner, more focused)")
print("2. Compact links (preserves access to Discord source)")
