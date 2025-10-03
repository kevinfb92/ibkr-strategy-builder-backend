# SPY/SPX 0DTE Expiry Fix

## Problem
SPY and SPX option alerts were defaulting to next Friday expiry (e.g., 10/10/2025) instead of 0DTE (same day expiry, e.g., 10/03/2025) when no expiry date was explicitly mentioned in the alert message.

## Root Cause
The `LiteRobinDaHoodHandler` was calling `_extract_expiry(message, strike_pos)` without passing the `ticker` parameter. This caused the function to use the default Friday logic for all tickers instead of the special 0DTE logic for SPY/SPX.

## Fix Applied
Modified `LiteRobinDaHoodHandler._process_buy_alert()` in `app/services/handlers/lite_handlers.py`:

**Before:**
```python
expiry = _extract_expiry(message, strike_pos)
```

**After:**
```python
expiry = _extract_expiry(message, strike_pos, ticker)
```

## Logic in `_extract_expiry()` Function

The function now properly implements:

1. **Explicit Date Found**: If message contains MM/DD format date, use it
2. **SPY/SPX Default**: If ticker is SPY or SPX and no expiry found, default to 0DTE (current date)  
3. **Other Tickers Default**: If other ticker and no expiry found, default to next Friday

```python
if ticker and ticker.upper() in ['SPY', 'SPX']:
    # SPY/SPX: Default to 0DTE (same day expiry)
    current_date = datetime.now().strftime("%m/%d/%Y")
    return current_date
else:
    # Other tickers: Default to closest Friday
    # ... Friday calculation logic
```

## Verification Tests

Created test scripts that confirm:

- **SPY Alert Without Expiry**: Defaults to 10/03/2025 (0DTE) ✅
- **SPX Alert Without Expiry**: Defaults to 10/03/2025 (0DTE) ✅  
- **Other Ticker Without Expiry**: Defaults to 10/10/2025 (Friday) ✅

## Impact

- All SPY option alerts will now use same-day expiry (0DTE) by default
- All SPX option alerts will now use same-day expiry (0DTE) by default  
- Other ticker alerts continue to use next Friday expiry by default
- Explicit expiry dates in alert messages are still respected

## Files Modified

1. `app/services/handlers/lite_handlers.py` - Fixed robindahood handler
2. `test_spy_0dte.py` - SPY verification test
3. `test_spx_0dte.py` - SPX verification test

## Testing

Run the test scripts to verify the fix:

```bash
python test_spy_0dte.py
python test_spx_0dte.py
```

Both should show "✅ SPY/SPX correctly defaults to 0DTE".