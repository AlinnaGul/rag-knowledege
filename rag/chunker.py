"""
Utility functions for extracting and chunking text from PDF documents.

The ingestion pipeline uses these helpers to read PDFs into page-level text and
then split them into token-aware chunks suitable for embedding into a vector
store.  If tiktoken is not available or the model’s encoding cannot be found
the text will be split based on approximate word counts.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Dict, Any

import pypdf

try:
    import docx  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    docx = None

try:
    import tiktoken  # type: ignore
except ImportError:
    tiktoken = None  # fallback to simple splitting if not installed


def clean_text(text: str) -> str:
    """Collapse runs of whitespace for more stable embeddings."""
    return " ".join(text.split())


def extract_text_from_pdf(filepath: str) -> List[Tuple[int, str]]:
    """Extract text from a PDF file page by page.

    Returns a list of tuples containing the page number (starting at 1) and the
    text on that page.  Pages with no extractable text will return an empty
    string.
    """
    pages: List[Tuple[int, str]] = []
    reader = pypdf.PdfReader(filepath)
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append((i, clean_text(text)))
    return pages



def extract_text_from_docx(filepath: str) -> List[Tuple[int, str]]:
    """Extract text from a DOC or DOCX file as a single page."""
    if docx is None:  # pragma: no cover - handled via tests when installed
        raise RuntimeError("python-docx is required for DOC/DOCX support")
    document = docx.Document(filepath)
    texts = [p.text for p in document.paragraphs]
    text = "\n".join(texts)
    return [(1, clean_text(text))]


def extract_text_from_txt(filepath: str) -> List[Tuple[int, str]]:
    """Extract text from a plain text file as a single page."""
    text = Path(filepath).read_text(encoding="utf-8", errors="ignore")
    return [(1, clean_text(text))]


def _tokenizer_for_model(model_name: str):
    """Get a tiktoken encoding for a given model, falling back gracefully."""
    if tiktoken is None:
        return None
    try:
        return tiktoken.encoding_for_model(model_name)
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None


def chunk_pages(
    pages: List[Tuple[int, str]],
    model_name: str = "gpt-4o-mini",
    tokens_per_chunk: int = 800,
    overlap: int = 200,
) -> List[Dict[str, Any]]:
    """Split page texts into token-aware overlapping chunks.

    Each chunk is a dictionary containing the text and metadata: page number and
    a zero-padded chunk index.  Overlap ensures that context is preserved across
    chunk boundaries.  If tiktoken is not available the function falls back to
    splitting by approximate word count.
    """
    encoding = _tokenizer_for_model(model_name)
    chunks: List[Dict[str, Any]] = []
    for page_num, text in pages:
        if not text:
            continue
        if encoding:
            tokens = encoding.encode(text)
            start = 0
            chunk_id = 0
            while start < len(tokens):
                end = min(start + tokens_per_chunk, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_text = clean_text(encoding.decode(chunk_tokens))
                chunks.append({
                    "text": chunk_text,
                    "page": page_num,
                    "chunk_id": f"{page_num:04d}-{chunk_id:04d}",
                })
                chunk_id += 1
                start += tokens_per_chunk - overlap
        else:
            # Fallback splitting by words
            words = text.split()
            approx_words_per_chunk = tokens_per_chunk  # roughly assume 1 token ~ 1 word
            start = 0
            chunk_id = 0
            while start < len(words):
                end = min(start + approx_words_per_chunk, len(words))
                chunk_words = words[start:end]
                chunk_text = clean_text(" ".join(chunk_words))
                chunks.append({
                    "text": chunk_text,
                    "page": page_num,
                    "chunk_id": f"{page_num:04d}-{chunk_id:04d}",
                })
                chunk_id += 1
                start += approx_words_per_chunk - overlap
    return chunks
