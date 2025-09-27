# Demslayer SPX Options Chain Link Fix ✅

## Issue Description
Demslayer-spx-alerts were not receiving SPX options chain links in Telegram messages despite having all the necessary data (static SPX conid 416904, strike, side information).

## Root Cause
The `LiteTelegramService.send_trading_alert()` method was ignoring the hardcoded SPX conid (416904) provided by the demslayer handler and instead attempting to look it up via API, which failed for SPX options.

## Fix Applied

### Before (Broken)
```python
# Only do IBKR conid lookup for actual alerts
conid = None
portal_url = None
primary_ticker = processed_data.get('ticker')

if is_alert and primary_ticker:
    logger.info(f"Looking up conid for ticker: {primary_ticker}")
    conid = await self.get_stock_conid(primary_ticker)  # ❌ Always lookup, ignores provided conid
```

### After (Fixed)
```python
# Only do IBKR conid lookup for actual alerts
conid = processed_data.get('conid')  # ✅ Check if conid already provided (e.g., for demslayer)
portal_url = processed_data.get('portal_url')  # ✅ Check if portal_url already provided
primary_ticker = processed_data.get('ticker')

if is_alert and primary_ticker:
    if conid:
        # ✅ Conid already provided (e.g., demslayer with hardcoded SPX conid)
        logger.info(f"Using provided conid {conid} for ticker: {primary_ticker}")
        if not portal_url:
            portal_url = self.generate_ibkr_portal_url(conid)
    else:
        # Need to lookup conid for other alerters
        conid = await self.get_stock_conid(primary_ticker)
```

## Result

### Original Message (Missing Link)
```
📝 Message:
🌟demspxslayer-and-leaps: 6655P at 2.45 @everyone Size right. Could move fast.

🔧 Lite Mode: Enhanced alert parsing enabled
```

### Fixed Message (With Options Chain Link)
```
📝 Message:
🌟demspxslayer-and-leaps: 6655P at 2.45 @everyone Size right. Could move fast.

🟢 📈 SPX - 6655P | [🔗 View on IBKR](https://www.interactivebrokers.ie/portal/?loginType=2&action=ACCT_MGMT_MAIN&clt=0&RL=1&locale=es_ES#/quote/416904/option/option.chain?source=onebar&u=false)

🔧 Lite Mode: Enhanced alert parsing enabled
```

## Technical Details

### Static SPX Conid
- **Value**: `416904` (hardcoded in `LiteDemslayerHandler`)
- **Usage**: Direct link to SPX options chain on IBKR portal
- **Why Static**: SPX conid never changes, avoids API lookup delays

### Data Flow
1. **Demslayer Handler** extracts strike/side and provides `conid: 416904`
2. **Alerter Manager** routes to Telegram service with processed_data
3. **Telegram Service** (FIXED) uses provided conid instead of lookup
4. **Portal URL Generated**: `https://www.interactivebrokers.ie/portal/...#/quote/416904/option/option.chain...`
5. **Message Formatted**: Includes parsed alert + options chain link

## Files Modified
- `app/services/lite_telegram_service.py`: Updated `send_trading_alert()` to respect provided conid

## Testing
✅ **Portal URL Generation**: Working correctly  
✅ **Message Formatting**: Includes SPX options chain link  
✅ **Demslayer Recognition**: Uses static conid 416904  
✅ **Backward Compatibility**: Other alerters still lookup conid normally  

The fix ensures demslayer SPX alerts now include direct links to the options chain for immediate trading access.
