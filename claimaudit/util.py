"""Small shared helpers: time, numbers, text hygiene.

Everything here is stdlib-only and Python 3.9 compatible.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Optional

_ISO = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
)


def utcnow() -> _dt.datetime:
    """Naive UTC 'now' — all timestamps in this project are naive UTC."""
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def parse_iso(value: Optional[str]) -> Optional[_dt.datetime]:
    """Parse the ISO-8601 subset GitHub returns ('...Z' or '+00:00')."""
    if not value:
        return None
    m = _ISO.match(str(value).strip())
    if not m:
        return None
    try:
        return _dt.datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None


def days_since(value: Optional[str], now: Optional[_dt.datetime] = None) -> Optional[float]:
    parsed = parse_iso(value)
    if parsed is None:
        return None
    now = now or utcnow()
    return (now - parsed).total_seconds() / 86400.0


def age_days(created: Optional[str], pushed: Optional[str],
             now: Optional[_dt.datetime] = None) -> float:
    """Repo age in days, floored at 1 so division stays safe."""
    d = days_since(created, now)
    return max(1.0, d if d is not None else 1.0)


def human_days(days: Optional[float]) -> str:
    if days is None:
        return "未知"
    if days < 1:
        return "今天"
    if days < 30:
        return "%d 天前" % int(round(days))
    if days < 365:
        return "%d 个月前" % int(round(days / 30.0))
    return "%.1f 年前" % (days / 365.0)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def ratio(hit: int, total: int, empty: float = 0.5) -> float:
    """Safe hit/total. `empty` is used when there is nothing to measure."""
    if total <= 0:
        return empty
    return clamp(hit / float(total))


def squish(text: str, limit: int = 160) -> str:
    """Collapse whitespace and clip — used for evidence strings and tables."""
    if not text:
        return ""
    flat = re.sub(r"\s+", " ", str(text)).strip()
    if len(flat) <= limit:
        return flat
    return flat[: max(0, limit - 1)].rstrip() + "…"


def dedupe(items, key=None):
    seen, out = set(), []
    for item in items:
        k = key(item) if key else item
        if k in seen:
            continue
        seen.add(k)
        out.append(item)
    return out


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)
