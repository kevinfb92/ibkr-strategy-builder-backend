# Tests Directory

This directory contains all test files for the IBKR Strategy Builder Backend, organized by category for better maintainability.

## Directory Structure

### `/curl/` - cURL Test Scripts
Shell scripts for testing API endpoints with cURL commands:
- `test_notification_curl.sh` - Test notification endpoints
- `test_demslayer_curl_commands.sh` - Test Demslayer-specific endpoints
- `test_curl_commands.sh` - General API endpoint tests

### `/demslayer/` - Demslayer Handler Tests
Tests specific to the Demslayer SPX alerts handler:
- `test_demslayer_scenarios.py` - Various Demslayer alert scenarios
- Additional Demslayer-specific test files

### `/ibkr/` - IBKR Service Tests
Tests for Interactive Brokers integration:
- `test_spx_market_data.py` - SPX market data retrieval
- `test_market_data_fields.py` - Market data field validation
- `test_stock_price.py` - Stock price data tests
- `test_strikes.py` / `test_strikes_new.py` - Options strike price tests
- `test_trailing_limit.py` - Trailing limit order tests
- `test_stop_loss.py` - Stop loss order tests
- `test_contract_replacement.py` - Contract replacement logic

### `/integration/` - Integration & End-to-End Tests
Complex tests that involve multiple components:
- `test_complete_order_flow.py` - Full order placement flow
- `test_final_automation.py` - Automated trading flow tests
- `test_button_press.py` - Button interaction tests
- `test_enhanced_*.py` - Enhanced feature integration tests
- `test_ws.py` - WebSocket connection tests
- `test_discord_webhook.py` - Discord webhook integration
- `test_free_runner_ws.py` - Free runner WebSocket tests
- `test_real_day_trading.py` - Real day trading scenarios

### `/notifications/` - Notification System Tests
Tests for notification processing and handling:
- `test_notifications.py` - General notification tests
- `test_notification_payload.py` - Notification payload validation
- `test_notification_mapping.py` - Notification routing tests
- `test_failing_payload.py` - Error handling for bad payloads
- `test_malformed_json.py` - Malformed JSON handling
- `test_various_payloads.py` - Different payload format tests

### `/telegram/` - Telegram Bot Tests
Tests for Telegram bot functionality:
- `test_telegram.py` - Core Telegram bot tests
- `test_telegram_bot.py` - Bot interaction tests
- `test_telegram_formatting.py` - Message formatting tests
- `test_telegram_open_interest.py` - Open interest display tests
- `test_direct_bot.py` - Direct bot communication tests
- `test_alerter_detection.py` - Alerter source detection
- `test_simple_button_detection.py` - Button detection logic

## Running Tests

### Python Tests
```bash
# Run all tests
python -m pytest tests/

# Run specific category
python -m pytest tests/telegram/
python -m pytest tests/ibkr/

# Run specific test file
python tests/telegram/test_telegram_bot.py
```

### Shell Script Tests
```bash
# Make executable and run
chmod +x tests/curl/test_notification_curl.sh
./tests/curl/test_notification_curl.sh
```

## Test Conventions

1. **Naming**: All test files start with `test_` prefix
2. **Organization**: Tests are grouped by functionality/component
3. **Dependencies**: Each test should be self-contained where possible
4. **Documentation**: Include docstrings explaining test purpose

## Adding New Tests

When adding new tests:
1. Place in appropriate subdirectory based on functionality
2. Follow existing naming conventions
3. Include proper documentation
4. Update this README if adding new categories
