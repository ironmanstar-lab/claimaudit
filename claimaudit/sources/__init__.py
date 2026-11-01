"""Source adapters: turn a user-supplied target into a plain facts dict.

Every adapter returns the same top-level shape so the rubric never has to
care where a fact came from::

    {"source": "github"|"web"|"video"|"text",
     "target": str, "url": str, "notes": [str], "facts": {...}}
"""
from __future__ import annotations

from . import github, web, video, textfile

__all__ = ["github", "web", "video", "textfile"]
