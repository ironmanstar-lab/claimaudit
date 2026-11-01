"""Web page adapter — fetches a page and strips it down to auditable text."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any, Dict, List

from .. import http

PROMO_HINTS = (
    "加群", "微信群", "私信", "网盘", "星球", "训练营", "课程", "付费",
    "会员", "优惠", "名额", "扫码", "公众号", "资料包", "咨询", "报名",
)
_SKIP_TAGS = {"script", "style", "noscript", "svg", "code", "pre"}
_BLOCK_TAGS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "td"}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.headings: List[str] = []
        self.links: List[str] = []
        self.paragraphs: List[str] = []
        self._chunks: List[str] = []
        self._para: List[str] = []
        self._in_para = 0
        self._in_a = 0
        self._skip = 0
        self._in_title = False
        self._heading: List[str] = []
        self._heading_tag = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in _SKIP_TAGS:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in ("p", "article", "section", "blockquote"):
            self._in_para += 1
            self._para = []
        if tag in ("h1", "h2", "h3"):
            self._heading_tag = tag
            self._heading = []
        if tag == "meta":
            name = (attrs.get("name") or attrs.get("property") or "").lower()
            if name in ("description", "og:description") and attrs.get("content"):
                self.description = attrs["content"]
        if tag == "a":
            self._in_a += 1
            href = attrs.get("href") or ""
            if href.startswith("http"):
                self.links.append(href)
        if tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag == "a" and self._in_a:
            self._in_a -= 1
        if tag == "title":
            self._in_title = False
        if tag in ("p", "article", "section", "blockquote") and self._in_para:
            self._in_para -= 1
            if not self._in_para:
                text = " ".join(self._para).strip()
                if len(text) >= 20:
                    self.paragraphs.append(re.sub(r"\s+", " ", text))
                self._para = []
        if tag == self._heading_tag:
            text = " ".join(self._heading).strip()
            if text:
                self.headings.append(text)
            self._heading_tag = ""
            self._heading = []

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip or self._in_a:
            # 链接文字是导航（相关阅读/推荐位），不是正文宣称
            return
        text = data.strip()
        if not text:
            return
        if self._heading_tag:
            self._heading.append(data)
            return
        if self._in_para:
            self._para.append(data)
        self._chunks.append(text + " ")

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


def _numbers(text: str) -> List[str]:
    pattern = re.compile(
        r"[0-9]+(?:\.[0-9]+)?\s*(?:%|倍|万|亿|个|条|种|项|人|天|小时|分钟|元|美元|star|k|w)?"
    )
    found = [m.group(0).strip() for m in pattern.finditer(text)]
    return found[:60]


def probe(url: str, token: str = None) -> Dict[str, Any]:
    body, _ = http.get(url, token=token)
    parser = _Extractor()
    try:
        parser.feed(body)
    except Exception:  # malformed HTML must not kill the audit
        pass
    text = parser.text()
    long_paras = [p for p in parser.paragraphs if len(p) >= 60]
    if len(parser.paragraphs) >= 3:
        # 有段落结构就只信段落：导航/侧栏/相关阅读都在段落之外
        text = "\n".join(long_paras or parser.paragraphs)
    lowered = text.lower()
    promos = sorted({h for h in PROMO_HINTS if h in text})
    return {
        "source": "web",
        "target": parser.title.strip() or url,
        "url": url,
        "notes": [],
        "facts": {
            "title": parser.title.strip(),
            "description": parser.description,
            "chars": len(text),
            "headings": parser.headings[:40],
            "text": text,
            "links": list(dict.fromkeys(parser.links))[:60],
            "promo_hits": promos,
            "numbers": _numbers(text),
            "has_tests": False,
            "promo_count": len(promos),
            "lower_chars": len(lowered),
        },
    }
