#!/bin/bash
# CURL commands for testing SPX automated trading via /notification endpoint
# SPX current price: 6482
# Correct payload format: {"title": "title", "message": "message", "subtext": "subtext"}

# Option 1: ATM Call (Conservative pricing)
curl -X POST "http://localhost:8000/notification" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "SPX 6500C AUG29 - BUY SIGNAL",
    "message": "SPX is at 6482, looking for a breakout above 6500\n\nBid: $15.20 Ask: $15.80 Last: $15.50\nOpen Interest: 12.5K\n\nTarget: Quick scalp on momentum",
    "subtext": "DeMsLayer Alert"
  }'

# Option 2: ATM Put (Realistic pricing)
curl -X POST "http://localhost:8000/notification" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "SPX 6480P AUG29 SETUP", 
    "message": "Current SPX: 6482\nLooking for a pullback entry\n\nBid: $48.50\nAsk: $49.20\nLast: $48.85\nOpen Interest: 8.7K\n\nStrategy: Quick hedge play on market dip",
    "subtext": "DeMsLayer Alert"
  }'

# Option 3: OTM Call (Lower price - RECOMMENDED FOR TESTING)
curl -X POST "http://localhost:8000/notification" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "SPX 6520C AUG29 MOMENTUM PLAY",
    "message": "SPX @ 6482 - watching for breakout\n\nBid: $3.40\nAsk: $3.80\nLast: $3.60\nOI: 15.2K\n\nQuick momentum trade setup",
    "subtext": "DeMsLayer Alert"
  }'

# Option 4: Very conservative OTM put for testing
curl -X POST "http://localhost:8000/notification" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "SPX 6400P AUG29 - HEDGE PLAY",
    "message": "SPX @ 6482 - protective put\n\nBid: $0.85\nAsk: $1.15\nLast: $1.00\nOI: 25.3K\n\nDownside protection trade",
    "subtext": "DeMsLayer Alert"
  }'

# Option 5: Ultra conservative for testing automation
curl -X POST "http://localhost:8000/notification" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "SPX 6350P AUG29 - TEST TRADE",
    "message": "SPX @ 6482 - far OTM put for testing\n\nBid: $0.25\nAsk: $0.35\nLast: $0.30\nOI: 45.8K\n\nAutomation test with minimal risk",
    "subtext": "DeMsLayer Test"
  }'
