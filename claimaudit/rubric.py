"""The rubric — 18 deterministic checks across 6 dimensions.

Why a rubric instead of "ask the model how good it is":

* two runs on the same target must produce the same score, otherwise the number
  is decoration;
* every point must point at an artifact (a file, a date, a count) so the reader
  can disagree with the *judgement* without doubting the *facts*;
* a check that cannot be evaluated on this target is dropped and the weights
  renormalised, instead of silently scoring 0.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import claims as claims_mod
from .util import age_days, clamp, days_since, human_days, ratio, squish, utcnow

DIMENSIONS = [
    ("可验证性", 25.0),
    ("证据密度", 20.0),
    ("宣称一致", 20.0),
    ("维护可信", 15.0),
    ("风险敞口", 10.0),
    ("上手成本", 10.0),
]

GRADES = [
    (85.0, "S", "可以当依赖用：宣称与证据基本对齐，缺的部分也标了出来"),
    (70.0, "A", "值得投入时间：有真东西，按报告里的缺口补齐再信任"),
    (55.0, "B", "有真东西但掺水：先做自检清单，再决定要不要投入"),
    (40.0, "C", "宣传远大于交付：只当素材看，别当工具用"),
    (0.0, "D", "不建议投入时间或钱：证据链基本不成立"),
]

CONTENT_VERDICTS = {
    "S": "罕见：关键说法都能追到外部材料，可以直接引用（仍建议回源）",
    "A": "可信度较高：关键数字有出处，引用前回源确认即可",
    "B": "半可信：方向可能对，但数字与机制需要回源",
    "C": "当线索用：自述多、可核材料少，别直接当结论",
    "D": "不建议引用：关键说法基本无法核实",
}

METHOD_WORDS = (
    "样本", "回测", "数据集", "基准", "benchmark", "口径", "t+1", "夏普", "sharpe",
    "回撤", "drawdown", "icir", "置信", "消融", "ablation", "复现", "随机种子", "bench",
)

DATA_COST_WORDS = (
    "tushare", "付费", "积分", "api key", "apikey", "token", "订阅", "会员",
    "买数据", "wind", "choice", "需要自行获取",
)

DISCLAIMER_WORDS = ("不构成投资建议", "免责", "disclaimer", "风险自担", "not investment advice")

MODULE_TOKEN = re.compile(r"`([A-Za-z_][\w./-]{2,40})`|\b([a-z_]{3,20})/(?=\s|\||\Z)")
CODE_EXT = (".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java")
ARTIFACT_EXT = (".zip", ".exe", ".cmd", ".md", ".json", ".yaml", ".yml", ".db", ".html", ".toml")


@dataclass
class Outcome:
    check_id: str
    dim: str
    title: str
    weight: float
    pct: float
    evidence: str
    redflag: Optional[str] = None
    action: Optional[str] = None


@dataclass
class Audit:
    target: str
    source: str
    score: float
    grade: str
    verdict: str
    dims: List[Tuple[str, float, float]]  # (name, earned, possible)
    outcomes: List[Outcome] = field(default_factory=list)
    redflags: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    checklist: List[str] = field(default_factory=list)
    claims: List[claims_mod.Claim] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    facts: Dict[str, Any] = field(default_factory=dict)
    cap_reason: str = ""
    insufficient: bool = False
    insufficient_reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "source": self.source,
            "score": round(self.score, 1),
            "grade": self.grade,
            "verdict": self.verdict,
            "dims": [
                {"name": n, "earned": round(e, 1), "possible": round(p, 1),
                 "pct": round(e / p * 100, 1) if p else 0.0}
                for n, e, p in self.dims
            ],
            "checks": [
                {
                    "id": o.check_id,
                    "dim": o.dim,
                    "title": o.title,
                    "weight": o.weight,
                    "pct": round(o.pct, 2),
                    "evidence": o.evidence,
                    "redflag": o.redflag,
                }
                for o in self.outcomes
            ],
            "redflags": self.redflags,
            "gaps": self.gaps,
            "checklist": self.checklist,
            "cap_reason": self.cap_reason,
            "insufficient": self.insufficient,
            "insufficient_reason": self.insufficient_reason,
            "claims": [c.as_dict() for c in self.claims],
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _sig(facts: Dict[str, Any]) -> Dict[str, Any]:
    return facts.get("signals") or {}


def _text(ctx: Dict[str, Any]) -> str:
    facts = ctx["facts"]
    readme = facts.get("readme") or {}
    return (readme.get("text") or facts.get("text") or facts.get("transcript") or "")


def _count_words(haystack: str, needles) -> int:
    low = haystack.lower()
    return sum(1 for n in needles if n.strip() and n.lower() in low)


def _has(ctx: Dict[str, Any], key: str) -> bool:
    return bool(_sig(ctx["facts"]).get(key))


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
def _claim_numbers(ctx, now):
    found = ctx["claims"]
    if not found:
        return 0.6, "未提取到明确宣称（可能只是薄薄一页说明）", None, "把它的卖点原文贴进 --transcript 再跑一次，避免空跑"
    verifiable = [c for c in found if c.verifiable]
    pct = ratio(len(verifiable), len(found), empty=0.3)
    return (
        pct,
        "%d 条宣称中 %d 条带可核口径" % (len(found), len(verifiable)),
        None if pct >= 0.4 else "宣称多为不可证伪的定性表述",
        "挑 1 条最重要的宣称，要求作者给出数字口径（样本期 + 计算方法）",
    )


def _external_refs(ctx, now):
    facts = ctx["facts"]
    text = _text(ctx)
    links = set(facts.get("links") or [])
    links |= set(re.findall(r"https?://[^\s)\]>]+", text))
    self_url = (facts.get("url") or "").rstrip("/")
    external = [u for u in links if not (self_url and u.startswith(self_url))]
    n = len(external)
    if n >= 3:
        return 1.0, "正文含 %d 个外部可核链接（论文/数据/文档）" % n, None, None
    if n >= 1:
        return 0.6, "正文含 %d 个外部链接，证据面偏薄" % n, None, "要求给出第三方数据源或论文出处"
    return 0.2, "正文没有任何外部可核链接", "全靠自述，没有第三方可核材料", "让它给出一条能独立复核的数据或代码路径"


def _method_disclosure(ctx, now):
    hits = _count_words(_text(ctx), METHOD_WORDS)
    if hits >= 4:
        return 1.0, "出现 %d 处方法论/口径表述" % hits, None, None
    if hits >= 2:
        return 0.7, "出现 %d 处方法论表述，但缺关键口径" % hits, None, "补齐样本期、成本模型、失败案例"
    if hits == 1:
        return 0.4, "只有 1 处方法论表述", None, "追问样本期与对照基线"
    return 0.1, "没有任何方法论/口径表述", "只有结论没有方法", "要求提供方法与失败案例，否则结论不可信"


def _tests(ctx, now):
    facts = ctx["facts"]
    sig = _sig(facts)
    if "code_files" not in sig:
        return None
    if not sig.get("code_files"):
        return 0.2, "仓库里没有可识别的代码文件", None, "确认交付物到底是什么"
    if sig.get("has_tests"):
        return 1.0, "有 %d 个测试文件" % sig.get("test_files", 0), None, None
    return 0.1, "0 个测试文件（%d 个代码文件）" % sig.get("code_files", 0), "没有任何自动化测试", "跑一条最关键的路径，看是否只能靠肉眼验证"


def _ci(ctx, now):
    if "has_ci" not in _sig(ctx["facts"]):
        return None
    if _has(ctx, "has_ci"):
        return 1.0, "存在 CI 配置", None, None
    return 0.1, "没有 CI 配置", None, "看最近一次提交是否真的能跑起来"


def _repro(ctx, now):
    sig = _sig(ctx["facts"])
    if "has_demo_data" not in sig:
        return None
    demo, deps = sig.get("has_demo_data"), sig.get("dependency_files") or []
    if demo and deps:
        return 1.0, "有演示数据 + 依赖清单，可离线跑通", None, None
    if demo or deps:
        return 0.6, "有%s，缺%s" % ("演示数据" if demo else "依赖清单", "依赖清单" if demo else "演示数据"), None, "先跑 demo，再碰真实数据"
    return 0.15, "没有演示数据也没有依赖清单", None, "要求 10 分钟可复现的最小样例"


def _docs(ctx, now):
    sig = _sig(ctx["facts"])
    if "docs_count" not in sig:
        return None
    docs = sig.get("docs_count", 0)
    chars = (ctx["facts"].get("readme") or {}).get("chars", 0)
    if docs >= 3:
        return 1.0, "%d 篇文档" % docs, None, None
    if docs >= 1:
        return 0.6, "%d 篇文档 + README %d 字" % (docs, chars), None, None
    if chars >= 3000:
        return 0.4, "只有 README（%d 字），无独立文档" % chars, None, "按 README 走一遍，记录卡住的地方"
    return 0.15, "文档极薄（README %d 字）" % chars, "文档体量与宣称体量不匹配", "先问作者要一份能跑的环境说明"


def _module_claims(ctx, now):
    facts = ctx["facts"]
    paths = (facts.get("tree") or {}).get("paths") or []
    if not paths:
        return None
    text = _text(ctx)
    tokens = []
    for m in MODULE_TOKEN.finditer(text):
        token = (m.group(1) or m.group(2) or "").strip().strip("/")
        if not token or "/" in token:
            continue
        if not re.match(r"^[A-Za-z_][\w-]{3,30}$", token):
            continue  # 文件名/版本号/中文标识，不是模块名
        tokens.append(token)
    tokens = [t for t in dict.fromkeys(tokens) if len(t) >= 4][:25]
    if not tokens:
        return 0.5, "正文没有可核对的模块名", None, "要求列出目录结构，对照功能列表"
    joined = "\n".join(paths).lower()
    hits = [t for t in tokens if t.lower() in joined]
    pct = ratio(len(hits), len(tokens), empty=0.5)
    missing = [t for t in tokens if t not in hits][:4]
    evidence = "正文提到的 %d 个模块名中 %d 个能在文件树里找到" % (len(tokens), len(hits))
    if missing:
        evidence += "；缺失示例：" + "、".join(missing)
    return (
        pct,
        evidence,
        None if pct >= 0.5 else "宣称的模块在代码里对不上",
        "逐个点开功能列表，确认每一项都有对应实现文件",
    )


def _license_claim(ctx, now):
    if ctx.get("source") != "github":
        return None  # 只有仓库才有 LICENSE 可言
    facts = ctx["facts"]
    kinds = claims_mod.counts(ctx["claims"])
    if not kinds.get("free_open"):
        return 0.7, "未宣称开源/免费（不适用）", None, None
    license_id = facts.get("license")
    if license_id and license_id.upper() != "NOASSERTION":
        return 1.0, "宣称开源且 LICENSE = %s" % license_id, None, None
    if _sig(facts).get("has_license_file") or (license_id or "").upper() == "NOASSERTION":
        return 0.8, "宣称开源，有 LICENSE 文件但类型未被识别", None, "打开 LICENSE 确认是否真开源（MIT/Apache-2.0…）"
    return 0.0, "宣称开源但仓库无 LICENSE", "宣称开源却无 LICENSE：法律上不可用", "要求作者补 LICENSE，否则只能看不能改"


def _install_claim(ctx, now):
    facts = ctx["facts"]
    sig = _sig(facts)
    kinds = claims_mod.counts(ctx["claims"])
    if not kinds.get("effortless"):
        return 0.7, "未宣称一键/零门槛（不适用）", None, None
    if "dependency_count" not in sig:
        return None
    deps = sig.get("dependency_count", 0)
    if deps <= 3:
        return 1.0, "宣称零门槛，依赖文件 %d 个" % deps, None, None
    if deps <= 8:
        return 0.6, "宣称零门槛，实际依赖文件 %d 个" % deps, None, "先按 README 装一遍，记录失败点"
    return 0.15, "宣称一键，实际依赖文件 %d 个" % deps, "「一键」与依赖规模不符", "把它真正跑起来，记录到成功为止的每一步"


def _recent_push(ctx, now):
    facts = ctx["facts"]
    days = days_since(facts.get("pushed_at"), now)
    if days is None:
        days = facts.get("days_since_push")
    if days is None:
        return None
    if days <= 30:
        return 1.0, "最近一次提交 %s" % human_days(days), None, None
    if days <= 60:
        return 0.8, "最近一次提交 %s" % human_days(days), None, None
    if days <= 120:
        return 0.55, "最近一次提交 %s，维护节奏偏慢" % human_days(days), None, "看 issue 区最近有没有人回复"
    if days <= 180:
        return 0.35, "最近一次提交 %s，已进入低维护" % human_days(days), None, "看 issue 区最近有没有人回复"
    if days <= 365:
        return 0.2, "最近一次提交 %s" % human_days(days), "半年以上没有代码更新", "别指望它能跟上依赖升级"
    return 0.05, "最近一次提交 %s" % human_days(days), "一年以上没有提交，项目实质停更", "优先找仍在维护的替代方案"


def _cadence(ctx, now):
    facts = ctx["facts"]
    commits = facts.get("commits")
    if commits is None:
        return None
    age = age_days(facts.get("created_at"), facts.get("pushed_at"), now)
    per_month = commits / max(age / 30.0, 1.0 / 30.0)
    if per_month >= 4:
        return 1.0, "约 %.1f 次提交/月（共 %d 次）" % (per_month, commits), None, None
    if per_month >= 1:
        return 0.6, "约 %.1f 次提交/月（共 %d 次）" % (per_month, commits), None, None
    if commits > 0:
        return 0.3, "约 %.2f 次提交/月（共 %d 次）" % (per_month, commits), None, "看提交是否集中在发布日前后（一次性 dump）"
    return 0.1, "提交数为 0", None, None


def _bus_factor(ctx, now):
    facts = ctx["facts"]
    contributors = facts.get("contributors")
    if not contributors:
        return None
    if contributors >= 5:
        return 1.0, "%d 位贡献者" % contributors, None, None
    if contributors >= 3:
        return 0.8, "%d 位贡献者" % contributors, None, None
    if contributors == 2:
        return 0.6, "2 位贡献者", None, None
    stars = facts.get("stars") or 0
    return (
        0.25,
        "仅 1 位贡献者（%d star）" % stars,
        None if stars < 1000 else "单人维护但关注度高，bus factor = 1",
        "看作者是否接受外部 PR，判断会不会烂尾",
    )


def _promo(ctx, now):
    facts = ctx["facts"]
    text = _text(ctx)
    hits = list(facts.get("promo_hits") or [])
    for word in ("加群", "网盘", "私信", "知识星球", "训练营", "优惠", "名额"):
        if word in text:
            hits.append(word)
    hits = list(dict.fromkeys(hits))
    if not hits:
        return 1.0, "未见引流/付费钩子", None, None
    if len(hits) == 1:
        return 0.5, "出现 1 个转化钩子：%s" % hits[0], None, "确认内容主体是不是只为导流到私域"
    return 0.0, "出现 %d 个转化钩子：%s" % (len(hits), "、".join(hits[:5])), "内容带明显私域/付费转化钩子", "先把免费部分跑通，再决定要不要进群"


def _binaries(ctx, now):
    sig = _sig(ctx["facts"])
    if "binary_count" not in sig:
        return None
    binaries = sig.get("binary_count", 0)
    node_modules = sig.get("committed_node_modules")
    if binaries or node_modules:
        extra = "、".join(sig.get("binaries", [])[:3])
        return (
            0.0,
            "仓库提交了 %d 个二进制/压缩包%s%s" % (
                binaries, " + node_modules" if node_modules else "",
                ("：" + extra) if extra else "",
            ),
            "交付物含闭源二进制/依赖目录：无法审计，体积也异常",
            "要求源码构建路径，或先在隔离环境里跑",
        )
    return 1.0, "仓库无二进制/依赖目录提交", None, None


def _disclosure(ctx, now):
    text = _text(ctx).lower()
    kinds = claims_mod.counts(ctx["claims"])
    has = any(w.lower() in text for w in DISCLAIMER_WORDS)
    if has:
        return 1.0, "含免责/风险声明", None, None
    if kinds.get("money"):
        return 0.0, "有收益类宣称但无任何免责声明", "收益宣称 + 无免责声明：典型高风险内容", "要求作者明确说明这是不是投资建议、亏损谁承担"
    return 0.4, "未见免责声明", None, None


def _deps_cost(ctx, now):
    sig = _sig(ctx["facts"])
    text = _text(ctx).lower()
    if "dependency_count" not in sig:
        return None
    deps = sig.get("dependency_count", 0)
    paid = _count_words(text, DATA_COST_WORDS)
    if deps <= 2:
        base = 1.0
    elif deps <= 6:
        base = 0.7
    else:
        base = 0.35
    if paid >= 2:
        base = min(base, 0.45)
        return base, "依赖文件 %d 个，且需自备付费数据/Key" % deps, None, "把隐性成本算清楚：数据、Key、机器"
    return base, "依赖文件 %d 个" % deps, None, None


def _quickstart(ctx, now):
    text = _text(ctx)
    hits = _count_words(text, ("快速开始", "quickstart", "安装", "install", "usage", "用法", "开始"))
    if hits >= 2:
        return 1.0, "含安装/上手说明", None, None
    if hits == 1:
        return 0.6, "上手说明只有一句话", None, None
    return 0.2, "没有任何上手说明", None, "让作者补一份三步能跑通的说明"


CHECKS: List[Tuple[str, str, float, Callable]] = [
    ("claim_numbers", "可验证性", 10.0, _claim_numbers),
    ("external_refs", "可验证性", 8.0, _external_refs),
    ("method_disclosure", "可验证性", 7.0, _method_disclosure),
    ("tests", "证据密度", 7.0, _tests),
    ("ci", "证据密度", 5.0, _ci),
    ("repro", "证据密度", 4.0, _repro),
    ("docs", "证据密度", 4.0, _docs),
    ("module_claims", "宣称一致", 10.0, _module_claims),
    ("license_claim", "宣称一致", 5.0, _license_claim),
    ("install_claim", "宣称一致", 5.0, _install_claim),
    ("recent_push", "维护可信", 7.0, _recent_push),
    ("cadence", "维护可信", 4.0, _cadence),
    ("bus_factor", "维护可信", 4.0, _bus_factor),
    ("promo", "风险敞口", 4.0, _promo),
    ("binaries", "风险敞口", 3.0, _binaries),
    ("disclosure", "风险敞口", 3.0, _disclosure),
    ("deps_cost", "上手成本", 5.0, _deps_cost),
    ("quickstart", "上手成本", 5.0, _quickstart),
]


# --------------------------------------------------------------------------
# top-level
# --------------------------------------------------------------------------
def _extra_redflags(ctx, now) -> List[str]:
    flags: List[str] = []
    facts, found = ctx["facts"], ctx["claims"]
    kinds = claims_mod.counts(found)

    if kinds.get("money"):
        flags.append("出现收益/致富类宣称：必须配实盘净值 + 样本外验证，否则一律打折")
    if kinds.get("absolute", 0) >= 3:
        flags.append("绝对化用词密度异常（%d 处）" % kinds["absolute"])

    stars = facts.get("stars") or 0
    age = facts.get("age_days")
    if stars >= 3000 and age is not None and age < 60:
        flags.append("建库 %d 天即 %d star：注意投放/刷星" % (int(age), stars))
    if facts.get("archived"):
        flags.append("仓库已归档（archived）：官方已停止维护")
    if (facts.get("open_issues") or 0) > 200 and (facts.get("contributors") or 1) <= 1:
        flags.append("单人维护但 issue 积压 %d 条" % facts["open_issues"])

    readme_chars = (facts.get("readme") or {}).get("chars") or facts.get("chars") or 0
    if readme_chars and readme_chars < 300 and kinds.get("quantity"):
        flags.append("宣称体量很大但文档不足 300 字：交付与宣称不匹配")
    return flags


def _gaps(ctx) -> List[str]:
    gaps: List[str] = []
    facts = ctx["facts"]
    source = ctx["source"]
    if source == "video" and (facts.get("transcript_required")):
        gaps.append("视频没有字幕/文案：口播里的关键承诺无法核实")
    if source == "github":
        if not (facts.get("readme") or {}).get("chars"):
            gaps.append("没有拿到 README：无法核对功能宣称")
        if not (facts.get("tree") or {}).get("paths"):
            gaps.append("没有拿到文件树：无法核对「宣称的模块是否存在」")
        if not facts.get("license"):
            gaps.append("没有 LICENSE：法律上不能直接复用代码")
        if "releases" in facts and not facts.get("releases"):
            gaps.append("没有 Release 记录：没有可归档的版本快照")
    if source in ("web", "text", "video"):
        gaps.append("没有代码可供核对：只能核文案自洽性，不能核实现")
    gaps.append("没有实盘/生产使用记录：任何「能赚钱/能省时间」的结论都未被外部验证")
    return gaps


def _ceiling(ctx, now) -> Tuple[Optional[str], str]:
    """Hard caps — some facts should outrank the weighted sum.

    A rubric that lets 12 polished docs outvote "3 commits, then silence"
    rewards exactly the thing this tool exists to catch.
    """
    facts, kinds = ctx["facts"], claims_mod.counts(ctx["claims"])
    sig = _sig(facts)
    age = days_since(facts.get("created_at"), now)
    days_push = days_since(facts.get("pushed_at"), now)

    if ctx.get("source") != "github":
        return ("A", "内容类目标（文章/视频）：没有代码可审计，最高 A。要核实现，请给它引用的仓库或论文")

    commits = facts.get("commits") or 0
    contributors = facts.get("contributors") or 0

    caps: List[Tuple[str, str]] = []
    if commits and commits <= 5 and (age or 0) > 30:
        caps.append(("B", "共 %d 次提交、建库 %d 天：更像一次性发布，不是持续演进的代码库" % (commits, int(age or 0))))
    if sig.get("committed_node_modules") or sig.get("binary_count"):
        caps.append(("C", "交付物含闭源二进制或 node_modules：无法审计"))
    if kinds.get("free_open") and not facts.get("license") and not sig.get("has_license_file"):
        caps.append(("C", "宣称开源但仓库没有 LICENSE"))
    if kinds.get("money") and not any(w.lower() in _text(ctx).lower() for w in DISCLAIMER_WORDS):
        caps.append(("C", "出现收益类宣称却没有免责声明"))
    if contributors <= 1 and (days_push or 0) > 180:
        caps.append(("C", "单人维护且半年以上无更新"))
    if not caps:
        return None, ""
    order = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
    cap, reason = sorted(caps, key=lambda c: order[c[0]])[0]
    return cap, reason


def _insufficient(ctx) -> Tuple[bool, str]:
    facts = ctx["facts"]
    if facts.get("transcript_required"):
        return True, "视频没有字幕/文案：口播里的承诺一条都没法核"
    if ctx.get("source") in ("web", "video", "text") and len(ctx.get("text") or "") < 200:
        return True, "对象正文不足 200 字，打分没有意义"
    return False, ""


def score(ctx: Dict[str, Any], now: Optional[_dt.datetime] = None) -> Audit:
    now = now or utcnow()
    outcomes: List[Outcome] = []
    for check_id, dim, weight, fn in CHECKS:
        result = fn(ctx, now)
        if result is None:
            continue
        pct, evidence, redflag, action = result
        outcomes.append(
            Outcome(
                check_id=check_id,
                dim=dim,
                title=evidence,
                weight=weight,
                pct=clamp(pct),
                evidence=evidence,
                redflag=redflag,
                action=action,
            )
        )

    possible = sum(o.weight for o in outcomes) or 1.0
    earned = sum(o.weight * o.pct for o in outcomes)
    total = earned / possible * 100.0

    by_dim: Dict[str, List[float]] = {name: [0.0, 0.0] for name, _ in DIMENSIONS}
    for o in outcomes:
        by_dim.setdefault(o.dim, [0.0, 0.0])
        by_dim[o.dim][0] += o.weight * o.pct
        by_dim[o.dim][1] += o.weight

    grade, verdict = "D", GRADES[-1][2]
    for threshold, letter, sentence in GRADES:
        if total >= threshold:
            grade, verdict = letter, sentence
            break

    sentences = {letter: sentence for _, letter, sentence in GRADES}
    ranks = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
    cap, cap_reason = _ceiling(ctx, now)
    if cap and ranks[cap] < ranks[grade]:
        grade, verdict = cap, sentences[cap]

    insufficient, insufficient_reason = _insufficient(ctx)
    if ctx.get("source") != "github" and grade in CONTENT_VERDICTS:
        verdict = CONTENT_VERDICTS[grade]
    if insufficient:
        grade = "—"
        verdict = "证据不足，暂不定级：把字幕/原文补上再跑一次（--transcript）"

    redflags = [o.redflag for o in outcomes if o.redflag]
    redflags += _extra_redflags(ctx, now)
    if cap_reason:
        redflags.insert(0, "评分封顶：%s" % cap_reason)
    redflags = list(dict.fromkeys(redflags))

    checklist = []
    for o in sorted(outcomes, key=lambda x: x.weight * (1 - x.pct), reverse=True):
        if o.action and o.pct < 0.75:
            checklist.append(o.action)
    checklist = list(dict.fromkeys(checklist))[:8]

    dims = [
        (name, by_dim[name][0], by_dim[name][1]) for name, _ in DIMENSIONS
    ]

    return Audit(
        target=ctx.get("target") or ctx["facts"].get("full_name") or "",
        source=ctx.get("source", "unknown"),
        score=total,
        grade=grade,
        verdict=verdict,
        dims=dims,
        outcomes=outcomes,
        redflags=redflags,
        gaps=_gaps(ctx),
        checklist=checklist,
        claims=ctx["claims"],
        notes=ctx.get("notes") or [],
        facts=ctx["facts"],
        cap_reason=cap_reason,
        insufficient=insufficient,
        insufficient_reason=insufficient_reason,
    )


def build_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Turn an adapter payload into the rubric's input context."""
    facts = payload.get("facts") or {}
    text = ""
    for candidate in (
        (facts.get("readme") or {}).get("text"),
        facts.get("text"),
        facts.get("transcript"),
    ):
        if candidate:
            text = candidate
            break
    return {
        "source": payload.get("source", "unknown"),
        "target": payload.get("target", ""),
        "facts": facts,
        "text": text,
        "claims": claims_mod.extract(text),
        "notes": payload.get("notes") or [],
    }
