#!/bin/bash
# CURL command for testing SPX automated trading via Postman
# SPX current price: 6482

# Basic trading alert test
curl -X POST "http://localhost:8000/webhook/demslayer-spx-alerts" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "SPX 6500C AUG29 - BUY SIGNAL\n\nSPX is at 6482, looking for a breakout above 6500\n\nBid: $15.20 Ask: $15.80 Last: $15.50\nOpen Interest: 12.5K\n\nTarget: Quick scalp on momentum",
    "embeds": [],
    "username": "DeMsLayer",
    "avatar_url": "https://example.com/avatar.png"
  }'

# Alternative with more realistic ATM put pricing
curl -X POST "http://localhost:8000/webhook/demslayer-spx-alerts" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "📉 SPX 6480P AUG29 SETUP\n\nCurrent SPX: 6482\nLooking for a pullback entry\n\n💰 Pricing:\nBid: $48.50\nAsk: $49.20\nLast: $48.85\nOpen Interest: 8.7K\n\n🎯 Strategy: Quick hedge play on market dip",
    "embeds": [],
    "username": "DeMsLayer", 
    "avatar_url": "https://example.com/avatar.png"
  }'

# OTM call with lower pricing for testing
curl -X POST "http://localhost:8000/webhook/demslayer-spx-alerts" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "🚀 SPX 6520C AUG29 MOMENTUM PLAY\n\nSPX @ 6482 - watching for breakout\n\n💎 Contract Details:\nStrike: 6520\nBid: $3.40\nAsk: $3.80\nLast: $3.60\nOI: 15.2K\n\n⚡ Quick momentum trade setup",
    "embeds": [],
    "username": "DeMsLayer",
    "avatar_url": "https://example.com/avatar.png"
  }'
