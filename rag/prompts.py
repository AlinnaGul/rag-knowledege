"""Prompt templates used in the RAG pipeline."""

from api.config import settings
from rag.domain_config import DOMAIN_CONFIGS

_prompts = DOMAIN_CONFIGS.get(settings.domain, DOMAIN_CONFIGS["manufacturing"]).get("prompts", {})

# System prompt for rewriting the user's question to maximize retrieval recall.
REWRITER_SYSTEM_PROMPT = _prompts.get("rewriter", "")

# System prompt for compressing long context into concise bullet points.
COMPRESSOR_SYSTEM_PROMPT = _prompts.get("compressor", "")

# System prompt for grounded answering.
ANSWERER_SYSTEM_PROMPT = _prompts.get("answerer", "")
