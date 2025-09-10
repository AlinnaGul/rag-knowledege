"""Simple moderation helpers for user questions and answers."""
from __future__ import annotations

from openai import OpenAI
from api.config import settings
from rag.domain_config import DOMAIN_CONFIGS

client = OpenAI(api_key=settings.openai_api_key)

_guard = DOMAIN_CONFIGS.get(settings.domain, DOMAIN_CONFIGS["manufacturing"]).get("guardrails", {})

# Standard message returned when content is deemed unsafe
DEFAULT_REFUSAL = _guard.get("default_refusal", "I'm sorry, but I can't help with that request.")

def is_safe(text: str) -> bool:
    """Return True if the text passes OpenAI's moderation check."""
    try:
        resp = client.moderations.create(
            model="omni-moderation-latest", input=text
        )
        return not resp.results[0].flagged  # type: ignore[index]
    except Exception:
        # If moderation call fails, err on the side of allowing
        return True


def safe_response(text: str) -> str:
    """Return text if safe, otherwise a standard refusal message."""
    return text if is_safe(text) else DEFAULT_REFUSAL

