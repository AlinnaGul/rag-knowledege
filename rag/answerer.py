"""
Functions for orchestrating the RAG pipeline and generating answers.

This module contains helpers to rewrite the user's question, compress context if
needed, and call OpenAI’s Chat Completions API (v1 client) to produce a grounded
answer along with citations.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from openai import OpenAI
from api.config import settings  # absolute import

from .prompts import (
    REWRITER_SYSTEM_PROMPT,
    COMPRESSOR_SYSTEM_PROMPT,
    ANSWERER_SYSTEM_PROMPT,
)

# Single shared client
client = OpenAI(api_key=settings.openai_api_key)


def _safe_label(meta: Dict[str, Any]) -> str:
    """Build a stable citation label like [Title p.N]."""
    title = (meta or {}).get("title") or "Doc"
    page = (meta or {}).get("page")
    try:
        # handle str/int/None
        page_str = f"{int(page)}" if page is not None else "?"
    except Exception:
        page_str = "?"
    return f"[{title} p.{page_str}]"


def rewrite_question(question: str) -> str:
    """Use the rewriter prompt to improve the user's question for retrieval."""
    messages = [
        {"role": "system", "content": REWRITER_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.0,
            max_tokens=64,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        # Fall back to the original question if the API call fails
        import logging

        logging.getLogger(__name__).exception("Question rewrite failed: %s", exc)
        return question


def compress_context(question: str, contexts: List[Dict[str, Any]]) -> str:
    """Optionally compress context into bullet points using an LLM.

    If the combined context is short, return the concatenation directly.
    Otherwise, call the compressor prompt while preserving citation labels.
    """
    # Build a single string of snippets with separators and citation labels
    snippets: List[str] = []
    for c in contexts:
        meta = c.get("metadata", {}) or {}
        text = c.get("text") or ""
        label = _safe_label(meta)
        snippets.append(f"{label} {text}")
    full_context = "\n\n".join(snippets)

    # If context is short enough, skip compression
    if len(full_context.split()) < 1500:
        return full_context

    messages = [
        {"role": "system", "content": COMPRESSOR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Question:\n{question}\n\nContext:\n{full_context}",
        },
    ]
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.0,
            max_tokens=512,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).exception("Context compression failed: %s", exc)
        # Fallback: return the uncompressed context
        return full_context


def _rank_dedupe(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate and sort citations by score."""
    dedup: Dict[tuple[int, int], Dict[str, Any]] = {}
    for cit in citations:
        key = (cit["doc_id"], cit["page"])
        if key not in dedup or cit["score"] > dedup[key]["score"]:
            dedup[key] = cit
    ordered = sorted(dedup.values(), key=lambda x: x["score"], reverse=True)
    for cit in ordered:
        cit["id"] = cit.get("chunk_id") or f"{cit['doc_id']}:{cit['page']}"
        cit["filename"] = cit.pop("title")
        cit["url"] = None
        cit["section"] = None
    return ordered


def generate_answer(
    question: str,
    contexts: List[Dict[str, Any]],
    temperature: float | None = None,
    history: List[Dict[str, str]] | None = None,
) -> Dict[str, Any]:
    """Generate an answer to the question using the provided contexts.

    Returns:
        dict: {
            "answer": str,
            "citations": List[{doc_id,title,page,chunk_id,score}],
            "latency_ms": int
        }
    """
    # Concatenate context with labels for citations
    context_string = "\n\n".join(
        f"{_safe_label(c.get('metadata', {}) or {})} {c.get('text') or ''}"
        for c in contexts
    )

    messages = [
        {"role": "system", "content": ANSWERER_SYSTEM_PROMPT}
    ]
    if history:
        for turn in history:
            messages.append({"role": "user", "content": turn["question"]})
            messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append(
        {
            "role": "user",
            "content": f"Context:\n{context_string}\n\nQuestion: {question}",
        }
    )

    start = time.time()
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=temperature if temperature is not None else settings.answer_temperature,
            max_tokens=512,
        )
        latency_ms = int((time.time() - start) * 1000)
        answer_text = (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).exception("Answer generation failed: %s", exc)
        latency_ms = int((time.time() - start) * 1000)
        answer_text = "I'm sorry, I'm unable to answer your question at the moment."

    intro = "Here is a brief overview before the detailed steps:\n\n"
    answer_text = f"{intro}{answer_text}"

    # Build citations list from metadata (preserve score if the retriever provided it)
    citations: List[Dict[str, Any]] = []
    for c in contexts:
        meta = c.get("metadata", {}) or {}
        doc_id = meta.get("doc_id") or meta.get("document_id") or 0
        title = meta.get("title") or "Document"
        page = meta.get("page")
        if page is None:
            page = 0
        chunk_id = meta.get("chunk_id") or ""
        collection_name = meta.get("collection_name") or f"Collection {meta.get('collection_id', '')}"
        citations.append(
            {
                "doc_id": doc_id,
                "title": title,
                "page": page,
                "chunk_id": chunk_id,
                "score": c.get("score", 0.0),
                "collection_id": meta.get("collection_id", 0),
                "collection_name": collection_name,
                "snippet": c.get("text", ""),
            }
        )

    ordered = _rank_dedupe(citations)
    return {"answer": answer_text, "citations": ordered, "latency_ms": latency_ms}
