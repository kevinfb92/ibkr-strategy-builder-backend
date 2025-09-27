#!/usr/bin/env python3
"""Simulate Telegram callback flow without starting the real bot.

This script creates a fake pending message in the global `telegram_service` and
calls the internal handlers that are normally invoked when buttons are pressed.
It prints the edited message HTML and the reply_markup structure.

Run with:
C:/Users/kevin/Desktop/trading/stoqey/ibkr-strategy-builder-backend/.venv/Scripts/python.exe tools/simulate_callback.py
"""
import asyncio
import json
import sys
import os
from datetime import datetime

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.telegram_service import telegram_service


class MockReplyMarkup:
    def __init__(self, keyboard):
        self.keyboard = keyboard

    def __repr__(self):
        return f"MockReplyMarkup({self.keyboard})"


class MockQuery:
    def __init__(self):
        self.last_edit = None

    async def edit_message_text(self, text=None, reply_markup=None, parse_mode=None):
        self.last_edit = {
            'text': text,
            'reply_markup': repr(reply_markup) if reply_markup is not None else None,
            'parse_mode': parse_mode
        }
        print("--- edit_message_text called ---")
        print(f"parse_mode: {parse_mode}")
        print("text:\n", text)
        print("reply_markup:\n", reply_markup)
        print("-------------------------------\n")
        return self.last_edit


async def run_simulation():
    # Prepare a fake message id
    message_id = 'sim1234'

    # Create processed_data similar to Real Day Trading with IBKR fields
    processed_data = {
        'action': 'LONG',
        'instrument_type': 'STOCK',
        'ticker': 'TSLA',
        'ibkr_position_size': 3,
        'ibkr_unrealized_pnl': -573.04,
        'ibkr_realized_pnl': 0.0,
        'ibkr_market_value': 567.0,
        'ibkr_avg_price': 3.80014785,
        'ibkr_current_price': 1.89,
        # no option_contracts in storage to force IBKR fallback in regeneration
    }

    message_info = {
        'alerter': 'Real Day Trading',
        'original_message': 'TSLA green !!',
        'ticker': 'TSLA',
        'additional_info': 'Layer Trading Signal',
        'processed_data': processed_data,
        'timestamp': datetime.now().isoformat(),
        'response': None,
        'quantity': 1,
        'has_position': True,
        'max_position': 3,
    }

    telegram_service.pending_messages[message_id] = message_info

    mock_query = MockQuery()

    print("Simulating quantity +1 (open) adjustment...\n")
    await telegram_service._handle_quantity_adjustment(mock_query, message_id, +1)

    print("Simulating close quantity +1 adjustment...\n")
    await telegram_service._handle_close_quantity_adjustment(mock_query, message_id, +1)
    
    # Now simulate pressing the Close Position button which triggers execute_close
    print("Simulating pressing Close Position (execute_close callback)...)\n")
    # Create a fake callback data object similar to telegram CallbackQuery
    class FakeCallback:
        def __init__(self, data):
            self.data = data
            self.message = None
        async def edit_message_text(self, text=None, reply_markup=None, parse_mode=None):
            return await mock_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        async def answer(self, text=None):
            # no-op
            return None

    fake_cb = FakeCallback(f"execute_close:{message_id}")
    await telegram_service.handle_button_callback(fake_cb)


if __name__ == '__main__':
    asyncio.run(run_simulation())
