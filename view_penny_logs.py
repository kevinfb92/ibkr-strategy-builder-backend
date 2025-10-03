#!/usr/bin/env python3
"""
Penny stock notification log viewer utility
"""
import os
import sys
from datetime import datetime


def view_notification_logs():
    """View and format penny stock notification logs"""
    
    # Find the log file
    script_dir = os.path.dirname(__file__)
    log_file = os.path.join(script_dir, 'logs', 'penny_stock_notifications.log')
    
    print("📝 Penny Stock Notification Log Viewer")
    print("=" * 60)
    print(f"📂 Log file: {log_file}")
    
    if not os.path.exists(log_file):
        print("❌ Log file not found. No notifications logged yet.")
        return
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if not lines:
            print("📄 Log file is empty. No notifications logged yet.")
            return
        
        print(f"📊 Total notifications: {len(lines)}")
        print("-" * 60)
        
        for i, line in enumerate(lines, 1):
            try:
                # Parse the log line
                parts = line.strip().split(' | ')
                if len(parts) >= 3:
                    timestamp = parts[0]
                    level = parts[1]
                    content = ' | '.join(parts[2:])
                    
                    # Extract notification type and ticker
                    if '][' in content:
                        type_part = content.split(']')[0] + ']'
                        ticker_part = content.split('] ')[1].split(' |')[0] if '] ' in content else 'Unknown'
                        message_part = ' | '.join(content.split(' | ')[1:])
                    else:
                        type_part = 'UNKNOWN'
                        ticker_part = 'Unknown'
                        message_part = content
                    
                    print(f"\n📧 Notification #{i}")
                    print(f"   ⏰ Time: {timestamp}")
                    print(f"   🏷️  Type: {type_part}")
                    print(f"   📊 Ticker: {ticker_part}")
                    print(f"   💬 Content: {message_part[:100]}{'...' if len(message_part) > 100 else ''}")
                    
                else:
                    print(f"\n❌ Malformed log entry #{i}: {line.strip()}")
                    
            except Exception as e:
                print(f"\n❌ Error parsing log entry #{i}: {e}")
                print(f"   Raw: {line.strip()}")
        
        print("\n" + "=" * 60)
        print("✅ Log viewing complete")
        
    except Exception as e:
        print(f"❌ Error reading log file: {e}")


def tail_logs(lines=10):
    """Show the last N log entries"""
    
    script_dir = os.path.dirname(__file__)
    log_file = os.path.join(script_dir, 'logs', 'penny_stock_notifications.log')
    
    print(f"📝 Last {lines} Penny Stock Notifications")
    print("=" * 60)
    
    if not os.path.exists(log_file):
        print("❌ Log file not found.")
        return
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        recent_lines = all_lines[-lines:] if len(all_lines) >= lines else all_lines
        
        for line in recent_lines:
            parts = line.strip().split(' | ')
            if len(parts) >= 3:
                timestamp = parts[0]
                notification_info = ' | '.join(parts[2:])
                print(f"{timestamp} | {notification_info}")
            else:
                print(line.strip())
                
    except Exception as e:
        print(f"❌ Error reading log file: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tail":
        tail_lines = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        tail_logs(tail_lines)
    else:
        view_notification_logs()