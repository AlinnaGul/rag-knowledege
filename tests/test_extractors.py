import os
import sys
from pathlib import Path

current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from rag import chunker  # type: ignore


def test_extract_text_from_txt(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("Hello\nworld")
    pages = chunker.extract_text_from_txt(str(p))
    assert pages == [(1, "Hello world")]


def test_extract_text_from_docx(tmp_path):
    p = tmp_path / "sample.docx"
    import docx  # type: ignore

    doc = docx.Document()
    doc.add_paragraph("Hello from docx")
    doc.save(str(p))

    pages = chunker.extract_text_from_docx(str(p))
    assert pages == [(1, "Hello from docx")]
