"""GitHub adapter — collects the machine-checkable half of a claim audit.

Only the public REST API is used; no git binary, no cloning. Six small
requests at most, all of them cacheable, so a 60 req/h anonymous quota is
enough for real use.
"""
from __future__ import annotations

import base64
import re
from typing import Any, Dict, List, Optional

from .. import http
from ..util import days_since

API = "https://api.github.com"

_SCP = re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")
_HTTP = re.compile(
    r"https?://(?:www\.)?github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s?#]+)"
)
_SLUG = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)$")

BINARY_EXT = (".exe", ".dll", ".so", ".dylib", ".zip", ".7z", ".rar", ".whl", ".msi")
DEP_FILES = (
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "setup.py",
    "environment.yml",
    "pipfile",
    "go.mod",
    "cargo.toml",
)
DISCLAIMER_HINTS = ("不构成投资建议", "免责声明", "disclaimer", "not investment advice")
DEMO_HINTS = ("demo", "fixture", "sample", "example_data", "synthetic")


def parse_target(text: str) -> Optional[str]:
    """Accept a URL, a scp-style remote, or a bare ``owner/repo`` slug."""
    if not text:
        return None
    value = text.strip().strip("<>").strip()
    value = value.rstrip("/")
    m = _SCP.match(value)
    if m:
        return _slug(m.group("owner"), m.group("repo"))
    m = _HTTP.search(value)
    if m:
        return _slug(m.group("owner"), m.group("repo"))
    if "github.com" not in value:
        m = _SLUG.match(value)
        if m:
            return _slug(m.group("owner"), m.group("repo"))
    return None


def _slug(owner: str, repo: str) -> str:
    repo = repo.rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return "%s/%s" % (owner.strip(), repo.strip())


def _decode_readme(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    if not content:
        return ""
    try:
        raw = base64.b64decode(content.encode("ascii"), validate=False)
        return raw.decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _count_from_link(headers: Dict[str, str], fallback: int) -> int:
    link = headers.get("link") or ""
    match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link)
    if match:
        return int(match.group(1))
    return fallback


def _signals(paths: List[str]) -> Dict[str, Any]:
    lowered = [p.lower() for p in paths]
    root = {p.split("/")[0].lower() for p in lowered}

    tests = [
        p
        for p in lowered
        if p.startswith(("test/", "tests/", "spec/", "__tests__/"))
        or "/test_" in p
        or p.endswith("_test.py")
        or p.endswith(".test.js")
    ]
    ci = [p for p in lowered if p.startswith(".github/workflows/") or p in (
        ".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml", "circle.yml"
    )]
    node_modules = [p for p in lowered if p.startswith("node_modules/")]
    binaries = [p for p in paths if p.lower().endswith(BINARY_EXT)]
    docs = [p for p in lowered if p.endswith(".md")]
    code = [
        p
        for p in lowered
        if p.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp"))
    ]
    dep_files = [p for p in lowered if p.split("/")[-1] in DEP_FILES]
    demo = [p for p in lowered if any(h in p for h in DEMO_HINTS)]

    return {
        "has_tests": bool(tests),
        "test_files": len(tests),
        "has_ci": bool(ci),
        "has_license_file": bool(root & {"license", "license.md", "license.txt", "copying"}),
        "committed_node_modules": bool(node_modules),
        "node_modules_files": len(node_modules),
        "binaries": binaries[:10],
        "binary_count": len(binaries),
        "dependency_files": dep_files[:6],
        "dependency_count": len(dep_files),
        "has_demo_data": bool(demo),
        "docs_count": len(docs),
        "code_files": len(code),
        "top_dirs": sorted({p.split("/")[0] for p in paths if "/" in p})[:15],
        "file_count": len(paths),
    }


def probe(slug: str, token: Optional[str] = None, deep: bool = False) -> Dict[str, Any]:
    """Collect facts for ``owner/repo``. Partial failure is tolerated."""
    notes: List[str] = []
    repo_url = "%s/repos/%s" % (API, slug)
    repo, _ = http.get_json(repo_url, token=token)

    facts = {
        "full_name": repo.get("full_name") or slug,
        "description": repo.get("description") or "",
        "url": repo.get("html_url") or ("https://github.com/" + slug),
        "stars": repo.get("stargazers_count", 0) or 0,
        "forks": repo.get("forks_count", 0) or 0,
        "watchers": repo.get("subscribers_count", 0) or 0,
        "open_issues": repo.get("open_issues_count", 0) or 0,
        "created_at": repo.get("created_at"),
        "pushed_at": repo.get("pushed_at"),
        "updated_at": repo.get("updated_at"),
        "size_kb": repo.get("size", 0) or 0,
        "language": repo.get("language"),
        "license": ((repo.get("license") or {}) or {}).get("spdx_id"),
        "topics": repo.get("topics") or [],
        "archived": bool(repo.get("archived")),
        "default_branch": repo.get("default_branch") or "main",
        "commits": 0,
        "contributors": 0,
        "readme": {"path": "", "chars": 0, "headings": [], "text": ""},
        "tree": {"paths": [], "top_dirs": [], "file_count": 0},
        "signals": {},
    }

    # --- commits (1 request, count from the Link header) -------------------
    try:
        data, headers = http.get_json(
            "%s/repos/%s/commits?per_page=1" % (API, slug), token=token
        )
        facts["commits"] = _count_from_link(headers, len(data) if isinstance(data, list) else 0)
    except http.FetchError as exc:
        notes.append("提交数未取到：%s" % exc)

    # --- contributors ------------------------------------------------------
    try:
        data, _ = http.get_json(
            "%s/repos/%s/contributors?per_page=100&anon=1" % (API, slug), token=token
        )
        if isinstance(data, list):
            facts["contributors"] = len(data)
    except http.FetchError as exc:
        notes.append("贡献者未取到：%s" % exc)

    # --- readme ------------------------------------------------------------
    try:
        readme, _ = http.get(
            "%s/repos/%s/readme" % (API, slug),
            token=token,
            accept="application/vnd.github.raw",
        )
        if readme and not readme.lstrip().startswith("{"):
            facts["readme"] = {
                "path": "README",
                "chars": len(readme),
                "headings": re.findall(r"^#{1,6}\s+(.+)$", readme, flags=re.M),
                "text": readme,
            }
    except http.FetchError as exc:
        notes.append("README 未取到：%s" % exc)

    # --- file tree ---------------------------------------------------------
    try:
        tree, _ = http.get_json(
            "%s/repos/%s/git/trees/%s?recursive=1"
            % (API, slug, facts["default_branch"]),
            token=token,
        )
        paths = [n.get("path", "") for n in tree.get("tree", []) if n.get("type") == "blob"]
        facts["tree"] = {"paths": paths, "file_count": len(paths)}
        facts["signals"] = _signals(paths)
        facts["tree"]["top_dirs"] = facts["signals"].get("top_dirs", [])
    except http.FetchError as exc:
        notes.append("文件树未取到：%s" % exc)

    facts["age_days"] = days_since(facts["created_at"])
    facts["days_since_push"] = days_since(facts["pushed_at"])
    facts["disclaimer"] = any(h in facts["readme"]["text"].lower() for h in DISCLAIMER_HINTS)

    if deep:
        try:
            releases, _ = http.get_json(
                "%s/repos/%s/releases?per_page=5" % (API, slug), token=token
            )
            facts["releases"] = len(releases) if isinstance(releases, list) else 0
        except http.FetchError as exc:
            notes.append("Release 未取到：%s" % exc)

    return {
        "source": "github",
        "target": facts["full_name"],
        "url": facts["url"],
        "notes": notes,
        "facts": facts,
    }
