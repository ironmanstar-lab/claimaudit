"""Local text adapter — audit a transcript, a README dump, or a sales page."""
from __future__ import annotations

import os
from typing import Any, Dict

from .. import http

TEXT_EXT = (".md", ".markdown", ".txt", ".srt", ".vtt", ".html", ".htm")


def looks_like_text(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in TEXT_EXT


def probe(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    headings = [
        line.lstrip("#").strip()
        for line in text.splitlines()
        if line.startswith("#")
    ]
    return {
        "source": "text",
        "target": os.path.basename(path),
        "url": path,
        "notes": [],
        "facts": {
            "chars": len(text),
            "headings": headings[:40],
            "text": text,
            "links": [w for w in text.split() if w.startswith("http")][:60],
            "promo_hits": [],
            "numbers": [],
            "has_tests": False,
        },
    }
