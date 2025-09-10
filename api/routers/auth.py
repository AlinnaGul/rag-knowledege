"""
Authentication and user account endpoints.

This router exposes a login endpoint that returns a JWT access token and a
whoami endpoint that returns information about the current user.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from ..schemas import LoginRequest, LoginResponse, UserRead, PasswordChange
from ..deps import get_db, get_current_user
from ..services import auth as auth_service
from ..security import verify_password, get_password_hash
from ..security import oauth2_scheme, revoked_tokens


router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.options("/login", include_in_schema=False)
def login_options():
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/login", response_model=LoginResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user credentials and return an access token along with user info."""
    user = auth_service.authenticate_user(db, credentials.email, credentials.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = auth_service.issue_access_token(user)
    return {"token": token, "user": user}


@router.get("/me", response_model=UserRead)
def me(current_user=Depends(get_current_user)):
    """Return information about the currently authenticated user."""
    return current_user


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Allow the current user to change their password."""
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incorrect password")
    if not auth_service._valid_password(payload.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet complexity requirements",
        )
    current_user.password_hash = get_password_hash(payload.new_password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


#
# Logout endpoint
#
# The logout flow simply revokes the caller's current access token by adding it
# to an in‑memory blacklist.  Clients should clear any persisted credentials
# and consider the session invalidated on receiving a 204 response.  Note that
# this implementation does not return a response body per RFC 7231 for 204
# codes.

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_token: str = Depends(oauth2_scheme)):
    """Invalidate the caller's current JWT access token."""
    # Mark the token as revoked
    revoked_tokens.add(current_token)
    # No content returned; the FastAPI router will handle the empty body for 204
    return Response(status_code=status.HTTP_204_NO_CONTENT)
