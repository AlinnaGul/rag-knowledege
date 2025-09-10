"""
Security utilities for authentication and authorization.

This module provides password hashing with bcrypt, JWT token generation and
verification, and an OAuth2 password bearer scheme for FastAPI endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException, status, Depends
from typing import Set
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings
from .schemas import TokenData


# Password hashing context (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 bearer token extraction.  The token will be taken from the Authorization
# header as "Bearer <token>".
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# JWT configuration
SECRET_KEY = settings.jwt_secret
ALGORITHM = "HS256"

# --- Token revocation ---
#
# Maintain a simple in‑memory blacklist of JWTs that have been explicitly
# revoked via the logout endpoint.  This allows the application to reject
# requests using a token that has been invalidated.  Note that this set is
# process‑local and will reset on application restart.  For a production
# system, consider persisting revocations to a shared store or using a
# versioned token scheme.
revoked_tokens: Set[str] = set()

def is_token_revoked(token: str) -> bool:
    """Return True if the given JWT has been revoked."""
    return token in revoked_tokens


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a new JWT access token.

    The token contains the given data payload and expires after the specified
    delta (or the default from settings).  The `exp` claim is a Unix timestamp.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> TokenData:
    """Decode a JWT access token and return the contained data.

    Raises an HTTPException if the token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Reject requests with tokens that have been explicitly revoked.  This
    # prevents reuse of JWTs after the user logs out.  See `logout` in
    # api/routers/auth.py for more details.
    if is_token_revoked(token):
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: Optional[str] = payload.get("sub")  # subject is the user email
        role: Optional[str] = payload.get("role")
        if email is None or role is None:
            raise credentials_exception
        token_data = TokenData(email=email, role=role)
    except JWTError:
        raise credentials_exception
    return token_data