"""Command line entry point.

Exit codes
----------
0  report produced
2  network / source failure (nothing to score)
3  bad usage (target missing, unknown file, empty fixture)
4  score below --fail-under (CI gate)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

from . import __version__, http, report, rubric
from . import sources
from .sources import github as gh

EXIT_OK, EXIT_FETCH, EXIT_USAGE, EXIT_GATE = 0, 2, 3, 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claimaudit",
        description="宣称 vs 证据：给「开源神器 / AI 教程 / 致富方法」做一份可复现的尽调报告。",
        epilog="例：claimaudit https://github.com/owner/repo",
    )
    parser.add_argument("target", nargs="?", help="GitHub 仓库 URL / 网页 URL / 视频分享链接 / 本地文件")
    parser.add_argument("--transcript", metavar="PATH", help="视频或口播的文案（srt/txt/md），补上后才可能核实口播承诺")
    parser.add_argument("--json", action="store_true", help="输出机器可读的 JSON（给 agent 用）")
    parser.add_argument("--html", action="store_true", help="输出自包含 HTML（发给不装 Python 的人看）")
    parser.add_argument("-o", "--out", metavar="PATH", help="把报告写到文件")
    parser.add_argument("--token", metavar="TOKEN", help="GitHub token（不传则读 CLAIMAUDIT_TOKEN，再退回匿名 60 次/小时）")
    parser.add_argument("--deep", action="store_true", help="多花 1-2 个请求，额外核对 Release 记录")
    parser.add_argument("--offline", metavar="FIXTURE.json", help="用本地快照打分，不联网（演示 / 测试用）")
    parser.add_argument("--no-cache", action="store_true", help="不复用本地响应缓存")
    parser.add_argument("--fail-under", type=float, metavar="N", help="分数低于 N 时返回退出码 4（可用于 CI 卡依赖）")
    parser.add_argument("--version", action="version", version="claimaudit %s" % __version__)
    return parser


def resolve_token(args) -> Optional[str]:
    return args.token or os.environ.get("CLAIMAUDIT_TOKEN") or os.environ.get("GITHUB_TOKEN")


def load_payload(args) -> Dict[str, Any]:
    if args.offline:
        with open(args.offline, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict) or "facts" not in payload:
            raise ValueError("fixture 结构不对：至少需要 {\"source\", \"target\", \"facts\"}")
        return payload

    target = (args.target or "").strip()
    if not target:
        raise ValueError("给个目标：仓库 URL、网页链接、视频链接，或本地文件路径")

    token = resolve_token(args)

    if os.path.exists(target) and sources.textfile.looks_like_text(target):
        return sources.textfile.probe(target)

    slug = gh.parse_target(target)
    if slug and not sources.textfile.looks_like_text(target):
        return gh.probe(slug, token=token, deep=args.deep)
    if sources.textfile.looks_like_text(target) and not target.startswith("http"):
        raise ValueError("本地文件不存在：%s" % target)

    transcript = ""
    if args.transcript:
        with open(args.transcript, "r", encoding="utf-8", errors="replace") as fh:
            transcript = fh.read()

    if sources.video.detect(target):
        return sources.video.probe(target, transcript=transcript or None, token=token)

    if target.startswith(("http://", "https://")):
        payload = sources.web.probe(target, token=token)
        if transcript:
            payload["facts"]["text"] = transcript
            payload["facts"]["chars"] = len(transcript)
        return payload

    raise ValueError("认不出这个目标：既不是仓库、网页、视频链接，也不是本地文本文件")


def run(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    http.ensure_utf8_stdout()

    try:
        payload = load_payload(args)
    except http.NotFound as exc:
        print("✗ %s" % exc, file=sys.stderr)
        return EXIT_FETCH
    except http.RateLimited as exc:
        print("✗ %s" % exc, file=sys.stderr)
        return EXIT_FETCH
    except (http.FetchError, OSError) as exc:
        print("✗ 取数失败：%s" % exc, file=sys.stderr)
        return EXIT_FETCH
    except (ValueError, json.JSONDecodeError) as exc:
        print("✗ %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    ctx = rubric.build_context(payload)
    audit = rubric.score(ctx)
    audit.notes = list(audit.notes) + list(http.warnings)

    if args.json:
        body = report.render_json(audit)
    elif args.html or (args.out or "").lower().endswith((".html", ".htm")):
        body = report.render_html(audit)
    else:
        body = report.render(audit)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(body + ("\n" if not body.endswith("\n") else ""))
        if not args.json:
            print("✓ 报告已写入 %s（%s %.1f/100）" % (args.out, audit.grade, audit.score))
    else:
        print(body)

    if args.fail_under is not None and audit.score < args.fail_under:
        print("✗ 得分 %.1f 低于门槛 %.1f" % (audit.score, args.fail_under), file=sys.stderr)
        return EXIT_GATE
    return EXIT_OK


def main() -> None:
    try:
        code = run()
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
