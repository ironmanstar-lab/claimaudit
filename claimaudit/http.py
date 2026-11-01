"""HTTP layer: one place that knows how to talk to the outside world.

Design notes
------------
* stdlib only (urllib) — no requests, no certifi, nothing to install.
* every response is cached under a local cache dir so repeated audits of the
  same target cost zero requests (public GitHub API is 60 req/h unauthenticated).
* SSL failures fall back to an unverified context *once*, because corporate
  and campus networks in CN routinely MITM the chain. The fallback is recorded
  in ``warnings`` so a report never silently pretends the channel was clean.
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

DEFAULT_UA = (
    "ClaimAudit/0.1 (+https://github.com/claimaudit; claim-vs-evidence audit)"
)

warnings = []  # type: list


class FetchError(Exception):
    """Base class for every network-level failure."""


class NotFound(FetchError):
    """404 — the thing the user pointed at does not exist."""


class RateLimited(FetchError):
    """403 with an exhausted quota; ``reset_epoch`` tells when it clears."""

    def __init__(self, message: str, reset_epoch: Optional[int] = None):
        super().__init__(message)
        self.reset_epoch = reset_epoch


def cache_dir() -> str:
    override = os.environ.get("CLAIMAUDIT_CACHE")
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "claimaudit")


def _cache_file(url: str, extra: str = "") -> str:
    digest = hashlib.sha1((url + "|" + extra).encode("utf-8")).hexdigest()
    return os.path.join(cache_dir(), digest + ".json")


def _read_cache(path: str, ttl: int) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
    except (OSError, ValueError):
        return None
    if ttl and time.time() - blob.get("ts", 0) > ttl:
        return None
    return blob


def _write_cache(path: str, status: int, headers: Dict[str, str], body: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(
                {"ts": time.time(), "status": status, "headers": headers, "body": body},
                fh,
            )
    except OSError:
        pass  # a read-only home directory must not break the audit


def _open(request: urllib.request.Request, timeout: int):
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except ssl.SSLError:
        msg = "SSL 校验失败，已降级为不校验证书（企业/校园网常见），结果仍可用但通道不可信"
        if msg not in warnings:
            warnings.append(msg)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return urllib.request.urlopen(request, timeout=timeout, context=ctx)


def get(
    url: str,
    *,
    token: Optional[str] = None,
    timeout: int = 15,
    cache: bool = True,
    ttl: int = 1800,
    accept: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    """GET a URL and return ``(body_text, headers)``.

    Headers are lower-cased so callers can simply do ``headers.get("link")``.
    """
    extra = (accept or "") + ("|token" if token else "")
    path = _cache_file(url, extra)
    if cache:
        blob = _read_cache(path, ttl)
        if blob is not None:
            return blob.get("body", ""), blob.get("headers", {})

    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": accept or "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)

    try:
        with _open(request, timeout) as resp:
            raw = resp.read()
            lowered = {k.lower(): v for k, v in dict(resp.headers).items()}
            body = raw.decode("utf-8", errors="replace")
            if cache:
                _write_cache(path, getattr(resp, "status", 200), lowered, body)
            return body, lowered
    except urllib.error.HTTPError as exc:
        status = getattr(exc, "code", 0)
        hdrs = {k.lower(): v for k, v in dict(getattr(exc, "headers", {}) or {}).items()}
        if status == 404:
            raise NotFound(_describe(url, status))
        if status in (403, 429) and hdrs.get("x-ratelimit-remaining") == "0":
            reset = hdrs.get("x-ratelimit-reset")
            raise RateLimited(
                "GitHub API 配额用尽（未认证 60 次/小时）。%s 后恢复，"
                "或设置 CLAIMAUDIT_TOKEN / --token 提高上限。"
                % _until(reset),
                int(reset) if reset and reset.isdigit() else None,
            )
        raise FetchError(_describe(url, status) + " " + _clip(str(exc.reason)))
    except urllib.error.URLError as exc:
        raise FetchError("%s 无法访问：%s" % (url, _clip(str(exc.reason))))
    except TimeoutError:
        raise FetchError("%s 请求超时（%ss）" % (url, timeout))


def get_json(
    url: str,
    *,
    token: Optional[str] = None,
    timeout: int = 15,
    cache: bool = True,
    ttl: int = 1800,
) -> Tuple[Any, Dict[str, str]]:
    body, headers = get(
        url,
        token=token,
        timeout=timeout,
        cache=cache,
        ttl=ttl,
        accept="application/vnd.github+json, application/json",
    )
    try:
        return json.loads(body), headers
    except ValueError:
        raise FetchError("%s 返回的不是 JSON（可能是镜像/登录墙）" % url)


def _until(reset_epoch: Optional[str]) -> str:
    if not reset_epoch or not reset_epoch.isdigit():
        return "一小时"
    mins = max(1, int((int(reset_epoch) - time.time()) / 60))
    return "%d 分钟" % mins


def _describe(url: str, status: int) -> str:
    if status == 404:
        return "%s 不存在（404）—— 仓库名拼错、已删除或已转私有" % url
    if status == 403:
        return "%s 被拒绝（403）" % url
    return "%s 返回 HTTP %s" % (url, status)


def _clip(text: str, limit: int = 180) -> str:
    text = (text or "").replace("\n", " ")
    return text[:limit]


def join_url(base: str, *parts: str) -> str:
    url = base.rstrip("/")
    for part in parts:
        url += "/" + urllib.parse.quote(str(part).strip("/"))
    return url


def ensure_utf8_stdout() -> None:
    """Windows consoles default to cp936; reports contain CJK + arrows."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
