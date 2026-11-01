"""Rubric tests — ordering, determinism, and graceful degradation."""
from __future__ import annotations

import datetime as dt
import unittest

from claimaudit import rubric
from claimaudit.util import utcnow


def iso(days_ago: float) -> str:
    moment = utcnow() - dt.timedelta(days=days_ago)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def solid_facts(**over):
    facts = {
        "full_name": "demo/solid",
        "url": "https://github.com/demo/solid",
        "stars": 2100,
        "forks": 190,
        "open_issues": 8,
        "created_at": iso(700),
        "pushed_at": iso(3),
        "updated_at": iso(1),
        "license": "MIT",
        "archived": False,
        "language": "Python",
        "commits": 480,
        "contributors": 15,
        "readme": {
            "chars": 5400,
            "headings": ["Install", "Quickstart", "Testing"],
            "text": (
                "# solid\n\n## Install\npip install solid\n\n## Quickstart\nsolid run\n\n"
                "## Testing\n41 tests, CI on 3.10-3.12. Benchmark on 50k rows: 2.1s.\n"
                "Comparison is a set diff over normalised signatures; sample data in demo/.\n"
                "`src/differ.py` and `src/report.py` implement it. See https://arxiv.org/abs/1234\n"
                "and https://example.com/spec and https://example.com/data\n"
            ),
        },
        "tree": {
            "paths": [
                "README.md", "LICENSE", "src/differ.py", "src/report.py",
                "tests/test_differ.py", "docs/cli.md", "docs/arch.md", "docs/test.md",
                ".github/workflows/ci.yml", "requirements.txt", "demo/a.csv",
            ],
            "file_count": 11,
        },
        "signals": {
            "has_tests": True, "test_files": 4, "has_ci": True, "has_license_file": True,
            "committed_node_modules": False, "binaries": [], "binary_count": 0,
            "dependency_files": ["requirements.txt"], "dependency_count": 1,
            "has_demo_data": True, "docs_count": 4, "code_files": 2, "file_count": 11,
        },
    }
    facts.update(over)
    return facts


def hype_facts(**over):
    facts = {
        "full_name": "demo/hype",
        "url": "https://github.com/demo/hype",
        "stars": 5200,
        "forks": 640,
        "open_issues": 300,
        "created_at": iso(15),
        "pushed_at": iso(11),
        "updated_at": iso(2),
        "license": None,
        "archived": False,
        "language": "Python",
        "commits": 4,
        "contributors": 1,
        "readme": {
            "chars": 700,
            "headings": ["神器", "功能"],
            "text": (
                "# 神器\n\n全网首发，唯一全自动，100% 无人值守，零风险躺赚。\n"
                "120+ 因子，一键部署，3 分钟上手。完全免费开源。月入 3 万。\n"
                "8 大模块：`factors/` `strategy/` `risk/` `deck/` `harness/` `etf/` `data/` `backtest/`\n"
                "加群领完整版，网盘下载 exe。\n"
            ),
        },
        "tree": {"paths": ["README.md", "run.exe"], "file_count": 2},
        "signals": {
            "has_tests": False, "test_files": 0, "has_ci": False, "has_license_file": False,
            "committed_node_modules": True, "binaries": ["run.exe"], "binary_count": 1,
            "dependency_files": [], "dependency_count": 0, "has_demo_data": False,
            "docs_count": 0, "code_files": 0, "file_count": 2,
        },
    }
    facts.update(over)
    return facts


def ctx_for(facts, source="github"):
    return rubric.build_context(
        {"source": source, "target": facts.get("full_name", "t"), "facts": facts, "notes": []}
    )


class ScoringTests(unittest.TestCase):
    def test_solid_beats_hype(self):
        solid = rubric.score(ctx_for(solid_facts()))
        hype = rubric.score(ctx_for(hype_facts()))
        self.assertGreater(solid.score, hype.score + 25)

    def test_grades_ordered(self):
        solid = rubric.score(ctx_for(solid_facts()))
        hype = rubric.score(ctx_for(hype_facts()))
        self.assertIn(solid.grade, ("S", "A"))
        self.assertIn(hype.grade, ("C", "D"))

    def test_scores_are_bounded(self):
        for audit in (
            rubric.score(ctx_for(solid_facts())),
            rubric.score(ctx_for(hype_facts())),
        ):
            self.assertGreaterEqual(audit.score, 0.0)
            self.assertLessEqual(audit.score, 100.0)

    def test_deterministic(self):
        fixed = dt.datetime(2026, 11, 1, 12, 0, 0)
        context = ctx_for(solid_facts())
        first = rubric.score(context, now=fixed).score
        second = rubric.score(context, now=fixed).score
        self.assertEqual(round(first, 4), round(second, 4))

    def test_redflags_are_reported(self):
        audit = rubric.score(ctx_for(hype_facts()))
        joined = " ".join(audit.redflags)
        self.assertIn("收益", joined)
        self.assertIn("二进制", joined)

    def test_checklist_is_actionable(self):
        audit = rubric.score(ctx_for(hype_facts()))
        self.assertGreaterEqual(len(audit.checklist), 3)
        self.assertTrue(all(isinstance(item, str) and item for item in audit.checklist))

    def test_web_context_skips_repo_checks(self):
        payload = {
            "source": "web",
            "target": "某篇安利文",
            "facts": {
                "title": "某篇安利文",
                "chars": 1200,
                "text": "这个工具一键搞定，100% 免费，月入 3 万，加群领取。",
                "links": [],
                "promo_hits": ["加群"],
                "headings": [],
            },
            "notes": [],
        }
        audit = rubric.score(rubric.build_context(payload))
        self.assertLess(audit.score, 70)
        ids = {o.check_id for o in audit.outcomes}
        self.assertNotIn("tests", ids)  # repo-only check dropped
        self.assertIn("promo", ids)

    def test_video_without_transcript_flags_the_gap(self):
        payload = {
            "source": "video",
            "target": "抖音视频",
            "facts": {
                "platform": "douyin", "title": "", "transcript": "", "chars": 0,
                "transcript_required": True, "links": [], "promo_hits": [],
            },
            "notes": [],
        }
        audit = rubric.score(rubric.build_context(payload))
        self.assertTrue(any("字幕" in gap for gap in audit.gaps))

    def test_video_without_transcript_is_not_graded(self):
        payload = {
            "source": "video",
            "target": "抖音视频",
            "facts": {
                "platform": "douyin", "title": "", "transcript": "", "chars": 0,
                "transcript_required": True, "links": [], "promo_hits": [],
            },
            "notes": [],
        }
        audit = rubric.score(rubric.build_context(payload))
        self.assertTrue(audit.insufficient)
        self.assertEqual(audit.grade, "—")

    def test_dump_repo_is_capped(self):
        facts = solid_facts(commits=3, created_at=iso(120), contributors=1)
        audit = rubric.score(ctx_for(facts))
        self.assertEqual(audit.grade, "B")
        self.assertIn("一次性发布", audit.cap_reason)

    def test_web_never_gets_s_grade(self):
        payload = {
            "source": "web",
            "target": "一篇很好的文章",
            "facts": {
                "title": "很好的文章",
                "chars": 4000,
                "text": "样本 2019-2025，回测夏普 1.2，回撤 8%，数据集公开，复现脚本在 https://a.com "
                        "和 https://b.com 与 https://c.com。方法见 https://d.com 的论文。",
                "links": ["https://a.com", "https://b.com", "https://c.com"],
                "promo_hits": [],
                "headings": [],
            },
            "notes": [],
        }
        audit = rubric.score(rubric.build_context(payload))
        self.assertNotEqual(audit.grade, "S")
        self.assertIn("内容类目标", audit.cap_reason)

    def test_dimensions_always_present(self):
        audit = rubric.score(ctx_for(solid_facts()))
        names = [name for name, _, _ in audit.dims]
        self.assertEqual(
            names, ["可验证性", "证据密度", "宣称一致", "维护可信", "风险敞口", "上手成本"]
        )


if __name__ == "__main__":
    unittest.main()
