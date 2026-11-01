"""Markdown / JSON rendering — the part a human actually reads."""
from __future__ import annotations

import datetime as _dt
import html
import json
from typing import Any, Dict, List, Optional

from . import claims as claims_mod
from .rubric import DISCLAIMER, RUBRIC_VERSION, Audit

CLAIM_KIND_TO_CHECK = {
    "money": "disclosure",
    "absolute": "claim_numbers",
    "quantity": "module_claims",
    "effortless": "install_claim",
    "free_open": "license_claim",
    "time": "quickstart",
    "authority": "external_refs",
    "social": "external_refs",
}

MARKS = ((0.75, "✅ 对得上"), (0.4, "⚠️ 部分对得上"), (0.0, "❌ 对不上"))


def _mark(pct: Optional[float]) -> str:
    if pct is None:
        return "· 未核"
    for threshold, label in MARKS:
        if pct >= threshold:
            return label
    return MARKS[-1][1]


def _bar(pct: float, width: int = 10) -> str:
    filled = int(round(pct * width))
    return "█" * filled + "░" * (width - filled)


def _now(now: Optional[_dt.datetime]) -> str:
    now = now or _dt.datetime.utcnow()
    return (now + _dt.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M（UTC+8）")


def _check_id_for(claim: claims_mod.Claim, source: str) -> str:
    # 非仓库目标没有 LICENSE / 依赖可言，用「有没有外部材料」代答
    if source != "github" and claim.kind in ("free_open", "effortless"):
        return "external_refs"
    return CLAIM_KIND_TO_CHECK.get(claim.kind, "")


def _evidence_for(claim: claims_mod.Claim, by_id: Dict[str, Any], source: str = "github") -> str:
    check = by_id.get(_check_id_for(claim, source))
    if check is None:
        return "未取得可核证据"
    return check.evidence


def _claim_pct(claim: claims_mod.Claim, by_id: Dict[str, Any], source: str = "github") -> Optional[float]:
    check = by_id.get(_check_id_for(claim, source))
    return None if check is None else check.pct


def _pick_claims(claims, limit: int, per_kind: int = 2):
    """Keep at most ``per_kind`` claims of one type so the table stays readable."""
    out, seen = [], {}
    for claim in claims:
        if seen.get(claim.kind, 0) >= per_kind:
            continue
        seen[claim.kind] = seen.get(claim.kind, 0) + 1
        out.append(claim)
        if len(out) >= limit:
            break
    return out


def render(audit: Audit, now: Optional[_dt.datetime] = None, top_claims: int = 8) -> str:
    by_id = {o.check_id: o for o in audit.outcomes}
    lines: List[str] = []

    lines.append("# 验货报告 · %s" % (audit.target or audit.facts.get("full_name") or "—"))
    lines.append("")
    if audit.insufficient:
        verdict_line = "**未定级** · %s" % audit.verdict
    else:
        verdict_line = "**%s（%.1f / 100）** · %s" % (audit.grade, audit.score, audit.verdict)
    lines.append("> 结论：%s" % verdict_line)
    if audit.redflags:
        lines.append("> 首要红旗：%s" % audit.redflags[0])
    lines.append(">")
    lines.append(
        "> 对象：%s · 来源：%s · 生成：%s · 方法：claimaudit 18 项检查 · rubric v%s（规则打分，可复现）"
        % (
            audit.facts.get("url") or audit.target or "—",
            audit.source,
            _now(now),
            RUBRIC_VERSION,
        )
    )
    lines.append(">")
    lines.append("> 📌 %s" % DISCLAIMER)
    lines.append("")

    # --- 1. scorecard -----------------------------------------------------
    lines.append("## 一、评分卡")
    if audit.insufficient:
        lines.append("")
        lines.append("> 样本不足，下面是**参考分**，不要当成结论。")
    lines.append("")
    lines.append("| 维度 | 得分 | 占比 | 可视化 |")
    lines.append("|---|---:|---:|---|")
    for name, earned, possible in audit.dims:
        if possible <= 0:
            continue
        pct = (earned / possible) if possible else 0.0
        lines.append(
            "| %s | %.1f / %.0f | %.0f%% | `%s` |"
            % (name, earned, possible, pct * 100, _bar(pct))
        )
    lines.append("")

    # --- 2. claims vs evidence -------------------------------------------
    shown = _pick_claims(audit.claims, top_claims)
    lines.append("## 二、宣称 vs 证据")
    lines.append("")
    if not shown:
        lines.append("> 没有从文本里提取到明确宣称。把卖点原文（视频文案、商品页、README）贴进来再跑一次。")
    else:
        lines.append("| # | 它说 | 类型 | 我们核到 | 判定 |")
        lines.append("|---:|---|---|---|---|")
        for idx, claim in enumerate(shown, 1):
            lines.append(
                "| %d | %s | %s | %s | %s |"
                % (
                    idx,
                    claim.text.replace("|", "\\|")[:90],
                    claims_mod.FIELD_LABELS.get(claim.kind, claim.kind),
                    _evidence_for(claim, by_id, audit.source).replace("|", "\\|")[:90],
                    _mark(_claim_pct(claim, by_id, audit.source)),
                )
            )
        if len(audit.claims) > len(shown):
            lines.append("")
            lines.append("（另有 %d 条宣称未列出）" % (len(audit.claims) - len(shown)))
    lines.append("")

    # --- 3. red flags -----------------------------------------------------
    lines.append("## 三、红旗")
    lines.append("")
    if audit.redflags:
        for flag in audit.redflags:
            lines.append("- 🚩 %s" % flag)
    else:
        lines.append("- 未命中任何红旗（这很少见，通常说明样本太干净）")
    lines.append("")

    # --- 4. evidence gaps -------------------------------------------------
    lines.append("## 四、证据缺口（它没法被核实的部分）")
    lines.append("")
    for gap in audit.gaps:
        lines.append("- %s" % gap)
    lines.append("")

    # --- 5. checklist -----------------------------------------------------
    lines.append("## 五、30 分钟自检清单")
    lines.append("")
    if audit.checklist:
        for idx, item in enumerate(audit.checklist, 1):
            lines.append("%d. %s" % (idx, item))
    else:
        lines.append("1. 已经没什么要补的了，直接按它的文档跑一遍即可。")
    lines.append("")
    if audit.source == "github":
        lines.append("```bash")
        lines.append("# 想自己复核关键事实：")
        lines.append("claimaudit %s --json | jq '.facts | {stars, created_at, pushed_at, commits, contributors, license}'"
                     % (audit.facts.get("url") or audit.target))
        lines.append("```")
        lines.append("")

    # --- 6. facts ---------------------------------------------------------
    lines.append("## 六、采集到的事实")
    lines.append("")
    lines.append("| 事实 | 值 |")
    lines.append("|---|---|")
    for key, value in _fact_rows(audit).items():
        lines.append("| %s | %s |" % (key, value))
    lines.append("")

    notes = [n for n in audit.notes if n]
    if notes:
        lines.append("**采集备注**")
        lines.append("")
        for note in notes[:6]:
            lines.append("- %s" % note)
        lines.append("")

    lines.append("---")
    lines.append(
        "> 打分是启发式的，用来对齐讨论，不是判决。所有分数都能追到上面的事实与检查项；"
        "不同意某一条时，改 `claimaudit/rubric.py` 里的权重就行。"
    )
    return "\n".join(lines)


def _fact_rows(audit: Audit) -> Dict[str, Any]:
    f = audit.facts
    rows: Dict[str, Any] = {}
    if audit.source == "github":
        rows["仓库"] = f.get("full_name", "")
        rows["Star / Fork"] = "%s / %s" % (f.get("stars", 0), f.get("forks", 0))
        rows["建库 / 最近提交"] = "%s / %s" % (
            (f.get("created_at") or "")[:10],
            (f.get("pushed_at") or "")[:10],
        )
        rows["提交数 / 贡献者"] = "%s / %s" % (f.get("commits", 0), f.get("contributors", 0))
        rows["License"] = f.get("license") or "无"
        sig = f.get("signals") or {}
        rows["测试 / CI"] = "%s / %s" % (
            "%d 个文件" % sig.get("test_files", 0) if sig.get("has_tests") else "无",
            "有" if sig.get("has_ci") else "无",
        )
        rows["文件数 / 代码文件"] = "%s / %s" % (sig.get("file_count", 0), sig.get("code_files", 0))
        rows["README 字数"] = (f.get("readme") or {}).get("chars", 0)
    else:
        rows["标题"] = f.get("title") or f.get("target") or ""
        rows["正文长度"] = "%s 字" % f.get("chars", 0)
        if f.get("promo_hits"):
            rows["转化钩子"] = "、".join(f["promo_hits"][:6])
        if f.get("platform"):
            rows["平台"] = f["platform"]
    rows["提取到的宣称"] = "%d 条" % len(audit.claims)
    return rows


def render_json(audit: Audit) -> str:
    return json.dumps(audit.as_dict(), ensure_ascii=False, indent=2)


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


HTML_CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;padding:56px 20px 96px;background:#0f1115;color:#e6e8ee;
 font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif}
main{max-width:920px;margin:0 auto}
h1{font-size:26px;margin:0 0 14px;letter-spacing:.3px}
h2{font-size:18px;margin:34px 0 12px;padding-bottom:8px;border-bottom:1px solid #262a33;color:#fff}
.verdict{margin:6px 0 18px;padding:14px 16px;border-left:3px solid #4b8bff;
 background:#151922;border-radius:0 8px 8px 0;color:#dfe6f5}
.verdict b{color:#fff}
.badge{display:inline-block;min-width:34px;text-align:center;padding:2px 8px;margin-right:8px;
 border-radius:6px;background:#20242e;font-weight:700}
.g-S{color:#56c88c}.g-A{color:#79c8ff}.g-B{color:#f0aa3c}.g-C{color:#ff8f5a}.g-D{color:#ff6b6b}.g-na{color:#8b93a3}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}
th,td{border:1px solid #262a33;padding:7px 10px;text-align:left;vertical-align:top}
th{background:#171b24;font-weight:600;color:#fff}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.bar{font-family:ui-monospace,Consolas,monospace;color:#6ea8ff}
.flag{padding:4px 0}
ul{padding-left:22px}li{margin:5px 0}
code{background:#1b2029;padding:1px 5px;border-radius:4px;font-family:ui-monospace,Consolas,monospace;font-size:13px}
footer{margin-top:36px;padding-top:14px;border-top:1px solid #262a33;color:#8b93a3;font-size:13px}
"""


def render_html(audit: Audit, now: Optional[_dt.datetime] = None) -> str:
    """自包含单文件 HTML —— 发给不装 Python 的人看。"""
    by_id = {o.check_id: o for o in audit.outcomes}
    grade = audit.grade
    grade_cls = "g-" + (grade if grade in ("S", "A", "B", "C", "D") else "na")
    parts = [
        "<!doctype html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>验货报告 · %s</title>" % _e(audit.target),
        "<style>%s</style></head><body><main>" % HTML_CSS,
        "<h1>验货报告 · %s</h1>" % _e(audit.target),
    ]

    if audit.insufficient:
        head = '<span class="badge %s">—</span>未定级 · %s' % (grade_cls, _e(audit.verdict))
    else:
        head = '<span class="badge %s">%s</span>%.1f / 100 · %s' % (
            grade_cls, _e(grade), audit.score, _e(audit.verdict)
        )
    parts.append('<div class="verdict">%s</div>' % head)

    if audit.redflags:
        parts.append('<div class="verdict" style="border-color:#ff8f5a">🚩 %s</div>' % _e(audit.redflags[0]))

    parts.append('<p style="color:#8b93a3;font-size:13px">对象：%s · 来源：%s · 生成：%s'
                 ' · 方法：claimaudit 18 项检查 · rubric v%s（规则打分，可复现）</p>'
                 % (_e(audit.facts.get("url") or audit.target), _e(audit.source), _e(_now(now)),
                    _e(RUBRIC_VERSION)))
    parts.append(
        '<p style="margin:10px 0 0;padding:10px 12px;border-radius:8px;'
        'background:#171b24;color:#9aa3b2;font-size:13px">📌 %s</p>' % _e(DISCLAIMER)
    )

    # 评分卡
    parts.append("<h2>一、评分卡</h2><table><thead><tr><th>维度</th><th>得分</th><th>占比</th><th>可视化</th></tr></thead><tbody>")
    for name, earned, possible in audit.dims:
        if possible <= 0:
            continue
        pct = earned / possible
        parts.append(
            "<tr><td>%s</td><td class='num'>%.1f / %.0f</td><td class='num'>%.0f%%</td>"
            "<td class='bar'>%s</td></tr>" % (_e(name), earned, possible, pct * 100, _bar(pct))
        )
    parts.append("</tbody></table>")

    # 宣称 vs 证据
    shown = _pick_claims(audit.claims, 8)
    parts.append("<h2>二、宣称 vs 证据</h2>")
    if not shown:
        parts.append("<p>没有提取到明确宣称。</p>")
    else:
        parts.append("<table><thead><tr><th>#</th><th>它说</th><th>类型</th><th>我们核到</th><th>判定</th></tr></thead><tbody>")
        for idx, claim in enumerate(shown, 1):
            parts.append(
                "<tr><td class='num'>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                % (
                    idx,
                    _e(claim.text[:120]),
                    _e(claims_mod.FIELD_LABELS.get(claim.kind, claim.kind)),
                    _e(_evidence_for(claim, by_id, audit.source)[:120]),
                    _e(_mark(_claim_pct(claim, by_id, audit.source))),
                )
            )
        parts.append("</tbody></table>")

    # 红旗 / 缺口 / 清单
    parts.append("<h2>三、红旗</h2>")
    if audit.redflags:
        parts.append("".join('<div class="flag">🚩 %s</div>' % _e(f) for f in audit.redflags))
    else:
        parts.append("<div class='flag'>未命中任何红旗</div>")

    parts.append("<h2>四、证据缺口</h2><ul>%s</ul>" % "".join("<li>%s</li>" % _e(g) for g in audit.gaps))

    parts.append("<h2>五、30 分钟自检清单</h2>")
    if audit.checklist:
        parts.append("<ol>%s</ol>" % "".join("<li>%s</li>" % _e(i) for i in audit.checklist))
    else:
        parts.append("<p>没有额外要补的。</p>")

    parts.append("<h2>六、采集到的事实</h2><table><tbody>")
    for key, value in _fact_rows(audit).items():
        parts.append("<tr><th>%s</th><td>%s</td></tr>" % (_e(key), _e(value)))
    parts.append("</tbody></table>")

    parts.append(
        "<footer>打分是启发式的，用来对齐讨论，不是判决。"
        "所有分数都能追到上面的事实与检查项；不同意某一条时，改 claimaudit/rubric.py 的权重即可。</footer>"
    )
    parts.append("</main></body></html>")
    return "\n".join(parts)
