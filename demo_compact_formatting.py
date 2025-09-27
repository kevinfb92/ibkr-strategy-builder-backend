#!/usr/bin/env python3

"""
Test compact formatting with a mock telegram service
"""

import asyncio
import sys
import os
sys.path.append(os.getcwd())

from app.services.handlers.lite_handlers import LiteDemslayerHandler, _format_expiry_for_display

class MockTelegramService:
    """Mock telegram service to test message formatting"""
    
    async def send_lite_alert(self, alerter_name, message, ticker):
        """Mock send_lite_alert that just prints the message"""
        print("🔔 TELEGRAM MESSAGE (COMPACT FORMAT):")
        print("=" * 50)
        print(f"Alerter: {alerter_name}")
        print(f"Ticker: {ticker}")
        print("Message:")
        print(message)
        print("=" * 50)
        
        return {"success": True, "message_id": "test_12345"}

async def test_compact_formatting():
    """Test the compact formatting directly"""
    
    print("TESTING COMPACT FORMATTING")
    print("=" * 60)
    
    # Create mock telegram service
    mock_telegram = MockTelegramService()
    
    # Create handler with mock
    handler = LiteDemslayerHandler()
    
    # Mock the ibkr service calls
    async def mock_get_stock_conid(ticker):
        return 12345 if ticker == "SPX" else None
    
    async def mock_get_option_conid(ticker, strike, side, expiry):
        return 67890
    
    # Monkey patch the telegram service in the handler
    import app.services.handlers.lite_handlers as handlers_module
    handlers_module.telegram_service = mock_telegram
    handlers_module.ibkr_service.get_stock_conid = mock_get_stock_conid
    handlers_module.ibkr_service.get_option_conid = mock_get_option_conid
    
    print("✅ Set up mock services")
    print()
    
    # Test data
    test_cases = [
        {
            "ticker": "SPX",
            "strike": 6000.0,
            "side": "CALL", 
            "expiry": "0929",  # Sep 29
            "message": "demspxslayer 6000C filled - testing compact format"
        },
        {
            "ticker": "SPX",
            "strike": 5950.0,
            "side": "PUT",
            "expiry": "1025",  # Oct 25
            "message": "demspxslayer 5950P opened"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"TEST CASE {i}: {test_case['side']} option")
        print("-" * 30)
        
        result = await handler._send_buy_telegram(
            ticker=test_case["ticker"],
            strike=test_case["strike"], 
            side=test_case["side"],
            expiry=test_case["expiry"],
            stock_conid=12345,
            option_conid=67890,
            message=test_case["message"]
        )
        
        if result and result.get("success"):
            print("✅ Message sent successfully")
        else:
            print("❌ Message failed")
            print(f"Error: {result}")
        
        print()
    
    # Test expiry formatting function directly
    print("TESTING EXPIRY FORMATTING FUNCTION:")
    print("-" * 40)
    
    expiry_tests = ["0929", "1025", "1215", "0105"]
    for expiry in expiry_tests:
        formatted = _format_expiry_for_display(expiry)
        print(f"  {expiry} → {formatted}")
    
    print()
    print("🎉 All tests completed!")

if __name__ == "__main__":
    asyncio.run(test_compact_formatting())