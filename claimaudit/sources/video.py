"""Video adapter — best-effort metadata for share links (抖音 / B站 / 小红书 …).

A short video cannot be audited from its URL alone: the interesting part is
the *script*, and there is no public transcript endpoint. So this adapter
does two honest things:

1. resolves the share link to platform + content id + whatever metadata the
   page exposes (title, author);
2. tells the caller that a transcript is required, and how to supply one.

That "we cannot verify this yet" answer is itself a useful audit result —
it is exactly the evidence gap most 短视频 安利 leaves behind.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .. import http

PLATFORMS = (
    ("douyin", ("douyin.com", "v.douyin.com")),
    ("bilibili", ("bilibili.com", "b23.tv")),
    ("xiaohongshu", ("xiaohongshu.com", "xhslink.com")),
    ("kuaishou", ("kuaishou.com",)),
    ("youtube", ("youtube.com", "youtu.be")),
    ("wechat", ("mp.weixin.qq.com",)),
)


def detect(url: str) -> Optional[str]:
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    for name, domains in PLATFORMS:
        if any(host.endswith(d) for d in domains):
            return name
    return None


def _video_id(url: str) -> str:
    patterns = (
        r"/video/([\w]+)",
        r"/note/(\w+)",
        r"[?&]v=([\w-]+)",
        r"youtu\.be/([\w-]+)",
        r"/explore/([\w-]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def probe(url: str, transcript: Optional[str] = None, token: str = None) -> Dict[str, Any]:
    platform = detect(url) or "unknown"
    notes = []
    title = ""
    author = ""

    if not transcript:
        try:
            body, _ = http.get(url, token=token, timeout=12)
            match = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
            if match:
                title = re.sub(r"\s+", " ", match.group(1)).strip()
            meta = re.search(
                r'<meta[^>]+(?:name|property)="(?:og:title|author)"[^>]+content="([^"]*)"',
                body,
                re.I,
            )
            if meta:
                author = meta.group(1).strip()
        except http.FetchError as exc:
            notes.append("视频页元数据未取到：%s" % exc)

    text = transcript or ""
    notes.append(
        "视频类目标只能核到元数据；文案/口播内容需用 --transcript 提供，"
        "否则评分会显著偏低（这是证据缺口，不是内容问题）。"
    )
    return {
        "source": "video",
        "target": title or url,
        "url": url,
        "notes": notes,
        "facts": {
            "platform": platform,
            "video_id": _video_id(url),
            "title": title,
            "author": author,
            "transcript": text,
            "chars": len(text),
            "headings": [],
            "links": [],
            "promo_hits": [],
            "numbers": [],
            "has_tests": False,
            "transcript_required": not bool(transcript),
        },
    }
