#!/usr/bin/env python3
"""
Test runner for IBKR Strategy Builder Backend
Provides convenient commands to run different test categories
"""

import sys
import subprocess
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a command and print results"""
    print(f"\n{'='*60}")
    print(f"🧪 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"❌ Errors:\n{result.stderr}")
        
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Failed to run command: {e}")
        return False

def main():
    """Main test runner"""
    if len(sys.argv) < 2:
        print("""
🧪 IBKR Strategy Builder Backend Test Runner

Usage: python run_tests.py <category>

Available categories:
  telegram      - Run Telegram bot tests
  ibkr          - Run IBKR integration tests  
  notifications - Run notification system tests
  integration   - Run integration/end-to-end tests
  demslayer     - Run Demslayer handler tests
  all           - Run all Python tests
  
Examples:
  python run_tests.py telegram
  python run_tests.py all
        """)
        return

    category = sys.argv[1].lower()
    
    # Ensure we're in the right directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    if category == "telegram":
        run_command("python -m pytest tests/telegram/ -v", "Running Telegram Bot Tests")
        
    elif category == "ibkr":
        run_command("python -m pytest tests/ibkr/ -v", "Running IBKR Integration Tests")
        
    elif category == "notifications":
        run_command("python -m pytest tests/notifications/ -v", "Running Notification System Tests")
        
    elif category == "integration":
        run_command("python -m pytest tests/integration/ -v", "Running Integration Tests")
        
    elif category == "demslayer":
        run_command("python -m pytest tests/demslayer/ -v", "Running Demslayer Handler Tests")
        
    elif category == "all":
        run_command("python -m pytest tests/ -v", "Running All Tests")
        
    else:
        print(f"❌ Unknown category: {category}")
        print("Available categories: telegram, ibkr, notifications, integration, demslayer, all")

if __name__ == "__main__":
    main()
