#!/bin/bash
# CORRECT CURL commands for testing demslayer SPX alerts via /notification endpoint
# SPX current price: 6482
# 
# IMPORTANT: For demslayer alerts to be detected properly:
# - "title" field should be "demslayer-spx-alerts" to trigger the right handler
# - "message" field contains the actual alert message with contract info
# - "subtext" field contains additional context (can be the source)

echo "Testing demslayer SPX alerts with correct payload format..."

# Test 1: ATM Call Alert (Conservative entry)
echo "🚀 Test 1: ATM Call Alert"
curl -X POST "http://localhost:8000/notification" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "demslayer-spx-alerts",
    "message": "SPX 6500C AUG29 - Strong breakout signal detected!\n\nCurrent SPX: 6482\nTarget Strike: 6500\nBid: $15.20 Ask: $15.80 Last: $15.50\nOpen Interest: 12.5K\n\nMomentum play for quick scalp",
    "subtext": "DeMsLayer Premium Alert"
  }'

echo -e "\n\n"

# Test 2: ATM Put Alert (Hedge setup)  
echo "📉 Test 2: ATM Put Alert"
curl -X POST "http://localhost:8000/notification" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "demslayer-spx-alerts", 
    "message": "SPX 6480P AUG29 - Pullback entry setup\n\nCurrent SPX: 6482\nLooking for quick dip\nBid: $48.50 Ask: $49.20 Last: $48.85\nOpen Interest: 8.7K\n\nDefensive hedge positioning",
    "subtext": "DeMsLayer Alert System"
  }'

echo -e "\n\n"

# Test 3: OTM Call Alert (Lower price - BEST FOR TESTING)
echo "💎 Test 3: OTM Call Alert (RECOMMENDED)"
curl -X POST "http://localhost:8000/notification" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "demslayer-spx-alerts",
    "message": "SPX 6520C AUG29 - Momentum breakout setup!\n\nSPX Current: 6482\nTarget: 6520 strike\nBid: $3.40 Ask: $3.80 Last: $3.60\nOpen Interest: 15.2K\n\nLow cost, high reward potential",
    "subtext": "DeMsLayer Trading Signal"
  }'

echo -e "\n\n"

# Test 4: Far OTM Put (Very low cost for testing)
echo "🔻 Test 4: Far OTM Put (Cheap Testing)"
curl -X POST "http://localhost:8000/notification" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "demslayer-spx-alerts",
    "message": "SPX 6400P AUG29 - Black swan protection\n\nSPX: 6482\nFar OTM protection\nBid: $1.85 Ask: $2.10 Last: $1.95\nOI: 22.8K\n\nInsurance play for portfolio",
    "subtext": "DeMsLayer Risk Management"
  }'

echo -e "\n\nAll curl commands sent! Check Telegram for button responses."
