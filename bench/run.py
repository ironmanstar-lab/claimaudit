"""黄金集跑分器：改完代码先跑这个，再看别的。

用法：python bench/run.py [--json] [--verbose]
退出码：0 全绿 / 1 有样本不符预期
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from claimaudit import rubric  # noqa: E402

GOLDEN = os.path.join(HERE, "golden")
_DAYS_AGO = re.compile(r"^@-(\d+)d$")


def _resolve(value):
    """把 '@-80d' 换成本次运行时刻的相对日期 —— 样本永不过期。"""
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v) for v in value]
    if isinstance(value, str):
        m = _DAYS_AGO.match(value)
        if m:
            moment = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(
                days=int(m.group(1))
            )
            return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    return value


def load_all():
    items = []
    for name in sorted(os.listdir(GOLDEN)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(GOLDEN, name), "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        expect = payload.pop("_expect", {})
        payload["facts"] = _resolve(payload.get("facts") or {})
        items.append((name[:-5], payload, expect))
    return items


def check(audit, expect) -> str:
    grades = expect.get("grades") or []
    if audit.insufficient:
        return "PASS" if "—" in grades or not grades else "FAIL"
    if grades and audit.grade not in grades:
        return "FAIL"
    if "min_score" in expect and audit.score < expect["min_score"]:
        return "FAIL"
    if "max_score" in expect and audit.score > expect["max_score"]:
        return "FAIL"
    return "PASS"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    rows, failures = [], 0
    for name, payload, expect in load_all():
        audit = rubric.score(rubric.build_context(payload))
        result = check(audit, expect)
        if result == "FAIL":
            failures += 1
        rows.append(
            {
                "name": name,
                "grade": audit.grade,
                "score": round(audit.score, 1),
                "expect": "/".join(expect.get("grades", [])) or "-",
                "result": result,
                "redflags": audit.redflags,
            }
        )

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print("%-18s %-6s %-7s %-8s %s" % ("样本", "等级", "分数", "期望", "结果"))
        print("-" * 52)
        for row in rows:
            print(
                "%-18s %-6s %-7s %-8s %s"
                % (row["name"], row["grade"], "%.1f" % row["score"], row["expect"], row["result"])
            )
            if args.verbose and row["result"] == "FAIL":
                for flag in row["redflags"]:
                    print("    └─ %s" % flag)
        print("-" * 52)
        print("%d 个样本，%d 个不符预期" % (len(rows), failures))

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
