# Dual-Channel Telegram Notifications

This system now supports sending different types of messages to separate Telegram channels with distinct notification sounds.

## Configuration

### Environment Variables
```env
TELEGRAM_BUY_ALERTS_CHAT_ID=-3189101185
TELEGRAM_UPDATES_CHAT_ID=-2901988458
```

## Usage

### For Buy Alerts (High Priority)
```python
# Send buy alert to dedicated alerts channel
result = await telegram_service.send_buy_alert(
    "AAPL $175 calls - Strong breakout signal detected!"
)
```

### For Updates/Status Messages
```python
# Send update to dedicated updates channel  
result = await telegram_service.send_update_message(
    "Portfolio update: +2.5% gain today, 15 active positions"
)
```

### Legacy Method (Still Works)
```python
# Original method - goes to main chat
result = await telegram_service.send_lite_alert(
    "General notification message"
)
```

## Message Formatting

- **Buy Alerts**: Automatically prefixed with `🚨 BUY ALERT 🚨`
- **Updates**: Automatically prefixed with `📈 UPDATE`
- Both use HTML parsing for formatting support

## Phone Notification Setup

1. **Buy Alerts Channel**:
   - Open channel in Telegram app
   - Tap channel name → Notifications
   - Set custom sound (e.g., "Alarm", "Horn", "Emergency")
   - Enable vibration if desired

2. **Updates Channel**:
   - Open channel in Telegram app  
   - Tap channel name → Notifications
   - Set different sound (e.g., "Chime", "Soft ping")
   - Or set to silent if preferred

## Testing

Run the test script to verify functionality:
```bash
python test_dual_channels.py
```

## Integration Examples

### In Alert Handlers
```python
# For new position entries/buy signals
if alert_type == "buy_entry":
    await telegram_service.send_buy_alert(alert_message)

# For position updates/status
else:
    await telegram_service.send_update_message(alert_message)
```

### Message Routing Logic
```python
def route_telegram_notification(message_type: str, content: str):
    if message_type in ["buy_alert", "entry_signal", "new_position"]:
        return telegram_service.send_buy_alert(content)
    elif message_type in ["update", "status", "profit_loss"]:
        return telegram_service.send_update_message(content)
    else:
        return telegram_service.send_lite_alert(content)  # Fallback
```

## Benefits

- ✅ **Distinct notification sounds** for different message types
- ✅ **Separate chat history** for easy review and filtering
- ✅ **Individual notification control** per channel
- ✅ **Can mute updates while keeping alerts active**
- ✅ **Easy to add more categories** (just add more channels)
- ✅ **Backward compatible** with existing code