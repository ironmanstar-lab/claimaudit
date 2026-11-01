"""Claim extraction — turn marketing prose into a list of checkable claims.

This is deliberately *not* an LLM call. A regex pass over 中文/English hype
vocabulary gives the same answer every run, costs nothing, works offline, and
keeps the audit reproducible. An LLM can always layer interpretation on top
(see SKILL.md); the facts underneath stay deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

# (kind, severity, pattern, how_to_check)
RULES = [
    ("money", 3, r"(月入|年化|收益率?|翻倍|躺赚|稳赚|暴富|回本|passive income|roi\s*[:：]?\s*\d)", "要净值曲线、样本期、最大回撤，以及是否实盘"),
    ("absolute", 3, r"(唯一.{0,8}(能|可|方法|选择|方案|一款|一家|路径)|最强|第一|顶级|零风险|无风险|必赚|必胜|100\s*%|guarantee[ds]?|world[- ]class|only\s+one)", "绝对化表述本身不可证伪，要求给出对照基线与失败案例"),
    ("quantity", 1, r"(\d{2,}\s*\+?\s*(个|条|种|项|位)?\s*(因子|指标|插件|技能|模块|功能|模型|策略|案例|模板))", "数一遍仓库/页面里的实际条目，看是否含占位与重复"),
    ("effortless", 2, r"(一键|全自动|零基础|无脑|开箱即用|秒级上手|one[- ]click|out[- ]of[- ]the[- ]box|no[- ]code)", "看依赖数量、安装步骤、是否需要付费 key 或买数据"),
    ("free_open", 2, r"(免费|开源|白嫖|open[- ]source|free\s+forever)", "核对 LICENSE 是否存在、是否开放完整代码，还是只给 exe/网盘"),
    ("time", 2, r"(\d+\s*(分钟|小时|天|周|个月)\s*(学会|上手|搞定|跑通|回本|见效))", "找可复现的计时样本，别接受口头承诺"),
    ("authority", 1, r"(大厂|前(?:阿里|腾讯|字节|百度|美团|京东|华为)|十年经验|资深|博士|\bcto\b|首席)", "身份无法外部核实，只看产出物"),
    ("social", 2, r"(全网首发|人都在用|官方推荐|官方认证|国家级|独家)", "去官方渠道/榜单核对，别信截图"),
]

_COMPILED = [(k, s, re.compile(p, re.I), h) for k, s, p, h in RULES]

NOISE = re.compile(r"[\s`*_#>\[\]()（）【】,，。.!！?？:：;；\"'“”‘’]+")


@dataclass
class Claim:
    kind: str
    text: str
    severity: int
    verifiable: bool
    hint: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "kind": self.kind,
            "text": self.text,
            "severity": self.severity,
            "verifiable": self.verifiable,
            "hint": self.hint,
        }


def _normalize(text: str) -> str:
    return NOISE.sub("", text).lower()


def _line_around(text: str, start: int, end: int) -> str:
    """Return the markdown line containing the match, stripped of syntax.

    Line-level context beats ±N characters: it never slices a table in half and
    it reads like something a human actually wrote.
    """
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].strip()
    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"^[-*+>]\s*", "", line)
    line = re.sub(r"^\d+[.)]\s*", "", line)
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)  # markdown links → text
    line = line.replace("`", "").replace("**", "").replace("|", " ")
    line = re.sub(r"\s+", " ", line).strip()
    if len(line) > 110:
        pivot = max(0, line.find(text[start:end][:8]))
        line = line[max(0, pivot - 40): pivot + 70].strip()
        line = "…" + line + "…"
    return line


def _sentence_around(text: str, start: int, end: int, width: int = 28) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    snippet = text[left:right]
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet


def _looks_like_headline(line: str) -> bool:
    """短、无标点、带感叹号 — 通常是标题/导航条目，不是正文宣称。"""
    if not line:
        return True
    if len(line) > 46:
        return False
    if re.search(r"[，。；：,;]", line):
        return False
    return bool(re.search(r"[！!？?…]", line)) or len(line) <= 16


def _is_table_or_code(text: str, start: int, end: int) -> bool:
    """Skip claims that live inside a table row or a fenced code block."""
    line_start = text.rfind("\n", 0, start) + 1
    line = text[line_start: text.find("\n", end) if text.find("\n", end) != -1 else len(text)]
    if line.count("|") >= 2:
        return True
    if line.count("·") >= 3:  # 文档目录/导航行，不是宣称
        return True
    fences = text.count("```", 0, start)
    return fences % 2 == 1


def _is_verifiable(snippet: str) -> bool:
    """A claim is verifiable when it carries a number+unit, or a named artifact."""
    if re.search(r"\d+\s*(%|倍|万|亿|个|条|项|分钟|小时|天|周|月|元|美元|star)", snippet):
        return True
    return bool(re.search(r"(github|release|benchmark|数据集|代码|license)", snippet, re.I))


def extract(text: str, limit: int = 40, per_kind: int = 4) -> List[Claim]:
    """Return deduped claims, most severe first.

    Claims inside tables and fenced code blocks are skipped — they are almost
    always technical prose (a factor table, a shell snippet), not a pitch, and
    quoting them makes the report look silly. ``per_kind`` keeps one repetitive
    writer from filling the whole table.
    """
    if not text:
        return []
    seen = set()
    claims: List[Claim] = []
    for kind, severity, pattern, hint in _COMPILED:
        taken = 0
        for match in pattern.finditer(text):
            if taken >= per_kind:
                break
            if _is_table_or_code(text, match.start(), match.end()):
                continue
            snippet = _line_around(text, match.start(), match.end()) or _sentence_around(
                text, match.start(), match.end()
            )
            if not snippet or _looks_like_headline(snippet):
                continue
            key = (kind, _normalize(snippet)[:40])
            if key in seen:
                continue
            seen.add(key)
            taken += 1
            claims.append(
                Claim(
                    kind=kind,
                    text=snippet,
                    severity=severity,
                    verifiable=_is_verifiable(snippet),
                    hint=hint,
                )
            )
    claims.sort(key=lambda c: (-c.severity, len(c.text)))
    return claims[:limit]


def counts(claims: Iterable[Claim]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for claim in claims:
        out[claim.kind] = out.get(claim.kind, 0) + 1
    return out


def by_kind(claims: Iterable[Claim], kind: str) -> List[Claim]:
    return [c for c in claims if c.kind == kind]


FIELD_LABELS = {
    "money": "收益承诺",
    "absolute": "绝对化表述",
    "quantity": "数量宣称",
    "effortless": "轻松上手",
    "free_open": "开源/免费",
    "time": "时间承诺",
    "authority": "身份背书",
    "social": "社会证明",
}
