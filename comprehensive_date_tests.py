#!/usr/bin/env python3
"""
Comprehensive date extraction and defaulting tests for all alerters
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.services.handlers.lite_handlers import (
    _extract_expiry, 
    LiteRealDayTradingHandler,
    LiteDemslayerHandler,
    LiteProfAndKianHandler,
    LiteRobinDaHoodHandler
)
from datetime import datetime, timedelta
import re

def test_extract_expiry_function():
    """Test the core _extract_expiry function with various scenarios"""
    print("=" * 60)
    print("TESTING CORE _extract_expiry FUNCTION")
    print("=" * 60)
    
    current_date = datetime.now().strftime("%m/%d/%Y")
    current_date_short = datetime.now().strftime("%m/%d")
    
    # Calculate next Friday
    today = datetime.now()
    days_ahead = 4 - today.weekday()  # Friday is weekday 4
    if days_ahead <= 0:
        days_ahead += 7
    next_friday = today + timedelta(days=days_ahead)
    friday_date = next_friday.strftime("%m/%d/%Y")
    
    print(f"Current date (0DTE): {current_date}")
    print(f"Next Friday: {friday_date}")
    print()
    
    test_cases = [
        # Format: (message, strike_pos, ticker, expected_behavior, description)
        ("SPY 400C @2.50", 6, "SPY", "0DTE", "SPY without expiry should default to 0DTE"),
        ("SPX 5800P entry", 10, "SPX", "0DTE", "SPX without expiry should default to 0DTE"),
        ("AAPL 150C target", 9, "AAPL", "Friday", "AAPL without expiry should default to Friday"),
        ("TSLA 250P 10/15 exp", 9, "TSLA", "10/15", "Explicit 10/15 date should be used"),
        ("QQQ 350C 12/20 target", 8, "QQQ", "12/20", "Explicit 12/20 date should be used"),
        ("NVDA 800C exp 11/8", 9, "NVDA", "11/8", "Explicit 11/8 date should be used"),
        ("AMD 120P expiring 10/4", 7, "AMD", "10/4", "Explicit 10/4 date should be used"),
        ("SPY 450C 1/17 calls", 8, "SPY", "1/17", "SPY with explicit date should use that date"),
        ("SPX 6000P 3/21 puts", 9, "SPX", "3/21", "SPX with explicit date should use that date"),
    ]
    
    for message, strike_pos, ticker, expected, description in test_cases:
        result = _extract_expiry(message, strike_pos, ticker)
        
        # Check if result matches expected behavior
        if expected == "0DTE":
            success = current_date in result or current_date_short in result
        elif expected == "Friday":
            success = friday_date in result
        else:
            # Specific date expected
            success = expected in result
        
        status = "✅" if success else "❌"
        print(f"{status} {description}")
        print(f"    Message: '{message}'")
        print(f"    Ticker: {ticker}, Expected: {expected}")
        print(f"    Result: {result}")
        print()

def test_real_day_trading_handler():
    """Test Real Day Trading handler date extraction"""
    print("=" * 60)
    print("TESTING REAL DAY TRADING HANDLER")
    print("=" * 60)
    
    handler = LiteRealDayTradingHandler()
    
    test_messages = [
        # Format: (title, message, expected_behavior, description)
        ("RDT Alert", "TSLA 250C entry", "Friday", "No expiry should default to Friday"),
        ("RDT Alert", "AAPL 150P expiring 10/15", "10/15", "Should extract 10/15 expiry"),
        ("RDT Alert", "QQQ 350C exp 12/20", "12/20", "Should extract 12/20 expiry"),
        ("RDT Alert", "NVDA 800P 11/8 expiry", "11/8", "Should extract 11/8 expiry"),
        ("RDT Alert", "SPY 400C calls", "Friday", "SPY should default to Friday (not 0DTE in RDT)"),
    ]
    
    for title, message, expected, description in test_messages:
        try:
            # Extract expiration using handler's method
            expiry = handler._extract_expiration_date(message)
            
            # Check result
            if expected == "Friday":
                # Should be None (which triggers closest expiry logic)
                success = expiry is None
            else:
                # Should extract specific date
                success = expiry and expected in expiry
            
            status = "✅" if success else "❌"
            print(f"{status} {description}")
            print(f"    Message: '{message}'")
            print(f"    Expected: {expected}, Result: {expiry}")
            print()
            
        except Exception as e:
            print(f"❌ Error testing RDT handler: {e}")
            print(f"    Message: '{message}'")
            print()

def test_demslayer_handler():
    """Test Demslayer handler date extraction"""
    print("=" * 60)
    print("TESTING DEMSLAYER HANDLER")
    print("=" * 60)
    
    handler = LiteDemslayerHandler()
    
    test_messages = [
        # Format: (message, expected_behavior, description)
        ("ALGO ENTRIES SPX 5800C", "0DTE", "SPX without expiry should default to 0DTE"),
        ("BTO SPX 5750P 1002", "1002", "Should extract 1002 (Oct 2) expiry"),
        ("ENTRIES SPX 5900C 1015", "1015", "Should extract 1015 (Oct 15) expiry"),
        ("SPX 5850P 12/20", "1220", "Should extract 12/20 as 1220"),
        ("SPX CALLS 5950C", "0DTE", "No expiry should default to 0DTE"),
    ]
    
    for message, expected, description in test_messages:
        try:
            # Use the handler's detection method
            import asyncio
            result = asyncio.run(handler._detect_spx_buy_alert(message))
            
            if result:
                expiry = result.get('expiry', '')
                
                if expected == "0DTE":
                    # Check if it's today's date in MMDD format
                    today_mmdd = datetime.now().strftime("%m%d")
                    success = expiry == today_mmdd
                else:
                    success = expiry == expected
                
                status = "✅" if success else "❌"
                print(f"{status} {description}")
                print(f"    Message: '{message}'")
                print(f"    Expected: {expected}, Result: {expiry}")
            else:
                print(f"❌ No SPX alert detected in message")
                print(f"    Message: '{message}'")
            print()
            
        except Exception as e:
            print(f"❌ Error testing Demslayer handler: {e}")
            print(f"    Message: '{message}'")
            print()

def test_prof_and_kian_handler():
    """Test Prof & Kian handler date extraction"""
    print("=" * 60)
    print("TESTING PROF & KIAN HANDLER")
    print("=" * 60)
    
    handler = LiteProfAndKianHandler()
    
    test_messages = [
        # Format: (message, expected_behavior, description)
        ("AAPL 150C EXP: 10/15/2025", "10/15/2025", "Should extract full date format"),
        ("TSLA 250P EXP: 12/20", "12/20", "Should extract MM/DD format"),
        ("QQQ 350C entry", "Friday", "No expiry should default to Friday"),
        ("SPY 400P calls", "0DTE", "SPY should default to 0DTE"),
        ("SPX 5800C EXP: 11/8", "11/8", "SPX with explicit date should use it"),
        ("NVDA 800C EXP: 1/2027exp", "1/2027", "Should handle monthly options format"),
    ]
    
    for message, expected, description in test_messages:
        try:
            # Extract using handler's method
            expiry = handler._extract_detailed_expiry(message, ticker="TEST")
            
            # Determine ticker for default logic
            ticker = None
            if "SPY" in message:
                ticker = "SPY"
            elif "SPX" in message:
                ticker = "SPX"
            
            if expected == "Friday":
                # Should contain next Friday's date
                today = datetime.now()
                days_ahead = 4 - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                next_friday = today + timedelta(days=days_ahead)
                friday_str = next_friday.strftime("%m/%d")
                success = friday_str in expiry
            elif expected == "0DTE":
                # Should contain today's date
                today_str = datetime.now().strftime("%m/%d")
                success = today_str in expiry
            else:
                # Should contain specific date
                success = expected in expiry
            
            status = "✅" if success else "❌"
            print(f"{status} {description}")
            print(f"    Message: '{message}'")
            print(f"    Expected: {expected}, Result: {expiry}")
            print()
            
        except Exception as e:
            print(f"❌ Error testing Prof & Kian handler: {e}")
            print(f"    Message: '{message}'")
            print()

def test_robindahood_handler():
    """Test RobinDaHood handler date extraction"""
    print("=" * 60)
    print("TESTING ROBINDAHOOD HANDLER")
    print("=" * 60)
    
    test_messages = [
        # Format: (message, ticker, expected_behavior, description)
        ("SPY 672P @.83 small position", "SPY", "0DTE", "SPY should default to 0DTE"),
        ("AAPL 150C @5.50 entry", "AAPL", "Friday", "AAPL should default to Friday"),
        ("TSLA 250P 10/15 @3.20", "TSLA", "10/15", "Should extract 10/15 expiry"),
        ("QQQ 350C exp 12/20", "QQQ", "12/20", "Should extract 12/20 expiry"),
        ("SPX 5800P calls", "SPX", "0DTE", "SPX should default to 0DTE"),
    ]
    
    for message, ticker, expected, description in test_messages:
        try:
            # Simulate the expiry extraction logic from robindahood handler
            strike_match = re.search(r'\d+[CP]', message.upper())
            strike_pos = strike_match.end() if strike_match else len(message)
            
            # This should now properly pass the ticker parameter
            expiry = _extract_expiry(message, strike_pos, ticker)
            
            if expected == "Friday":
                # Should contain next Friday's date
                today = datetime.now()
                days_ahead = 4 - today.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                next_friday = today + timedelta(days=days_ahead)
                friday_str = next_friday.strftime("%m/%d")
                success = friday_str in expiry
            elif expected == "0DTE":
                # Should contain today's date
                today_str = datetime.now().strftime("%m/%d")
                success = today_str in expiry
            else:
                # Should contain specific date
                success = expected in expiry
            
            status = "✅" if success else "❌"
            print(f"{status} {description}")
            print(f"    Message: '{message}'")
            print(f"    Ticker: {ticker}, Expected: {expected}")
            print(f"    Result: {expiry}")
            print()
            
        except Exception as e:
            print(f"❌ Error testing RobinDaHood handler: {e}")
            print(f"    Message: '{message}'")
            print()

def main():
    """Run all date extraction tests"""
    print("COMPREHENSIVE DATE EXTRACTION AND DEFAULTING TESTS")
    print("=" * 60)
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test core function
    test_extract_expiry_function()
    
    # Test each handler
    test_real_day_trading_handler()
    test_demslayer_handler()
    test_prof_and_kian_handler()
    test_robindahood_handler()
    
    print("=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    main()