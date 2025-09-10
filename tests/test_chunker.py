"""
Unit tests for the chunker utility functions.

These tests ensure that the chunker preserves page metadata and produces
non-empty chunks.  The test manipulates sys.path at runtime to import the
module from the project directory.
"""
import os
import sys

# Add the project root to sys.path so we can import the rag package.  The
# directory structure uses a hyphen in the name (data-nucleus) which is not a valid
# Python identifier, so we append the path directly.
current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from rag import chunker  # type: ignore  # noqa: E402


def test_chunker_preserves_page_and_chunk_id():
    text = "This is a test sentence. " * 200
    pages = [(1, text), (2, text)]
    chunks = chunker.chunk_pages(pages, tokens_per_chunk=50, overlap=10)
    page_nums = {c["page"] for c in chunks}
    assert page_nums == {1, 2}
    for c in chunks:
        assert c["chunk_id"].startswith(f"{c['page']:04d}")


def test_clean_text_collapses_whitespace():
    dirty = "A   line\nwith\tmixed   spacing"
    assert chunker.clean_text(dirty) == "A line with mixed spacing"
