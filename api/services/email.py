"""Stub email sending service.

Records password reset emails for testing purposes."""
from __future__ import annotations

from typing import List, Dict

sent_emails: List[Dict[str, str]] = []


def send_password_reset(email: str, token: str) -> None:
    """Record a password reset email being sent."""
    sent_emails.append({"email": email, "token": token})
