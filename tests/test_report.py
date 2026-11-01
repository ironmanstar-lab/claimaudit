"""Report + CLI tests — the contract is "always produces something readable"."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from claimaudit import cli, report, rubric
from tests.test_rubric import ctx_for, hype_facts, solid_facts

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "claimaudit", "fixtures")


def _tmpdir() -> str:
    """Workspace-local scratch dir — the OS temp dir may be sandboxed."""
    path = os.path.join(os.path.dirname(FIXTURE_DIR), "_test_tmp")
    os.makedirs(path, exist_ok=True)
    return path


def _cleanup(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def audit_of(facts):
    return rubric.score(ctx_for(facts))


class ReportTests(unittest.TestCase):
    def test_all_sections_present(self):
        text = report.render(audit_of(hype_facts()))
        for heading in ("## 一、评分卡", "## 二、宣称 vs 证据", "## 三、红旗",
                        "## 四、证据缺口", "## 五、30 分钟自检清单", "## 六、采集到的事实"):
            self.assertIn(heading, text)

    def test_markdown_tables_are_well_formed(self):
        text = report.render(audit_of(solid_facts()))
        for line in text.splitlines():
            if line.startswith("|"):
                self.assertTrue(line.endswith("|"), "表格行未闭合: %r" % line)

    def test_json_roundtrip(self):
        blob = report.render_json(audit_of(solid_facts()))
        data = json.loads(blob)
        self.assertEqual(data["source"], "github")
        self.assertIn("dims", data)
        self.assertIn("checks", data)
        self.assertIsInstance(data["score"], float)

    def test_empty_claims_do_not_crash(self):
        facts = solid_facts()
        facts["readme"]["text"] = "plain readme with no marketing words at all"
        text = report.render(audit_of(facts))
        self.assertIn("没有从文本里提取到明确宣称", text)

    def test_html_is_self_contained(self):
        html = report.render_html(audit_of(hype_facts()))
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertTrue(html.rstrip().endswith("</html>"))
        self.assertIn("<style>", html)
        self.assertIn("评分卡", html)
        self.assertIn("宣称 vs 证据", html)
        self.assertNotIn("<script", html)  # 不发外部/可执行内容

    def test_html_escapes_user_content(self):
        facts = solid_facts()
        facts["description"] = "<script>alert(1)</script>"
        facts["readme"]["text"] = "一键部署 <img src=x onerror=alert(1)>"
        html = report.render_html(audit_of(facts))
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<script>alert(1)</script>", html)


class CliTests(unittest.TestCase):
    def test_offline_fixture_runs(self):
        path = os.path.join(FIXTURE_DIR, "hype_case.json")
        self.assertTrue(os.path.exists(path), path)
        self.assertEqual(cli.run(["--offline", path]), 0)

    def test_json_flag_outputs_json(self):
        import contextlib
        import io

        buffer = io.StringIO()
        path = os.path.join(FIXTURE_DIR, "solid_case.json")
        with contextlib.redirect_stdout(buffer):
            code = cli.run(["--offline", path, "--json"])
        self.assertEqual(code, 0)
        json.loads(buffer.getvalue())

    def test_out_file(self):
        path = os.path.join(FIXTURE_DIR, "solid_case.json")
        tmp = _tmpdir()
        try:
            out = os.path.join(tmp, "r.md")
            self.assertEqual(cli.run(["--offline", path, "--out", out]), 0)
            with open(out, "r", encoding="utf-8") as fh:
                self.assertIn("验货报告", fh.read())
        finally:
            _cleanup(tmp)

    def test_fail_under_gate(self):
        path = os.path.join(FIXTURE_DIR, "hype_case.json")
        self.assertEqual(cli.run(["--offline", path, "--fail-under", "99"]), 4)

    def test_bad_fixture_returns_usage_code(self):
        tmp = _tmpdir()
        try:
            bad = os.path.join(tmp, "bad.json")
            with open(bad, "w", encoding="utf-8") as fh:
                fh.write('{"nope": 1}')
            self.assertEqual(cli.run(["--offline", bad]), 3)
        finally:
            _cleanup(tmp)

    def test_missing_target_returns_usage_code(self):
        self.assertEqual(cli.run([]), 3)


if __name__ == "__main__":
    unittest.main()
