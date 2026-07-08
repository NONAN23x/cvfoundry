from __future__ import annotations

import re
import unicodedata
from typing import Any


FILENAME_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _filename_words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return FILENAME_WORD_RE.findall(ascii_value)


def final_pdf_filename(tailored: dict[str, Any]) -> str:
    basics = tailored.get("basics", {})
    name_words = _filename_words(str(basics.get("name", "")))
    role_words = _filename_words(str(basics.get("headline", "")))
    if not name_words or not role_words:
        raise ValueError(
            "Tailored resume requires a candidate name and headline for PDF naming."
        )
    return "-".join([name_words[0], *role_words]) + ".pdf"
