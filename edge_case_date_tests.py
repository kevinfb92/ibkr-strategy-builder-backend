#!/usr/bin/env python3
"""
Edge case date extraction tests - focusing on problem areas
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.services.handlers.lite_handlers import _extract_expiry, LiteProfAndKianHandler
from datetime import datetime
import re

def test_date_format_normalization():
    """Test various date format edge cases"""
    print("=" * 60)
    print("TESTING DATE FORMAT NORMALIZATION EDGE CASES")
    print("=" * 60)
    
    # These cases failed in the main test
    edge_cases = [
        # Single digit dates - should pad with zeros
        ("NVDA 800C exp 11/8", "NVDA", "11/8", "11/08/2025", "Single digit day should pad to 11/08/2025"),
        ("AMD 120P expiring 10/4", "AMD", "10/4", "10/04/2025", "Single digit day should pad to 10/04/2025"),
        ("TSLA 250C 9/5 calls", "TSLA", "9/5", "09/05/2026", "Single digit month and day should pad"),
        
        # Mixed format cases
        ("SPY 400C 1/17 entry", "SPY", "1/17", "01/17/2026", "Should normalize to 01/17/2026"),
        ("QQQ 350P 12/1 puts", "QQQ", "12/1", "12/01/2025", "Should normalize to 12/01/2025"),
        
        # Zero-padding edge cases  
        ("AAPL 150C 1/1 calls", "AAPL", "1/1", "01/01/2026", "Should handle 1/1 as 01/01/2026"),
        ("MSFT 300P 2/2 puts", "MSFT", "2/2", "02/02/2026", "Should handle 2/2 as 02/02/2026"),
    ]
    
    for message, ticker, extracted_date, expected_result, description in edge_cases:
        # Find strike position
        strike_match = re.search(r'\d+[CP]', message.upper())
        strike_pos = strike_match.end() if strike_match else len(message)
        
        result = _extract_expiry(message, strike_pos, ticker)
        
        success = expected_result in result
        status = "✅" if success else "❌"
        
        print(f"{status} {description}")
        print(f"    Message: '{message}'")
        print(f"    Extracted: {extracted_date} → Expected: {expected_result}")
        print(f"    Actual Result: {result}")
        print()

def test_prof_kian_ticker_awareness():
    """Test Prof & Kian handler SPY/SPX awareness"""
    print("=" * 60)
    print("TESTING PROF & KIAN HANDLER TICKER AWARENESS")
    print("=" * 60)
    
    handler = LiteProfAndKianHandler()
    
    # Test cases where handler should use ticker-specific defaults
    test_cases = [
        ("SPY 400P calls", "SPY", "0DTE", "SPY without EXP should default to 0DTE"),
        ("SPX 5800C entry", "SPX", "0DTE", "SPX without EXP should default to 0DTE"),
        ("AAPL 150C target", "AAPL", "Friday", "AAPL without EXP should default to Friday"),
    ]
    
    for message, ticker, expected_behavior, description in test_cases:
        # Extract ticker from message for the handler
        extracted_ticker = None
        if "SPY" in message:
            extracted_ticker = "SPY"
        elif "SPX" in message:
            extracted_ticker = "SPX"
        elif "AAPL" in message:
            extracted_ticker = "AAPL"
        
        # Use the handler's detailed expiry extraction
        result = handler._extract_detailed_expiry(message, ticker=extracted_ticker)
        
        # Check result
        current_date = datetime.now().strftime("%m/%d")
        friday_date = datetime.now().strftime("%m/%d")  # Simplified for testing
        
        if expected_behavior == "0DTE":
            success = current_date in result
        elif expected_behavior == "Friday":
            # For Friday, we expect NOT current date (since it should be Friday)
            success = current_date not in result
        else:
            success = expected_behavior in result
        
        status = "✅" if success else "❌"
        print(f"{status} {description}")
        print(f"    Message: '{message}'")
        print(f"    Ticker: {extracted_ticker}, Expected: {expected_behavior}")
        print(f"    Result: {result}")
        print()

def test_year_rollover_logic():
    """Test year rollover logic for past dates"""
    print("=" * 60)
    print("TESTING YEAR ROLLOVER LOGIC")
    print("=" * 60)
    
    current_date = datetime.now()
    current_month = current_date.month
    current_day = current_date.day
    
    # Test dates that should roll to next year
    test_cases = [
        # Format: (message, expected_year)
        ("AAPL 150C 01/01 calls", 2026 if (1, 1) < (current_month, current_day) else 2025),
        ("TSLA 250P 02/15 puts", 2026 if (2, 15) < (current_month, current_day) else 2025),
        ("QQQ 350C 09/30 entry", 2026 if (9, 30) < (current_month, current_day) else 2025),
    ]
    
    for message, expected_year in test_cases:
        strike_match = re.search(r'\d+[CP]', message.upper())
        strike_pos = strike_match.end() if strike_match else len(message)
        
        result = _extract_expiry(message, strike_pos, "TEST")
        
        success = str(expected_year) in result
        status = "✅" if success else "❌"
        
        print(f"{status} Year rollover for message: '{message}'")
        print(f"    Expected year: {expected_year}")
        print(f"    Result: {result}")
        print()

def main():
    """Run edge case tests"""
    print("DATE EXTRACTION EDGE CASE TESTS")
    print("=" * 60)
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Current Month/Day: {datetime.now().month}/{datetime.now().day}")
    print()
    
    test_date_format_normalization()
    test_prof_kian_ticker_awareness()
    test_year_rollover_logic()
    
    print("=" * 60)
    print("EDGE CASE TESTS COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    main()