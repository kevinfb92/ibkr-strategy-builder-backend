# IBKR Account Configuration

## Overview
The IBKR Strategy Builder Backend now supports configuring a preferred IBKR account ID through environment variables. This is useful when you have multiple IBKR accounts and want to ensure the system uses a specific one.

## Configuration

### Option 1: Automatic Account Detection (Default)
If no preferred account is configured, the system will automatically use the first available account from your IBKR login.

### Option 2: Specify Preferred Account
To use a specific IBKR account:

1. **Edit the `.env` file** in the project root
2. **Set the IBKR_ACCOUNT_ID** to your desired account:
   ```env
   IBKR_ACCOUNT_ID=YOUR_ACCOUNT_ID_HERE
   ```
3. **Restart the application** for changes to take effect

## Finding Your Account ID

Your IBKR account ID can be found:
- In IBKR TWS: Account menu → Account Information
- In IBKR Client Portal: Login and check the account dropdown
- From the backend logs: Look for "Using first available IBKR account: [ID]" messages

## Environment Variables

Complete IBKR configuration in `.env`:

```env
# IBKR Configuration  
IBKR_GATEWAY_URL=https://localhost:5000/v1/api

# Optional: Specify a preferred IBKR account ID if you have multiple accounts
# If not specified, the system will use the first available account
# Example: IBKR_ACCOUNT_ID=U1234567
IBKR_ACCOUNT_ID=

# Temporarily disable WebSocket to stop connection loop
IBKR_WS_DISABLE=0
```

## How It Works

1. **At startup**, the IBKR service checks for the `IBKR_ACCOUNT_ID` environment variable
2. **If configured**, it searches through available accounts for a match
3. **If found**, it uses the specified account and logs: "Using preferred IBKR account: [ID]"
4. **If not found**, it warns: "Preferred IBKR account '[ID]' not found" and falls back to the first available
5. **If not configured**, it uses the first available account and logs: "Using first available IBKR account: [ID]"

## Benefits

- **Multiple Account Support**: Easily switch between different IBKR accounts
- **Deterministic Behavior**: Ensures consistent account usage across restarts
- **Fallback Safety**: Automatically uses first available account if preferred isn't found
- **Zero Breaking Changes**: Existing setups continue working without modification

## Security

✅ **Account IDs are NOT hardcoded** in the source code
✅ **Environment variables** keep sensitive data out of the repository
✅ **Automatic detection** works for single-account setups
✅ **Clear logging** shows which account is being used

## Troubleshooting

### Warning: "Preferred IBKR account not found"
- Check that the account ID in `.env` matches exactly (case-sensitive)
- Verify the account is accessible from your IBKR login
- Check IBKR TWS/Client Portal for correct account ID format

### No Account Detected
- Ensure IBKR Gateway is running and authenticated
- Check 2FA authentication is completed
- Verify IBKR credentials are correct

### Multiple Accounts Available
- Check application logs for "available accounts" information
- Use exact account ID format shown in logs
- Test without IBKR_ACCOUNT_ID first to see available options