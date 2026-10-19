"""Undefended document reader for the Problem 5 injection test.

Same tool name, arguments, docstring, and path check as tools.read_vendor_document (Problem 3),
but with no cleanup at all:
- HTML is passed as raw source, so comments, scripts, and hidden elements reach the model.
- Emails include every text part (plain text and raw HTML), not just the plain-text part.
- PDF text is extracted without checking whether it is on the page or visible.
- Nothing is labelled as hidden, and zero-width characters are left in.
"""

import email
from email import policy
from pathlib import Path

from pypdf import PdfReader
from pydantic_ai import RunContext

from models import AgentDeps
from tools import DATA_DIR, HW_DIR


def raw_text(file: Path) -> str:
    suffix = file.suffix.lower()
    if suffix in (".html", ".htm"):
        return file.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(file).pages)
    if suffix == ".eml":
        msg = email.message_from_bytes(file.read_bytes(), policy=policy.default)
        lines = [f"{h}: {msg[h]}" for h in ("From", "To", "Subject", "Date") if msg[h]]
        for part in msg.walk():
            if part.get_content_maintype() == "text":
                lines += ["", f"--- {part.get_content_type()} part ---", part.get_content()]
        return "\n".join(lines)
    return f"[Unsupported file type: {suffix or 'none'}]"


def read_vendor_document(ctx: RunContext[AgentDeps], path: str) -> str:
    """Read a vendor document (.html, .pdf, or .eml) and return its text.

    Args:
        path: Path to the document inside the data folder, e.g. data/practice_docs/p01_bluehen_quote.html.
    """
    file = (HW_DIR / path).resolve()
    if DATA_DIR not in file.parents:
        return "Error: only documents inside the data folder can be read."
    if not file.is_file():
        return f"Error: no file found at {path}."
    return f"Document: {path}\n\n{raw_text(file)}"
