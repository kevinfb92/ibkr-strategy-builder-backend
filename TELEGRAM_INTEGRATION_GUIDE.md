# Telegram Bot Integration Setup Guide

## Overview
Your notification system now automatically sends trading alerts to Telegram with Buy/Sell buttons whenever alerter notifications are received.

## Bot Information
- **Bot Token**: `8331227211:AAHfYne1uCNrm58FoBHpsU8tD95ETepP_VY`
- **Target User**: @Kevchan

## Setup Steps

### 1. Get Your Chat ID
First, you need to get your chat ID so the bot knows where to send messages:

#### Option A: Use the Discovery Script
```bash
cd c:\Users\kevin\Desktop\trading\stoqey\ibkr-strategy-builder-backend
python discover_chat_id.py
```
Then send `/start` to your bot.

#### Option B: Manual Method
1. Start your bot (send any message or `/start`)
2. Use the API endpoint to check discovered chats:
   ```
   GET http://192.168.1.135:8000/telegram/status
   ```

### 2. Set Your Chat ID (if needed)
If the auto-discovery doesn't work, you can manually set your chat ID:
```bash
POST http://192.168.1.135:8000/telegram/set-chat-id
Content-Type: application/json

{
  "chat_id": "YOUR_CHAT_ID_HERE"
}
```

### 3. Test the Integration
Send a test message to verify everything works:
```bash
POST http://192.168.1.135:8000/telegram/test-message
```

## How It Works

### 1. Automatic Alerts
When any notification is received through `/notification`, the system:
1. Processes the notification through the alerter system
2. Extracts relevant trading information
3. Sends a formatted message to Telegram with Buy/Sell buttons
4. Tracks the message for response handling

### 2. Telegram Message Format
```
🚨 Trading Alert

🎯 Alerter: Nyrleth
📊 Ticker: AAPL
💬 Message: Strong resistance breakout at $150
ℹ️ Details: Signal: TECHNICAL | Confidence: HIGH

⏰ Time: 2025-08-26 15:30:45
🆔 ID: abc12345

[🟢 BUY] [🔴 SELL]
```

### 3. Button Response Handling
When you click Buy or Sell:
- The message updates to show your choice
- The response is logged and tracked
- Ready for integration with trading actions

## API Endpoints

### Telegram Management
- `GET /telegram/status` - Get bot status and pending messages
- `POST /telegram/set-chat-id` - Manually set chat ID
- `POST /telegram/test-message` - Send test message

### Notification Processing (Enhanced)
- `POST /notification` - Now automatically sends to Telegram
- `GET /alerters` - Get supported alerter information

## Message Tracking

### Pending Messages
Each message sent has a unique ID and is tracked until responded to:
```json
{
  "abc12345": {
    "alerter": "Nyrleth",
    "original_message": "Strong resistance breakout",
    "ticker": "AAPL",
    "timestamp": "2025-08-26T15:30:45",
    "response": {
      "action": "BUY",
      "timestamp": "2025-08-26T15:31:12",
      "user_id": 123456789,
      "username": "Kevchan"
    }
  }
}
```

### Getting Responses
Check responses programmatically:
```bash
GET http://192.168.1.135:8000/telegram/status
```

## Integration with Alerters

### Supported Alerters
All alerters now automatically send to Telegram:
- **Real Day Trading**: Shows ticker, action, price
- **Nyrleth**: Shows signal type, confidence level  
- **demslayer-spx-alerts**: Shows SPX level, option details
- **prof-and-kian-alerts**: Shows entry, target, stop loss

### Message Content Customization
Each alerter type includes specific information in the Telegram message:

#### Real Day Trading
```
🎯 Alerter: Real Day Trading
📊 Ticker: AAPL
💬 Message: Buy signal triggered
ℹ️ Details: Action: BUY | Price: $150.25
```

#### Nyrleth
```
🎯 Alerter: Nyrleth  
📊 Ticker: TSLA
💬 Message: Technical breakout pattern
ℹ️ Details: Signal: TECHNICAL | Confidence: HIGH
```

## Error Handling

### Common Issues
1. **No Chat ID**: User needs to send `/start` to bot first
2. **Bot Not Started**: Check if Telegram service is running
3. **Network Issues**: Verify internet connection and bot token

### Error Responses
```json
{
  "success": false,
  "message": "Cannot send message: No chat ID available",
  "error": "missing_chat_id"
}
```

## Future Enhancements

### Planned Features
1. **Trading Integration**: Connect button clicks to actual IBKR orders
2. **Multiple Users**: Support for multiple chat IDs
3. **Message Templates**: Customizable message formats per alerter
4. **Response Analytics**: Track response patterns and timing

### Button Action Integration
Currently buttons just track responses. To add actual trading:

```python
async def _process_trading_action(self, action: str, message_info: Dict[str, Any]):
    """Process the trading action"""
    if action == 'BUY':
        # Integration with IBKR service
        await ibkr_service.place_buy_order(
            ticker=message_info['ticker'],
            # ... other parameters
        )
    elif action == 'SELL':
        await ibkr_service.place_sell_order(
            ticker=message_info['ticker'],
            # ... other parameters  
        )
```

## Testing Examples

### Test Notification with Telegram
```bash
POST http://192.168.1.135:8000/notification
Content-Type: application/json

{
  "title": "Nyrleth",
  "message": "AAPL", 
  "subtext": "Strong resistance breakout at $150 - high confidence signal"
}
```

This will:
1. Process through Nyrleth handler
2. Extract ticker (AAPL), signal type (TECHNICAL), confidence (HIGH)
3. Send formatted message to your Telegram
4. Wait for your Buy/Sell response

## Troubleshooting

### Check Bot Status
```bash
GET http://192.168.1.135:8000/telegram/status
```

### View Application Logs
The server console will show:
- Telegram message sending attempts
- Button press responses  
- Error messages and troubleshooting info

### Manual Chat ID Discovery
If auto-discovery fails, you can find your chat ID by:
1. Messaging the bot
2. Checking the server logs for chat ID information
3. Using Telegram API tools online

## Security Notes
- Bot token is hardcoded for development (consider environment variables for production)
- Only your username (@Kevchan) should have access to the bot
- Button responses are logged for audit purposes
