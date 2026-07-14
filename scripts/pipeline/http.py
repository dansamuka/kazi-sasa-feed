"""Shared resilient HTTP client for public job-source collectors."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass
class _Policy:
    source_key: str = "unknown"
    timeout_seconds: float = 30.0
    min_interval_seconds: float = 0.15
    cache_ttl_seconds: int = 900


class CachedJsonResponse:
    """Small requests.Response-compatible object for cached JSON payloads."""

    def __init__(self, payload: Any, status_code: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = json.dumps(payload, ensure_ascii=False)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"cached HTTP status {self.status_code}")

    def json(self) -> Any:
        return self._payload


class HttpClient:
    """Requests-compatible GET client with retries, throttling and JSON cache.

    The active source policy is set by CollectorRunner immediately before each
    sequential collector run. Existing collectors can keep calling `.get()`
    with a requests-like interface while gaining the shared safeguards.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        cache_enabled: bool = True,
        session=None,
        max_retries: int = 3,
        backoff_factor: float = 0.6,
    ):
        if session is None:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            session = requests.Session()
            retry = Retry(
                total=max_retries,
                connect=max_retries,
                read=max_retries,
                status=max_retries,
                backoff_factor=backoff_factor,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
                respect_retry_after_header=True,
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            session.headers.update({"User-Agent": "KaziSasaFeed/3.4 (+https://github.com/dansamuka/kazi-sasa-feed)"})
        self.session = session
        self.cache_enabled = cache_enabled
        self.cache_dir = cache_dir
        if self.cache_enabled and self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.policy = _Policy()
        self._last_request_by_host: dict[str, float] = {}
        self.stats = {"network_requests": 0, "cache_hits": 0, "throttle_sleeps": 0}

    def set_policy(
        self,
        source_key: str,
        timeout_seconds: float = 30.0,
        min_interval_seconds: float = 0.15,
        cache_ttl_seconds: int = 900,
    ) -> None:
        self.policy = _Policy(source_key, timeout_seconds, min_interval_seconds, cache_ttl_seconds)

    @staticmethod
    def _normalise_for_key(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): HttpClient._normalise_for_key(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, (list, tuple)):
            return [HttpClient._normalise_for_key(v) for v in value]
        return value

    def _cache_path(self, url: str, kwargs: dict) -> Path | None:
        if not self.cache_enabled or not self.cache_dir:
            return None
        key_payload = {
            "source": self.policy.source_key,
            "url": url,
            "params": self._normalise_for_key(kwargs.get("params") or {}),
            "headers": self._normalise_for_key(kwargs.get("headers") or {}),
        }
        digest = hashlib.sha256(json.dumps(key_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path | None) -> CachedJsonResponse | None:
        if path is None or not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > self.policy.cache_ttl_seconds:
            try:
                path.unlink()
            except OSError:
                pass
            return None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            self.stats["cache_hits"] += 1
            return CachedJsonResponse(cached["payload"], cached.get("status_code", 200), cached.get("headers"))
        except (OSError, ValueError, KeyError, TypeError):
            try:
                path.unlink()
            except OSError:
                pass
            return None

    def _write_cache(self, path: Path | None, response) -> None:
        if path is None or getattr(response, "status_code", 200) != 200:
            return
        try:
            payload = response.json()
            record = {
                "cached_at": time.time(),
                "status_code": getattr(response, "status_code", 200),
                "headers": dict(getattr(response, "headers", {}) or {}),
                "payload": payload,
            }
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            temp.replace(path)
        except (OSError, TypeError, ValueError):
            return

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        if not host or self.policy.min_interval_seconds <= 0:
            return
        last = self._last_request_by_host.get(host)
        now = time.monotonic()
        if last is not None:
            wait = self.policy.min_interval_seconds - (now - last)
            if wait > 0:
                self.stats["throttle_sleeps"] += 1
                time.sleep(wait)
        self._last_request_by_host[host] = time.monotonic()

    def get(self, url: str, **kwargs):
        cache_path = self._cache_path(url, kwargs)
        cached = self._read_cache(cache_path)
        if cached is not None:
            return cached

        self._throttle(url)
        kwargs["timeout"] = self.policy.timeout_seconds
        self.stats["network_requests"] += 1
        response = self.session.get(url, **kwargs)
        self._write_cache(cache_path, response)
        return response

    def post(self, url: str, **kwargs):
        """Requests-compatible POST used by public career-site search APIs.

        POST responses are deliberately not cached because request bodies may
        contain page cursors or short-lived bearer tokens. Retry behaviour is
        still inherited from the underlying requests session adapter.
        """
        self._throttle(url)
        kwargs["timeout"] = self.policy.timeout_seconds
        self.stats["network_requests"] += 1
        return self.session.post(url, **kwargs)

    def close(self) -> None:
        close = getattr(self.session, "close", None)
        if callable(close):
            close()
