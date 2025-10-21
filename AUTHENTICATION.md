# Authentication Guide

## Overview

The EM Agent Gateway supports optional JWT (JSON Web Token) based authentication. Authentication is **disabled by default** and can be enabled via environment variables.

## Configuration

### Environment Variables

```bash
# Enable/disable authentication (default: false)
AUTH_ENABLED=true

# JWT secret key (required if AUTH_ENABLED=true)
# MUST be at least 32 characters for security
JWT_SECRET_KEY="your-super-secret-key-min-32-chars-long"

# Optional: Configure token expiration
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60  # Default: 60 minutes
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7     # Default: 7 days
JWT_ALGORITHM=HS256                  # Default: HS256
```

### Security Requirements

- `JWT_SECRET_KEY` must be at least 32 characters
- Use a cryptographically secure random string in production
- Never commit secrets to version control

**Generate a secure secret key:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## API Endpoints

### POST /v1/auth/login

Authenticate and receive JWT tokens.

**Request:**
```json
{
  "username": "user@example.com",
  "password": "your-password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### POST /v1/auth/refresh

Refresh an access token using a refresh token.

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### GET /v1/auth/me

Get current authenticated user information.

**Headers:**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response:**
```json
{
  "sub": "user@example.com",
  "email": "user@example.com",
  "role": "user"
}
```

## Using Authentication in Routes

### Require Authentication

Use the `get_current_user` dependency to require authentication:

```python
from fastapi import Depends
from ...deps import get_current_user

@router.get("/protected")
def protected_endpoint(current_user: dict = Depends(get_current_user)):
    # current_user contains: {"sub": "user@example.com", "email": "...", "role": "..."}
    return {"message": f"Hello {current_user['sub']}"}
```

### Optional Authentication

Use `get_current_user_optional` for endpoints that work with or without auth:

```python
from typing import Optional
from fastapi import Depends
from ...deps import get_current_user_optional

@router.get("/public")
def public_endpoint(current_user: Optional[dict] = Depends(get_current_user_optional)):
    if current_user:
        return {"message": f"Hello {current_user['sub']}"}
    return {"message": "Hello anonymous user"}
```

## Client Usage Examples

### Python (requests)

```python
import requests

# Login
response = requests.post("http://localhost:8000/v1/auth/login", json={
    "username": "user@example.com",
    "password": "password123"
})
tokens = response.json()
access_token = tokens["access_token"]

# Make authenticated request
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get("http://localhost:8000/v1/auth/me", headers=headers)
print(response.json())
```

### cURL

```bash
# Login
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user@example.com","password":"password123"}'

# Save token
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Make authenticated request
curl http://localhost:8000/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

### JavaScript (fetch)

```javascript
// Login
const response = await fetch('http://localhost:8000/v1/auth/login', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    username: 'user@example.com',
    password: 'password123'
  })
});
const {access_token} = await response.json();

// Make authenticated request
const userResponse = await fetch('http://localhost:8000/v1/auth/me', {
  headers: {'Authorization': `Bearer ${access_token}`}
});
const user = await userResponse.json();
console.log(user);
```

## Development Mode (Auth Disabled)

When `AUTH_ENABLED=false` (default):
- All endpoints are accessible without authentication
- `get_current_user` returns `{"sub": "anonymous", "auth_disabled": True}`
- `/v1/auth/login` returns 503 Service Unavailable
- No JWT validation occurs

This allows development without authentication complexity.

## Production Setup

### 1. Enable Authentication

```bash
export AUTH_ENABLED=true
export JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
```

### 2. Protect Sensitive Endpoints

Add authentication to routes that should be protected:

```python
@router.post("/admin/users", dependencies=[Depends(get_current_user)])
def create_user(...):
    # Only authenticated users can access
    pass
```

### 3. Implement User Management

The current implementation is a **demonstration**. For production:

1. Create a `User` model in the database
2. Store hashed passwords using `get_password_hash()`
3. Verify passwords using `verify_password()`
4. Add user roles and permissions
5. Implement user registration, password reset, etc.

**Example user model:**
```python
from services.gateway.app.core.auth import get_password_hash, verify_password

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    is_active = Column(Boolean, default=True)
```

## Security Best Practices

1. **Secret Key Management**
   - Use environment variables
   - Rotate keys periodically
   - Use different keys for dev/staging/production

2. **Token Expiration**
   - Keep access token lifetime short (15-60 minutes)
   - Use refresh tokens for longer sessions
   - Implement token revocation if needed

3. **HTTPS Only**
   - Always use HTTPS in production
   - Never send tokens over unencrypted connections

4. **Rate Limiting**
   - Limit login attempts to prevent brute force
   - Use rate limiting middleware (see RATE_LIMITING.md)

5. **Logging**
   - Log authentication attempts
   - Monitor for suspicious activity
   - Never log tokens or passwords

## Troubleshooting

### "Authentication required" but auth is disabled
- Check `AUTH_ENABLED` environment variable
- Restart the application after changing env vars

### "JWT_SECRET_KEY must be at least 32 characters"
- Generate a longer secret key
- Use `python -c "import secrets; print(secrets.token_urlsafe(32))"`

### Token expired
- Login again to get a new token
- Use refresh token to renew access token
- Adjust `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` if needed

### Invalid token signature
- Secret key mismatch between token creation and verification
- Ensure `JWT_SECRET_KEY` is consistent across restarts
- Check token wasn't tampered with
