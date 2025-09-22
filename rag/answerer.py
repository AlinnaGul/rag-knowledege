"""
Functions for orchestrating the RAG pipeline and generating answers.

This module contains helpers to rewrite the user's question, compress context if
needed, and call OpenAI’s Chat Completions API (v1 client) to produce a grounded
answer along with citations.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

# rag/answerer.py
# =============================================================================
# Concise RAG answerer with OPTIONAL DSPy.
# - If the question asks for table/compare → return ONLY a clean Markdown table
#   (headers + up to 5 rows), no extra text.
# - Otherwise → short direct answer (1–4 bullets or a tight paragraph).
# - Optional DSPy: set DSPY_USE=1 and have OPENAI_API_KEY to enable.
# - API: generate_answer(question, results, config=SynthesisConfig(...), llm=None)
# - Returns: {"answer": str, "citations": list, "latency_ms": int, ...}
# =============================================================================
from __future__ import annotations

import os
import re
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Iterable

# -----------------------------------------------------------------------------
# Behavior switches
# -----------------------------------------------------------------------------
_TABLE_TRIGGERS = (
    "table", "tabular", "tabulated", "comparison", "compare", "vs", "versus",
    "side-by-side", "side by side", "compare:", "comparison:"
)

def _wants_table(question: str) -> bool:
    q = (question or "").lower()
    return any(t in q for t in _TABLE_TRIGGERS)

# -----------------------------------------------------------------------------
# Config (kept compatible with your app.py)
# -----------------------------------------------------------------------------
@dataclass
class SynthesisConfig:
    strategies: List[str] | None = None
    temperature: float = 0.1
    max_tokens: int = 200
    max_bullets: int = 4
    max_bullet_length: int = 120
    # present for compatibility with app.py (not heavily used here)
    handle_multimodal: bool = True
    preserve_table_data: bool = True
    preserve_chart_data: bool = False

# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------
def _clean_text(s: str, max_len: int = 400) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s

def _first_sentences(text: str, max_chars: int = 500) -> str:
    text = _clean_text(text, max_len=max_chars)
    parts = re.split(r"(?<=[.!?])\s+", text)
    out: List[str] = []
    for p in parts:
        if not p:
            continue
        out.append(p.strip())
        if len(" ".join(out)) > max_chars or len(out) >= 3:
            break
    return " ".join(out)

def _topk_texts(results: Iterable[Any], k: int = 3) -> List[str]:
    items: List[str] = []
    for r in results:
        txt = getattr(r, "text", None)
        if not txt and isinstance(r, dict):
            txt = r.get("text")
        if txt:
            items.append(txt)
        if len(items) >= k:
            break
    return items

def _collect_citations(results: Iterable[Any], max_items: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in results:
        md = getattr(r, "metadata", None)
        if not md and isinstance(r, dict):
            md = r.get("metadata") or {}
        if isinstance(md, dict):
            out.append({
                "document_id": md.get("document_id") or md.get("doc_id"),
                "page": md.get("page"),
                "source": md.get("source") or md.get("filename") or md.get("url") or md.get("title"),
                "score": getattr(r, "score", None) if not isinstance(r, dict) else r.get("score"),
            })
        if len(out) >= max_items:
            break
    return out

# -----------------------------------------------------------------------------
# Table rendering
# -----------------------------------------------------------------------------
class TableSpec(dict):
    """Simple container: {"headers": List[str], "rows": List[List[str]]}"""
    @property
    def headers(self) -> List[str]: return self.get("headers", [])
    @property
    def rows(self) -> List[List[str]]: return self.get("rows", [])

def _from_generated_table(obj: Any) -> Optional[TableSpec]:
    """
    Accepts dict or JSON string in {"headers":[...], "rows":[[...], ...]} format.
    """
    if not obj:
        return None
    try:
        data = json.loads(obj) if isinstance(obj, str) else obj
        headers = data.get("headers") or []
        rows = data.get("rows") or []
        if isinstance(headers, list) and isinstance(rows, list) and headers and rows:
            # coerce to strings
            clean_rows: List[List[str]] = []
            for row in rows[:5]:
                clean_rows.append([_clean_text(str(c), 200) for c in row])
            return TableSpec(headers=[str(h) for h in headers], rows=clean_rows)
    except Exception:
        return None
    return None

def _guess_table_from_results(results: List[Any], max_rows: int = 5) -> Optional[TableSpec]:
    """
    Build a small, useful table when no structured table is present.
    Strategy:
      1) If chunk metadata has common keys (title/section/key/value), build 2-col table.
      2) Else, split top texts into short 'Item' + 'Summary' rows.
    """
    # 1) metadata key/value
    kv_rows: List[List[str]] = []
    for r in results:
        md = getattr(r, "metadata", None) or (r.get("metadata") if isinstance(r, dict) else {})
        if not isinstance(md, dict):
            continue
        key_candidates = []
        for k in ("title", "heading", "section", "name", "label", "key"):
            if md.get(k): key_candidates.append(str(md.get(k)))
        key = key_candidates[0] if key_candidates else None
        value = md.get("value") or md.get("summary") or md.get("topic")
        if key and value:
            kv_rows.append([_clean_text(key, 60), _clean_text(str(value), 160)])
        if len(kv_rows) >= max_rows:
            break
    if kv_rows:
        return TableSpec(headers=["Item", "Value"], rows=kv_rows)

    # 2) fallback from text
    texts = _topk_texts(results, k=max_rows)
    if not texts:
        return None
    rows: List[List[str]] = []
    for i, t in enumerate(texts, 1):
        rows.append([f"Item {i}", _first_sentences(t, max_chars=180)])
    return TableSpec(headers=["Item", "Summary"], rows=rows)

def _render_markdown_table(spec: TableSpec) -> str:
    headers = spec.headers
    rows = spec.rows
    md = []
    md.append("| " + " | ".join(headers) + " |")
    md.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        cells = [_clean_text(c, 200) for c in row]
        md.append("| " + " | ".join(cells) + " |")
    return "\n".join(md)

# -----------------------------------------------------------------------------
# OPTIONAL DSPy (behind DSPY_USE=1)
# -----------------------------------------------------------------------------
_DSPY_ENABLED = False
try:
    # Only enable if env flag is set AND an OpenAI key is available
    if os.getenv("DSPY_USE", "").lower() in ("1", "true", "yes") and os.getenv("OPENAI_API_KEY", ""):
        import dspy  # type: ignore
        # Choose a sensible default model; override via OPENAI_MODEL if desired
        _model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        dspy.configure(lm=dspy.OpenAI(model=_model_name, max_tokens=512))
        _DSPY_ENABLED = True
except Exception:
    _DSPY_ENABLED = False

if _DSPY_ENABLED:
    import dspy  # type: ignore

    class RewriteSig(dspy.Signature):  # type: ignore
        """Rewrite the user question to maximize retrieval recall while preserving intent (≤ 40 words)."""
        question: str = dspy.InputField()
        rewritten: str = dspy.OutputField()

    class CompressSig(dspy.Signature):  # type: ignore
        """Condense context into <= 6 short bullets (≤ 120 chars each), no filler, keep concrete facts."""
        question: str = dspy.InputField()
        context_text: str = dspy.InputField()
        summary: str = dspy.OutputField()

    class AnswerSig(dspy.Signature):  # type: ignore
        """Answer strictly from context in 2–4 short bullets (≤120 chars each). No preface, no extra lines."""
        question: str = dspy.InputField()
        context_text: str = dspy.InputField()
        answer: str = dspy.OutputField()

    class DSPyRewriter(dspy.Module):  # type: ignore
        def __init__(self): super().__init__(); self.pred = dspy.Predict(RewriteSig)
        def forward(self, question: str) -> str:
            out = self.pred(question=question)
            return (getattr(out, "rewritten", "") or "").strip() or question

    class DSPyCompressor(dspy.Module):  # type: ignore
        def __init__(self): super().__init__(); self.pred = dspy.Predict(CompressSig)
        def forward(self, question: str, context_text: str) -> str:
            out = self.pred(question=question, context_text=context_text)
            return (getattr(out, "summary", "") or "").strip() or context_text

    class DSPyAnswerer(dspy.Module):  # type: ignore
        def __init__(self): super().__init__(); self.pred = dspy.Predict(AnswerSig)
        def forward(self, question: str, context_text: str) -> str:
            out = self.pred(question=question, context_text=context_text)
            return (getattr(out, "answer", "") or "").strip()

    _DSPY_MODULES = None  # lazy init
    def _get_dspy_modules():
        global _DSPY_MODULES
        if _DSPY_MODULES is None:
            _DSPY_MODULES = (DSPyRewriter(), DSPyCompressor(), DSPyAnswerer())
        return _DSPY_MODULES

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def rewrite_question(question: str) -> str:
    """Optional DSPy rewrite; otherwise a no-op."""
    try:
        if _DSPY_ENABLED:
            rw, _, _ = _get_dspy_modules()
            return rw.forward(question=question)
        return (question or "").strip()
    except Exception:
        return (question or "").strip()

def _contexts_as_text(results: List[Any], max_chunks: int = 6) -> str:
    """
    Build a light 'context' string. We avoid heavy formatting so the answer stays concise.
    """
    parts: List[str] = []
    for r in results[:max_chunks]:
        txt = getattr(r, "text", None)
        if not txt and isinstance(r, dict):
            txt = r.get("text", "")
        md = getattr(r, "metadata", None)
        if not md and isinstance(r, dict):
            md = r.get("metadata") or {}
        page = (md or {}).get("page")
        page_str = f"p.{page}" if page is not None else "p.?"
        if txt:
            parts.append(f"[{page_str}] {txt}")
    return "\n\n".join(parts)

def generate_answer(
    question: str,
    results: List[Any],
    *,
    llm: Optional[Any] = None,                # kept for compatibility; not used here
    runner: Optional[Any] = None,             # compatibility no-op
    config: Optional[SynthesisConfig] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Compose a short, clean answer from retrieved chunks.
    - Table/compare requests → ONLY Markdown table in 'answer' (and 'generated_table' echo for UI).
    - Otherwise → concise bullets (2–4).
    """
    t0 = time.time()
    cfg = config or SynthesisConfig()
    results = results or []

    # Citations (small)
    citations = _collect_citations(results)

    # 1) TABLE PATH (hard requirement: no extra text)
    if _wants_table(question):
        # if retriever already produced a structured table, use it
        for r in results:
            # object or dict
            maybe_table = getattr(r, "generated_table", None)
            if maybe_table is None and isinstance(r, dict):
                maybe_table = r.get("generated_table")
            spec = _from_generated_table(maybe_table)
            if spec:
                md_table = _render_markdown_table(spec)
                latency_ms = int((time.time() - t0) * 1000)
                return {
                    "answer": md_table,
                    "generated_table": {"headers": spec.headers, "rows": spec.rows},
                    "citations": citations,
                    "latency_ms": latency_ms,
                    "output_mode": "table",
                    "is_multimodal": True,
                    "confidence": 0.9,
                }

        # else build a small table from results
        spec2 = _guess_table_from_results(results, max_rows=5)
        if spec2 and spec2.rows:
            md_table = _render_markdown_table(spec2)
        else:
            # last resort: empty placeholder table
            md_table = "| Item | Value |\n| --- | --- |\n| No data | — |"

        latency_ms = int((time.time() - t0) * 1000)
        return {
            "answer": md_table,
            "generated_table": {"headers": spec2.headers if spec2 else ["Item", "Value"],
                                "rows": spec2.rows if spec2 else [["No data", "—"]]},
            "citations": citations,
            "latency_ms": latency_ms,
            "output_mode": "table",
            "is_multimodal": True,
            "confidence": 0.85,
        }

    # 2) TEXT PATH (concise)
    texts = _topk_texts(results, k=3)

    if not texts:
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "answer": "I couldn’t find relevant indexed content to answer this yet.",
            "citations": citations,
            "latency_ms": latency_ms,
            "output_mode": "text",
            "is_multimodal": False,
            "confidence": 0.2,
        }

    # Optional DSPy summarize/answer
    concise_answer: Optional[str] = None
    if _DSPY_ENABLED:
        try:
            _, dspy_comp, dspy_ans = _get_dspy_modules()
            ctx_text = _contexts_as_text(results, max_chunks=6)
            # compress → answer
            compressed = dspy_comp.forward(question=question, context_text=ctx_text) or ctx_text
            concise_answer = dspy_ans.forward(question=question, context_text=compressed)
        except Exception:
            concise_answer = None

    if not concise_answer:
        # deterministic concise bullets (no DSPy)
        bullets: List[str] = []
        for txt in texts:
            snippet = _first_sentences(txt, max_chars=min(220, cfg.max_bullet_length))
            if snippet and snippet not in bullets:
                bullets.append(snippet)
            if len(bullets) >= max(2, min(4, cfg.max_bullets)):
                break
        if len(bullets) == 1:
            concise_answer = bullets[0]
        else:
            concise_answer = "\n".join(f"- {b}" for b in bullets)

    latency_ms = int((time.time() - t0) * 1000)
    return {
        "answer": concise_answer,
        "citations": citations,
        "latency_ms": latency_ms,
        "output_mode": "text",
        "is_multimodal": False,
        "confidence": 0.7 if _DSPY_ENABLED else 0.5,
    }

# (Optional) tiny helpers kept for compatibility with older codebases
def detect_output_mode(contexts: List[Dict[str, Any]] | List[Any]) -> str:
    for c in contexts or []:
        gt = getattr(c, "generated_table", None)
        if gt is None and isinstance(c, dict):
            gt = c.get("generated_table")
        if gt:
            return "table"
    return "text"

def get_multimodal_summary(contexts: List[Dict[str, Any]] | List[Any]) -> Dict[str, Any]:
    has_table = False
    for c in contexts or []:
        if (getattr(c, "generated_table", None) is not None) or (isinstance(c, dict) and c.get("generated_table")):
            has_table = True
            break
    return {"has_tables": has_table, "has_charts": False, "table_count": 1 if has_table else 0,
            "chart_count": 0, "output_modes": ["table"] if has_table else ["text"], "is_multimodal": has_table}

__all__ = ["generate_answer", "SynthesisConfig", "rewrite_question",
           "detect_output_mode", "get_multimodal_summary"]
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
