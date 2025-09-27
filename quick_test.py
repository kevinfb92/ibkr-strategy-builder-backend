#!/usr/bin/env python3
"""
Quick test for Stop Loss Management API endpoints
"""

import requests
import json
import time

BASE_URL = "http://localhost:8001"

def test_endpoints():
    print("=== STOP LOSS MANAGEMENT API TEST ===\n")
    
    # Test 1: Health check
    print("1. Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Health check: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")
        return
    
    # Test 2: Create stop loss management
    print("\n2. Testing stop loss management creation...")
    payload = {
        "conid": 725797159,  # SNOA
        "percentage": 5.0
    }
    
    try:
        response = requests.post(f"{BASE_URL}/stop-loss-management", json=payload, timeout=30)
        print(f"Create response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print("✅ Stop loss management created!")
            print(f"Status: {result['success']}")
            print(f"Message: {result['message']}")
            if 'data' in result and 'config' in result['data']:
                config = result['data']['config']
                print(f"Config - CONID: {config['conid']}, Percentage: {config['percentage']}, Status: {config['status']}")
        else:
            print(f"❌ Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 3: Get configurations
    print("\n3. Testing get configurations...")
    try:
        response = requests.get(f"{BASE_URL}/stop-loss-management", timeout=10)
        print(f"Get response: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print("✅ Configurations retrieved!")
            print(f"Active configs: {len(result['data']['active_configs'])}")
            print(f"Monitoring active: {result['data']['monitoring_active']}")
        else:
            print(f"❌ Failed: {response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n=== TEST COMPLETE ===")

if __name__ == "__main__":
    test_endpoints()
