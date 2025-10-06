# API Authentication Setup

This backend now includes simple password-based authentication for all API endpoints.

## Configuration

### 1. Set API Password
Add your API password to the `.env` file:

```env
# API Authentication
API_PASSWORD=your-secure-password-here
```

### 2. Development Mode
If `API_PASSWORD` is not set, authentication is **disabled** and all requests are allowed. This is useful for development but should never be used in production.

## Usage

### Making Authenticated Requests
Include the `X-API-Key` header with your password in all API requests:

```bash
# Using curl
curl -H "X-API-Key: your-secure-password-here" \
     http://localhost:8000/api/accounts

# Using Python requests
import requests
headers = {"X-API-Key": "your-secure-password-here"}
response = requests.get("http://localhost:8000/api/accounts", headers=headers)
```

### Public Endpoints (No Authentication Required)
These endpoints are accessible without authentication:
- `/health` - Health check
- `/docs` - API documentation
- `/openapi.json` - OpenAPI specification
- `/redoc` - Alternative API documentation
- `/ws/*` - WebSocket endpoints

### Protected Endpoints
All other endpoints require the `X-API-Key` header:
- `/api/*` - All API endpoints
- `/penny-stock/*` - Penny stock monitoring
- `/internal/*` - Internal system endpoints

## Error Responses

### Missing API Key (401)
```json
{
  "error": "Unauthorized",
  "message": "X-API-Key header is required"
}
```

### Invalid API Key (401)
```json
{
  "error": "Unauthorized", 
  "message": "Invalid API key"
}
```

## Frontend Integration

### React/JavaScript Example
```javascript
// Set up axios with default headers
import axios from 'axios';

const apiClient = axios.create({
  baseURL: 'http://localhost:8000',
  headers: {
    'X-API-Key': 'your-secure-password-here'
  }
});

// Use as normal
const response = await apiClient.get('/api/accounts');
```

### Fetch API Example
```javascript
const response = await fetch('http://localhost:8000/api/accounts', {
  headers: {
    'X-API-Key': 'your-secure-password-here'
  }
});
```

## Testing

Run the included test script to verify authentication is working:

```bash
python test_auth.py
```

**Note**: All test files in the `/tests/` directory have been updated to include authentication headers automatically.

To run individual test files:
```bash
# Run all notification tests
python -m pytest tests/notifications/

# Run a specific test
python tests/notifications/test_notifications.py
```

## Security Notes

1. **Use HTTPS in production** - Never send passwords over unencrypted HTTP
2. **Choose a strong password** - Use a long, random password
3. **Keep credentials secret** - Never commit real passwords to version control
4. **Rotate regularly** - Change the password periodically
5. **Monitor access** - Check logs for unauthorized access attempts

## Troubleshooting

### Authentication Not Working
1. Verify `API_PASSWORD` is set in `.env`
2. Check the header name is exactly `X-API-Key` (case-sensitive)
3. Ensure no extra spaces in the password value
4. Restart the server after changing `.env`

### Still Getting 401 Errors
1. Check server logs for authentication attempts
2. Verify the password matches exactly (no trailing newlines)
3. Test with a simple curl command first
4. Make sure you're not hitting a public endpoint by mistake

### Performance Impact
The middleware adds minimal overhead (~1ms per request) and runs before all other processing, so failed authentication requests are rejected quickly.