"""
rag/prompts.py
Modular prompt builders with optional DSPy integration.

- Domain-aware system prompts (via api.config.settings + rag.domain_config.DOMAIN_CONFIGS)
- Few-shot examples (overridable per domain config)
- Multi-turn conversation history support
- Message builders returning OpenAI-style messages for chat completion
- Optional DSPy signatures + lightweight module factories (safe if DSPy not installed)
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------------------
# Settings & domain config (safe fallbacks)
# --------------------------------------------------------------------------------------
try:
    from api.config import settings  # type: ignore
    _DOMAIN = getattr(settings, "domain", "manufacturing")
except Exception:
    class _S:
        domain = "manufacturing"
    settings = _S()  # type: ignore
    _DOMAIN = "manufacturing"

try:
    from rag.domain_config import DOMAIN_CONFIGS  # type: ignore
except Exception:
    DOMAIN_CONFIGS: Dict[str, Dict[str, Any]] = {}

_domain_prompts: Dict[str, Any] = DOMAIN_CONFIGS.get(_DOMAIN, DOMAIN_CONFIGS.get("manufacturing", {})).get("prompts", {})

# --------------------------------------------------------------------------------------
# System prompts (overridable via DOMAIN_CONFIGS[domain]["prompts"])
# --------------------------------------------------------------------------------------
REWRITER_SYSTEM_PROMPT: str = _domain_prompts.get(
    "rewriter",
    "You are a rewriter AI. Rephrase the user's question to maximize retrieval recall "
    "while preserving intent. Expand domain acronyms, normalize units, and keep it concise (<= 40 words)."
)

COMPRESSOR_SYSTEM_PROMPT: str = _domain_prompts.get(
    "compressor",
    "You are a summarizer AI. Condense the following document snippets into concise, "
    "operator-focused bullet points. Preserve page/section hints if present."
)

ANSWERER_SYSTEM_PROMPT: str = _domain_prompts.get(
    "answerer",
    "You are a domain-aware RAG assistant. Answer strictly from the provided context "
    "and avoid speculation. Keep answers practical and cite pages explicitly."
)

# --------------------------------------------------------------------------------------
# Few-shot examples (can be overridden in DOMAIN_CONFIGS[domain]["prompts"]["few_shots"])
# --------------------------------------------------------------------------------------
_FEW = _domain_prompts.get("few_shots", {}) if isinstance(_domain_prompts.get("few_shots", {}), dict) else {}

REWRITER_FEW_SHOT: List[Dict[str, str]] = _FEW.get("rewriter", [
    {"user": "What is the safety protocol for chemical spills?",
     "assistant": "Explain the chemical spill response steps from official SOPs and HSE guidance."},
    {"user": "How to reduce downtime in production?",
     "assistant": "Provide proven actions to minimize manufacturing downtime (maintenance, staffing, buffers)."},
])

COMPRESSOR_FEW_SHOT: List[Dict[str, str]] = _FEW.get("compressor", [
    {"user": "Text: 'Section 4 First Aid: eye wash 15 minutes, remove lenses, call physician ...'",
     "assistant": "- Rinse eyes 15 min; remove lenses.\n- Seek immediate medical attention.\n- Record incident and PPE used."},
])

ANSWERER_FEW_SHOT: List[Dict[str, str]] = _FEW.get("answerer", [
    {"user": "What are steps for preventive maintenance on pump X?",
     "assistant": "- Inspect seals weekly\n- Lubricate bearings per OEM interval\n- Log vibration/noise\n- Replace worn gaskets\n- Record actions"},
])

# --------------------------------------------------------------------------------------
# History serializer (accepts either {"user","assistant"} or {"question","answer"})
# --------------------------------------------------------------------------------------
def _history_to_text(conversation_history: Optional[Sequence[Dict[str, str]]]) -> str:
    if not conversation_history:
        return ""
    lines: List[str] = []
    for turn in conversation_history:
        u = turn.get("user") or turn.get("question")
        a = turn.get("assistant") or turn.get("answer")
        if u:
            lines.append(f"User: {u}")
        if a:
            lines.append(f"Assistant: {a}")
    return "\n".join(lines)

# --------------------------------------------------------------------------------------
# Prompt string builders (string form; message builders below use these)
# --------------------------------------------------------------------------------------
def rewriter_prompt(user_question: str, conversation_history: Optional[Sequence[Dict[str, str]]] = None) -> str:
    few_shot_text = "\n\n".join([f"User: {ex['user']}\nAssistant: {ex['assistant']}" for ex in REWRITER_FEW_SHOT])
    hist = _history_to_text(conversation_history)
    return (
        f"{REWRITER_SYSTEM_PROMPT}\n\n"
        f"{few_shot_text}\n\n"
        f"{hist}\n"
        f"User: {user_question}\n"
        f"Assistant:"
    ).strip()

def compressor_prompt(context_text: str, conversation_history: Optional[Sequence[Dict[str, str]]] = None) -> str:
    few_shot_text = "\n\n".join([f"User: {ex['user']}\nAssistant: {ex['assistant']}" for ex in COMPRESSOR_FEW_SHOT])
    hist = _history_to_text(conversation_history)
    return (
        f"{COMPRESSOR_SYSTEM_PROMPT}\n\n"
        f"{few_shot_text}\n\n"
        f"{hist}\n"
        f"Context:\n{context_text}\n"
        f"Summary:"
    ).strip()

def answerer_prompt(user_question: str, context_text: str, conversation_history: Optional[Sequence[Dict[str, str]]] = None) -> str:
    few_shot_text = "\n\n".join([f"User: {ex['user']}\nAssistant: {ex['assistant']}" for ex in ANSWERER_FEW_SHOT])
    hist = _history_to_text(conversation_history)
    return (
        f"{ANSWERER_SYSTEM_PROMPT}\n\n"
        f"{few_shot_text}\n\n"
        f"{hist}\n"
        f"Context:\n{context_text}\n\n"
        f"User: {user_question}\n"
        f"Assistant:"
    ).strip()

# --------------------------------------------------------------------------------------
# Message builders (OpenAI-style messages: [{"role": "...", "content": "..."}])
# --------------------------------------------------------------------------------------
def _few_shot_messages(examples: List[Dict[str, str]]) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = []
    for ex in examples:
        msgs.append({"role": "user", "content": ex["user"]})
        msgs.append({"role": "assistant", "content": ex["assistant"]})
    return msgs

def _history_messages(conversation_history: Optional[Sequence[Dict[str, str]]]) -> List[Dict[str, str]]:
    msgs: List[Dict[str, str]] = []
    if not conversation_history:
        return msgs
    for turn in conversation_history:
        u = turn.get("user") or turn.get("question")
        a = turn.get("assistant") or turn.get("answer")
        if u:
            msgs.append({"role": "user", "content": u})
        if a:
            msgs.append({"role": "assistant", "content": a})
    return msgs

def build_rewriter_messages(user_question: str, conversation_history: Optional[Sequence[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    return (
        [{"role": "system", "content": REWRITER_SYSTEM_PROMPT}]
        + _few_shot_messages(REWRITER_FEW_SHOT)
        + _history_messages(conversation_history)
        + [{"role": "user", "content": user_question}]
    )

def build_compressor_messages(context_text: str, conversation_history: Optional[Sequence[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    return (
        [{"role": "system", "content": COMPRESSOR_SYSTEM_PROMPT}]
        + _few_shot_messages(COMPRESSOR_FEW_SHOT)
        + _history_messages(conversation_history)
        + [{"role": "user", "content": f"Context:\n{context_text}\n\nSummarize into concise bullet points with page references."}]
    )

def build_answerer_messages(
    user_question: str,
    context_text: str,
    conversation_history: Optional[Sequence[Dict[str, str]]] = None,
) -> List[Dict[str, str]]:
    # NOTE: Your answerer.py adds its own rich format hint (heading + Source + bullets).
    return (
        [{"role": "system", "content": ANSWERER_SYSTEM_PROMPT}]
        + _few_shot_messages(ANSWERER_FEW_SHOT)
        + _history_messages(conversation_history)
        + [{"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {user_question}"}]
    )

# --------------------------------------------------------------------------------------
# Optional: DSPy signatures + simple factories (safe if DSPy not installed)
# --------------------------------------------------------------------------------------
_DSPY_AVAILABLE = False
try:
    import dspy  # type: ignore
    _DSPY_AVAILABLE = True
except Exception:
    _DSPY_AVAILABLE = False

if _DSPY_AVAILABLE:
    class RewriteSig(dspy.Signature):  # type: ignore
        """Rewrite the user question to maximize retrieval recall while preserving intent.
        Expand acronyms and synonyms; <= 40 words; no chit-chat.
        """
        question: str
        rewritten: str

    class CompressSig(dspy.Signature):  # type: ignore
        """Condense the following snippets into <= 8 operator-focused bullets.
        Keep page/section cues from the input.
        """
        question: str
        context_text: str
        summary: str

    class AnswerSig(dspy.Signature):  # type: ignore
        """Answer strictly from the context. Cite pages in 'Source: Doc p.N', then 6–10 detailed bullets."""
        question: str
        context_text: str
        format_hint: str
        answer: str

    class DSPyRewriter(dspy.Module):  # type: ignore
        def __init__(self):
            super().__init__()
            self.pred = dspy.Predict(RewriteSig)
        def forward(self, question: str) -> str:
            out = self.pred(question=question)
            return (getattr(out, "rewritten", "") or "").strip() or question

    class DSPyCompressor(dspy.Module):  # type: ignore
        def __init__(self):
            super().__init__()
            self.pred = dspy.Predict(CompressSig)
        def forward(self, question: str, context_text: str) -> str:
            out = self.pred(question=question, context_text=context_text)
            return (getattr(out, "summary", "") or "").strip() or context_text

    class DSPyAnswerer(dspy.Module):  # type: ignore
        def __init__(self):
            super().__init__()
            self.pred = dspy.Predict(AnswerSig)
        def forward(self, question: str, context_text: str, format_hint: str) -> str:
            out = self.pred(question=question, context_text=context_text, format_hint=format_hint)
            return (getattr(out, "answer", "") or "").strip()

    def make_dspy_modules() -> Tuple[Any, Any, Any]:
        """
        Convenience factory: returns (DSPyRewriter, DSPyCompressor, DSPyAnswerer) instances.
        If you want to configure DSPy LM here, do it before calling this function, e.g.:
            import dspy
            dspy.settings.configure(lm=dspy.OpenAI(model="gpt-4o-mini"))
        """
        return DSPyRewriter(), DSPyCompressor(), DSPyAnswerer()

else:
    # Stubs so imports don't fail when DSPy isn't installed.
    RewriteSig = CompressSig = AnswerSig = None  # type: ignore
    DSPyRewriter = DSPyCompressor = DSPyAnswerer = None  # type: ignore
    def make_dspy_modules() -> Tuple[None, None, None]:
        return None, None, None

__all__ = [
    # system prompts
    "REWRITER_SYSTEM_PROMPT", "COMPRESSOR_SYSTEM_PROMPT", "ANSWERER_SYSTEM_PROMPT",
    # few-shot
    "REWRITER_FEW_SHOT", "COMPRESSOR_FEW_SHOT", "ANSWERER_FEW_SHOT",
    # string prompts
    "rewriter_prompt", "compressor_prompt", "answerer_prompt",
    # message builders
    "build_rewriter_messages", "build_compressor_messages", "build_answerer_messages",
    # optional DSPy
    "RewriteSig", "CompressSig", "AnswerSig",
    "DSPyRewriter", "DSPyCompressor", "DSPyAnswerer", "make_dspy_modules",
]
