"""Tests for the source adapters — no network calls, pure parsing logic."""
from __future__ import annotations

import unittest

from claimaudit.sources import github, video


class ParseTargetTests(unittest.TestCase):
    def test_https_url(self):
        self.assertEqual(
            github.parse_target("https://github.com/psf/requests"), "psf/requests"
        )

    def test_url_with_subpath_and_query(self):
        self.assertEqual(
            github.parse_target("https://github.com/psf/requests/tree/main/src?tab=readme"),
            "psf/requests",
        )

    def test_dot_git_suffix(self):
        self.assertEqual(
            github.parse_target("https://github.com/psf/requests.git"), "psf/requests"
        )

    def test_scp_style(self):
        self.assertEqual(
            github.parse_target("git@github.com:psf/requests.git"), "psf/requests"
        )

    def test_bare_slug(self):
        self.assertEqual(github.parse_target("psf/requests"), "psf/requests")

    def test_rejects_noise(self):
        self.assertIsNone(github.parse_target("hello world"))
        self.assertIsNone(github.parse_target(""))
        self.assertIsNone(github.parse_target(None))


class SignalTests(unittest.TestCase):
    PATHS = [
        "README.md",
        "LICENSE",
        "src/app.py",
        "tests/test_app.py",
        ".github/workflows/ci.yml",
        "node_modules/x/index.js",
        "build/tool.exe",
        "demo/sample.csv",
        "docs/a.md",
        "docs/b.md",
        "requirements.txt",
    ]

    def test_detects_hygiene_signals(self):
        sig = github._signals(self.PATHS)
        self.assertTrue(sig["has_tests"])
        self.assertTrue(sig["has_ci"])
        self.assertTrue(sig["has_license_file"])
        self.assertTrue(sig["committed_node_modules"])
        self.assertEqual(sig["binary_count"], 1)
        self.assertTrue(sig["has_demo_data"])
        self.assertGreaterEqual(sig["docs_count"], 3)
        self.assertIn("requirements.txt", sig["dependency_files"])

    def test_clean_repo_has_no_flags(self):
        sig = github._signals(["README.md", "LICENSE", "src/a.py"])
        self.assertFalse(sig["has_tests"])
        self.assertFalse(sig["has_ci"])
        self.assertFalse(sig["committed_node_modules"])
        self.assertEqual(sig["binary_count"], 0)


class VideoDetectTests(unittest.TestCase):
    def test_douyin(self):
        self.assertEqual(video.detect("https://v.douyin.com/qSlB5fg5kdI/"), "douyin")

    def test_bilibili(self):
        self.assertEqual(video.detect("https://b23.tv/abcd"), "bilibili")

    def test_unknown(self):
        self.assertIsNone(video.detect("https://example.com/post/1"))

    def test_video_id_extraction(self):
        self.assertEqual(
            video._video_id("https://www.bilibili.com/video/BV1xx411c7mD"), "BV1xx411c7mD"
        )


if __name__ == "__main__":
    unittest.main()
