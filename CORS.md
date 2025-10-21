# CORS Configuration Guide

## Overview

Cross-Origin Resource Sharing (CORS) is configured in the EM Agent Gateway to control which web applications can access the API. The configuration is **development-friendly by default** but provides security controls for production environments.

## Configuration

### Environment Variables

```bash
# CORS Origins (comma-separated list)
# Development default: "*" (allows all origins)
# Production: Set to specific domains
CORS_ALLOW_ORIGINS=["https://yourdomain.com","https://app.yourdomain.com"]

# Allow credentials (cookies, authorization headers)
CORS_ALLOW_CREDENTIALS=true

# Allowed HTTP methods
CORS_ALLOW_METHODS=["GET","POST","PUT","DELETE","PATCH","OPTIONS"]

# Allowed headers
CORS_ALLOW_HEADERS=["*"]

# Preflight cache duration in seconds (default: 600 = 10 minutes)
CORS_MAX_AGE=600
```

### Default Configuration

By default, the gateway is configured for **development convenience**:

```python
cors_allow_origins: ["*"]              # Accept requests from any origin
cors_allow_credentials: true           # Allow cookies and auth headers
cors_allow_methods: ["*"]              # Allow all HTTP methods
cors_allow_headers: ["*"]              # Allow all headers
cors_max_age: 600                      # Cache preflight for 10 minutes
```

## Security Considerations

### Development vs Production

**Development (Default):**
- `CORS_ALLOW_ORIGINS=["*"]` is acceptable for local development
- Simplifies frontend development and testing
- No security risk as services are not publicly accessible

**Production:**
- **NEVER use `"*"` in production** - this allows any website to call your API
- Always specify explicit allowed origins
- The gateway will log a security warning if `"*"` is detected in production

### Example Production Configuration

```bash
# Set environment
ENV=production

# Restrict CORS to your domains only
CORS_ALLOW_ORIGINS=["https://app.example.com","https://admin.example.com"]

# Only allow necessary methods
CORS_ALLOW_METHODS=["GET","POST","PUT","DELETE","OPTIONS"]

# Allow credentials for authenticated requests
CORS_ALLOW_CREDENTIALS=true
```

## Common Scenarios

### 1. Single Frontend Application

```bash
CORS_ALLOW_ORIGINS=["https://app.yourdomain.com"]
```

### 2. Multiple Frontends (Admin + User Portal)

```bash
CORS_ALLOW_ORIGINS=["https://app.yourdomain.com","https://admin.yourdomain.com"]
```

### 3. Different Environments

```bash
# Development
CORS_ALLOW_ORIGINS=["*"]

# Staging
CORS_ALLOW_ORIGINS=["https://staging.yourdomain.com"]

# Production
CORS_ALLOW_ORIGINS=["https://app.yourdomain.com","https://yourdomain.com"]
```

### 4. Local Development with Multiple Ports

```bash
CORS_ALLOW_ORIGINS=["http://localhost:3000","http://localhost:3001","http://localhost:8080"]
```

## Testing CORS Configuration

### Using cURL

Test a cross-origin request with a preflight check:

```bash
# Preflight request (OPTIONS)
curl -X OPTIONS http://localhost:8000/v1/health \
  -H "Origin: https://example.com" \
  -H "Access-Control-Request-Method: GET" \
  -i

# Actual request
curl http://localhost:8000/v1/health \
  -H "Origin: https://example.com" \
  -i
```

Expected headers in response:
- `Access-Control-Allow-Origin: https://example.com` (or `*`)
- `Access-Control-Allow-Credentials: true`
- `Access-Control-Allow-Methods: GET, POST, ...`

### Using Browser Console

```javascript
// Test from browser console
fetch('http://localhost:8000/v1/health', {
  method: 'GET',
  headers: {
    'Content-Type': 'application/json'
  },
  credentials: 'include'  // Test with credentials
})
  .then(response => response.json())
  .then(data => console.log('Success:', data))
  .catch(error => console.error('CORS Error:', error));
```

## Troubleshooting

### "CORS policy: No 'Access-Control-Allow-Origin' header"

**Problem:** The browser blocks the request because the origin is not allowed.

**Solutions:**
1. Add your frontend's origin to `CORS_ALLOW_ORIGINS`
2. Check that the origin matches exactly (including protocol and port)
3. Verify the gateway is using the updated configuration (restart if needed)

**Example:**
```bash
# Frontend running on http://localhost:3000
# Add this origin to CORS_ALLOW_ORIGINS
CORS_ALLOW_ORIGINS=["http://localhost:3000"]
```

### "CORS policy: Credential is not supported if the CORS header 'Access-Control-Allow-Origin' is '*'"

**Problem:** You cannot use `allow_credentials=true` with `allow_origins=["*"]` - this is a security restriction.

**Solutions:**
1. Set `CORS_ALLOW_CREDENTIALS=false` if you don't need cookies/auth headers
2. OR specify explicit origins instead of `"*"`

```bash
# Option 1: Disable credentials
CORS_ALLOW_CREDENTIALS=false

# Option 2: Use specific origins (recommended)
CORS_ALLOW_ORIGINS=["http://localhost:3000"]
CORS_ALLOW_CREDENTIALS=true
```

### "CORS policy: Method X is not allowed"

**Problem:** The HTTP method is not in the allowed methods list.

**Solution:** Add the method to `CORS_ALLOW_METHODS`:

```bash
CORS_ALLOW_METHODS=["GET","POST","PUT","DELETE","PATCH","OPTIONS"]
```

### Preflight Request Failing (OPTIONS)

**Problem:** The browser's preflight OPTIONS request is rejected.

**Solutions:**
1. Ensure `OPTIONS` is in allowed methods (usually automatic)
2. Check that headers are allowed
3. Verify `CORS_MAX_AGE` is reasonable (default: 600 seconds)

## Best Practices

### 1. Use Specific Origins in Production

❌ **Don't:**
```bash
CORS_ALLOW_ORIGINS=["*"]  # In production
```

✅ **Do:**
```bash
CORS_ALLOW_ORIGINS=["https://app.yourdomain.com","https://yourdomain.com"]
```

### 2. Only Allow Required Methods

❌ **Don't:**
```bash
CORS_ALLOW_METHODS=["*"]  # If you only need GET/POST
```

✅ **Do:**
```bash
CORS_ALLOW_METHODS=["GET","POST"]
```

### 3. Use Environment-Based Configuration

```bash
# .env.development
CORS_ALLOW_ORIGINS=["*"]

# .env.production
CORS_ALLOW_ORIGINS=["https://app.yourdomain.com"]
```

### 4. Enable Credentials Only When Needed

If you're using JWT tokens in the `Authorization` header (recommended), you need:

```bash
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_HEADERS=["Authorization","Content-Type"]
```

### 5. Set Reasonable Cache Duration

```bash
# Cache preflight for 10 minutes (default)
CORS_MAX_AGE=600

# Longer for production (1 hour)
CORS_MAX_AGE=3600
```

## Advanced Configuration

### Using Subdomain Wildcards

FastAPI's CORS middleware doesn't support wildcard subdomains directly. For `*.yourdomain.com`, you need to:

1. List all subdomains explicitly
2. OR use a custom CORS middleware with regex support

### Dynamic CORS Based on Request

For advanced use cases where CORS origins need to be determined dynamically:

```python
from starlette.middleware.cors import CORSMiddleware

# Custom allow_origin_regex parameter
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r'https://.*\.yourdomain\.com',
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### CORS with Authentication

When using JWT authentication with CORS:

```bash
# Required settings
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_HEADERS=["Authorization","Content-Type"]

# Frontend must include credentials
fetch('http://localhost:8000/v1/auth/me', {
  credentials: 'include',  // Important!
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
```

## Security Checklist

- [ ] `CORS_ALLOW_ORIGINS` does not contain `"*"` in production
- [ ] Only necessary domains are listed in allowed origins
- [ ] `CORS_ALLOW_CREDENTIALS` is `false` unless cookies/auth headers are needed
- [ ] Origins include the full URL (protocol + domain + port if non-standard)
- [ ] All origins use HTTPS in production (not HTTP)
- [ ] The gateway logs CORS configuration on startup for verification
- [ ] CORS settings are tested in all environments (dev, staging, prod)

## Monitoring

The gateway logs CORS configuration on startup:

```json
{
  "event": "cors.configured",
  "allow_origins": ["https://app.yourdomain.com"],
  "allow_credentials": true
}
```

Monitor for:
- CORS-related errors in browser console
- 403 Forbidden responses from cross-origin requests
- Excessive preflight OPTIONS requests (may indicate caching issues)

## References

- [MDN CORS Documentation](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
- [FastAPI CORS Middleware](https://fastapi.tiangolo.com/tutorial/cors/)
- [Starlette CORS Middleware](https://www.starlette.io/middleware/#corsmiddleware)
