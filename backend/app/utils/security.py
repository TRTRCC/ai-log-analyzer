"""
Security utilities for AI Log Analyzer
"""

import hashlib
import secrets
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from functools import lru_cache

from jose import jwt, JWTError
from passlib.context import CryptContext
from cryptography.fernet import Fernet
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


# Password hashing context
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.password_hash_rounds,
)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def generate_password(length: int = 16) -> str:
    """Generate a secure random password"""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_token(length: int = 32) -> str:
    """Generate a secure random token"""
    return secrets.token_hex(length)


# JWT token utilities
def create_jwt_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    token_type: str = "access"
) -> str:
    """Create a JWT token"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        if token_type == "access":
            expire = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)
        else:
            expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_expiration_days)

    to_encode.update({
        "exp": expire,
        "type": token_type,
        "iat": datetime.utcnow(),
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def decode_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None


def verify_jwt_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """Verify a JWT token and return payload if valid"""
    payload = decode_jwt_token(token)
    if payload is None:
        return None

    if payload.get("type") != token_type:
        return None

    return payload


# Encryption utilities for sensitive data
@lru_cache()
def get_encryption_key() -> bytes:
    """Get encryption key from settings or generate one"""
    key = settings.secret_key[:32].encode()
    # Ensure key is 32 bytes for Fernet
    return hashlib.sha256(key).digest()


@lru_cache()
def get_fernet() -> Fernet:
    """Get Fernet instance for encryption"""
    key = get_encryption_key()
    # Fernet requires base64-encoded 32-byte key
    import base64
    encoded_key = base64.urlsafe_b64encode(key)
    return Fernet(encoded_key)


def encrypt_value(value: str) -> str:
    """Encrypt a string value"""
    fernet = get_fernet()
    return fernet.encrypt(value.encode()).decode()


def decrypt_value(encrypted_value: str) -> str:
    """Decrypt an encrypted string value"""
    fernet = get_fernet()
    return fernet.decrypt(encrypted_value.encode()).decode()


# File hash utilities
def calculate_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """Calculate hash of a file"""
    hash_func = hashlib.new(algorithm)

    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)

    return hash_func.hexdigest()


def calculate_string_hash(value: str, algorithm: str = "sha256") -> str:
    """Calculate hash of a string"""
    hash_func = hashlib.new(algorithm)
    hash_func.update(value.encode())
    return hash_func.hexdigest()


# Security middleware
class SecurityMiddleware(BaseHTTPMiddleware):
    """Middleware for security headers and checks"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"

        return response


# Rate limiting utilities
class RateLimiter:
    """Simple rate limiter using Redis"""

    def __init__(self, redis_client, key_prefix: str = "rate_limit"):
        self.redis = redis_client
        self.key_prefix = key_prefix

    async def is_allowed(
        self,
        identifier: str,
        max_requests: int = settings.rate_limit_requests,
        period_seconds: int = settings.rate_limit_period_seconds
    ) -> bool:
        """Check if request is allowed within rate limits"""
        key = f"{self.key_prefix}:{identifier}"

        current = await self.redis.get(key)
        if current is None:
            await self.redis.setex(key, period_seconds, 1)
            return True

        if int(current) >= max_requests:
            return False

        await self.redis.incr(key)
        return True

    async def get_remaining(
        self,
        identifier: str,
        max_requests: int = settings.rate_limit_requests,
    ) -> int:
        """Get remaining requests allowed"""
        key = f"{self.key_prefix}:{identifier}"
        current = await self.redis.get(key)
        if current is None:
            return max_requests
        return max_requests - int(current)


# Input sanitization
def sanitize_input(value: str) -> str:
    """Sanitize input to prevent XSS and injection"""
    # Remove potentially dangerous characters
    dangerous_chars = ['<', '>', '"', "'", '&', '\n', '\r', '\0']
    sanitized = value
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, '')

    # Limit length
    max_length = 10000
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized.strip()


def validate_ip_address(ip: str) -> bool:
    """Validate IP address format"""
    import ipaddress
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False