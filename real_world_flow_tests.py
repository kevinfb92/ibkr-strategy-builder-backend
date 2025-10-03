#!/usr/bin/env python3
"""
Real-world message flow simulation tests for all alerters
"""
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

import asyncio
from datetime import datetime

async def test_robindahood_real_flow():
    """Test RobinDaHood handler with real message flow"""
    print("=" * 60)
    print("TESTING ROBINDAHOOD REAL MESSAGE FLOW")
    print("=" * 60)
    
    from app.services.handlers.lite_handlers import LiteRobinDaHoodHandler
    
    handler = LiteRobinDaHoodHandler()
    
    # Real robindahood message examples
    test_messages = [
        {
            'title': 'OWLS Capital',
            'message': '🌟robindahood-alerts: Small position\nPlay with profits\n\nSPY 672P @.83\nSee it here: https://discord.com/channels/123/456/789',
            'subtext': '',
            'expected_ticker': 'SPY',
            'expected_expiry_type': '0DTE',
            'description': 'SPY put without expiry should default to 0DTE'
        },
        {
            'title': 'OWLS Capital',
            'message': '🌟robindahood-alerts: Big position\n\nAAPL 150C @5.20\nEntry alert',
            'subtext': '',
            'expected_ticker': 'AAPL',
            'expected_expiry_type': 'Friday',
            'description': 'AAPL call without expiry should default to Friday'
        },
        {
            'title': 'OWLS Capital',
            'message': '🌟robindahood-alerts: TSLA 250P 10/15 @3.40\nSpecific date trade',
            'subtext': '',
            'expected_ticker': 'TSLA',
            'expected_expiry_type': '10/15',
            'description': 'TSLA put with explicit date should use that date'
        }
    ]
    
    for test_case in test_messages:
        try:
            print(f"Testing: {test_case['description']}")
            print(f"Message: {test_case['message'][:100]}...")
            
            # This would normally be called by the notification service
            result = await handler.process_notification_with_conid(test_case)
            
            if 'error' not in result:
                ticker = result.get('ticker', 'N/A')
                expiry = result.get('expiry', 'N/A')
                
                # Validate ticker
                ticker_correct = ticker == test_case['expected_ticker']
                
                # Validate expiry
                expected_type = test_case['expected_expiry_type']
                current_date = datetime.now().strftime("%m/%d")
                
                if expected_type == '0DTE':
                    expiry_correct = current_date in expiry
                elif expected_type == 'Friday':
                    expiry_correct = current_date not in expiry  # Should be different from today
                else:
                    expiry_correct = expected_type in expiry
                
                ticker_status = "✅" if ticker_correct else "❌"
                expiry_status = "✅" if expiry_correct else "❌"
                
                print(f"  {ticker_status} Ticker: Expected {test_case['expected_ticker']}, Got {ticker}")
                print(f"  {expiry_status} Expiry: Expected {expected_type}, Got {expiry}")
            else:
                print(f"  ❌ Error: {result['error']}")
            
            print()
            
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            print()

async def test_prof_kian_real_flow():
    """Test Prof & Kian handler with real message flow"""
    print("=" * 60)
    print("TESTING PROF & KIAN REAL MESSAGE FLOW")
    print("=" * 60)
    
    from app.services.handlers.lite_handlers import LiteProfAndKianHandler
    
    handler = LiteProfAndKianHandler()
    
    # Real Prof & Kian message examples
    test_messages = [
        {
            'title': 'Prof & Kian',
            'message': 'SPY 400P EXP: 10/15/2025\nEntry: $3.50\nTarget: $5.00',
            'subtext': '',
            'expected_ticker': 'SPY',
            'expected_expiry': '10/15/2025',
            'description': 'SPY with explicit full date should use that date'
        },
        {
            'title': 'Prof & Kian', 
            'message': 'AAPL 150C EXP: 12/20\nBuy signal active',
            'subtext': '',
            'expected_ticker': 'AAPL',
            'expected_expiry': '12/20',
            'description': 'AAPL with MM/DD format should normalize correctly'
        },
        {
            'title': 'Prof & Kian',
            'message': 'SPX 5800C\nImmediate entry',
            'subtext': '',
            'expected_ticker': 'SPX',
            'expected_expiry_type': '0DTE',
            'description': 'SPX without EXP should default to 0DTE'
        }
    ]
    
    for test_case in test_messages:
        try:
            print(f"Testing: {test_case['description']}")
            print(f"Message: {test_case['message']}")
            
            result = await handler.process_notification_with_conid(test_case)
            
            if 'error' not in result:
                ticker = result.get('ticker', 'N/A')
                expiry = result.get('expiry', 'N/A')
                
                # Validate ticker
                ticker_correct = ticker == test_case['expected_ticker']
                
                # Validate expiry
                if 'expected_expiry' in test_case:
                    # Specific date expected
                    expiry_correct = test_case['expected_expiry'] in expiry
                    expected_display = test_case['expected_expiry']
                else:
                    # Type-based validation
                    expected_type = test_case['expected_expiry_type']
                    current_date = datetime.now().strftime("%m/%d")
                    
                    if expected_type == '0DTE':
                        expiry_correct = current_date in expiry
                    else:
                        expiry_correct = current_date not in expiry
                    
                    expected_display = expected_type
                
                ticker_status = "✅" if ticker_correct else "❌"
                expiry_status = "✅" if expiry_correct else "❌"
                
                print(f"  {ticker_status} Ticker: Expected {test_case['expected_ticker']}, Got {ticker}")
                print(f"  {expiry_status} Expiry: Expected {expected_display}, Got {expiry}")
            else:
                print(f"  ❌ Error: {result['error']}")
            
            print()
            
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            print()

async def test_demslayer_real_flow():
    """Test Demslayer handler with real message flow"""
    print("=" * 60)
    print("TESTING DEMSLAYER REAL MESSAGE FLOW")
    print("=" * 60)
    
    from app.services.handlers.lite_handlers import LiteDemslayerHandler
    
    handler = LiteDemslayerHandler()
    
    # Real Demslayer message examples
    test_messages = [
        {
            'title': 'demslayer-spx-alerts',
            'message': 'ALGO ENTRIES\nSPX 5800C',
            'subtext': '',
            'expected_ticker': 'SPX',
            'expected_expiry_type': '0DTE',
            'description': 'SPX call without expiry should default to 0DTE'
        },
        {
            'title': 'demslayer-spx-alerts',
            'message': 'BTO SPX 5750P 1015',
            'subtext': '',
            'expected_ticker': 'SPX',
            'expected_expiry': '1015',
            'description': 'SPX with MMDD format should extract correctly'
        }
    ]
    
    for test_case in test_messages:
        try:
            print(f"Testing: {test_case['description']}")
            print(f"Message: {test_case['message']}")
            
            result = await handler.process_notification_with_conid(test_case)
            
            if 'error' not in result:
                ticker = result.get('ticker', 'N/A')
                expiry = result.get('expiry', 'N/A')
                
                # Validate ticker
                ticker_correct = ticker == test_case['expected_ticker']
                
                # Validate expiry
                if 'expected_expiry' in test_case:
                    # Specific date expected (MMDD format)
                    expiry_correct = test_case['expected_expiry'] in expiry
                    expected_display = test_case['expected_expiry']
                else:
                    # 0DTE expected (today in MMDD format)
                    today_mmdd = datetime.now().strftime("%m%d")
                    expiry_correct = today_mmdd in expiry
                    expected_display = '0DTE'
                
                ticker_status = "✅" if ticker_correct else "❌"
                expiry_status = "✅" if expiry_correct else "❌"
                
                print(f"  {ticker_status} Ticker: Expected {test_case['expected_ticker']}, Got {ticker}")
                print(f"  {expiry_status} Expiry: Expected {expected_display}, Got {expiry}")
            else:
                print(f"  ❌ Error: {result['error']}")
            
            print()
            
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            print()

async def main():
    """Run all real-world flow tests"""
    print("REAL-WORLD MESSAGE FLOW TESTS")
    print("=" * 60)
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    await test_robindahood_real_flow()
    await test_prof_kian_real_flow() 
    await test_demslayer_real_flow()
    
    print("=" * 60)
    print("ALL REAL-WORLD FLOW TESTS COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())