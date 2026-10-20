"""Minimal synchronous client for a `strands-decider serve` endpoint (POST /v1/systemone).

stdlib-only on purpose, so the pattern adds no dependency beyond pydantic. There is no
fallback: if the server is unreachable or answers malformed JSON the client raises, and
the gate turns that into a fail-closed decision. It never fabricates an answer.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

DEFAULT_URL = os.environ.get("STRANDS_DECIDER_URL", "http://127.0.0.1:8099")


class DeciderError(RuntimeError):
    status = "error"


class DeciderUnavailable(DeciderError):
    status = "unavailable"


class DeciderTimeout(DeciderError):
    status = "timeout"


class DeciderMalformedResponse(DeciderError):
    status = "malformed"


class DeciderVersionMismatch(DeciderError):
    status = "version_mismatch"


class DeciderClient:
    def __init__(self, url: str = DEFAULT_URL, timeout_s: float = 120.0, retries: int = 1,
                 backoff_s: float = 1.0, expected_checkpoint: str | None = None,
                 auth_token: str | None = None) -> None:
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s
        self.retries = max(0, retries)
        self.backoff_s = backoff_s
        self.expected_checkpoint = expected_checkpoint
        self.auth_token = auth_token or os.environ.get("STRANDS_DECIDER_TOKEN")
        self._health: dict[str, Any] | None = None

    def _headers(self) -> dict[str, str]:
        h = {"content-type": "application/json"}
        if self.auth_token:
            h["authorization"] = f"Bearer {self.auth_token}"
        return h

    def health(self, refresh: bool = False) -> dict[str, Any]:
        if self._health is not None and not refresh:
            return self._health
        req = urllib.request.Request(f"{self.url}/health", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DeciderUnavailable(f"no Decider server at {self.url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DeciderMalformedResponse(f"/health returned non-JSON: {exc}") from exc
        if self.expected_checkpoint and data.get("checkpoint") != self.expected_checkpoint:
            raise DeciderVersionMismatch(
                f"server serves {data.get('checkpoint')!r}, expected {self.expected_checkpoint!r}")
        self._health = data
        return data

    def ask(self, state: str, questions: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
        """Return the raw server payload: {model, answers, usage, latency_ms}."""
        body = json.dumps({"state": state, "questions": dict(questions)}).encode()
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(f"{self.url}/v1/systemone", data=body,
                                         headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                    payload = json.loads(r.read())
                return _validate_payload(payload, questions)
            except TimeoutError as exc:
                last = DeciderTimeout(f"Decider timed out after {self.timeout_s}s")
                last.__cause__ = exc
            except urllib.error.HTTPError as exc:
                # 4xx is a request problem; retrying will not help.
                if 400 <= exc.code < 500:
                    raise DeciderMalformedResponse(f"Decider rejected request: HTTP {exc.code}") from exc
                last = DeciderUnavailable(f"Decider HTTP {exc.code}")
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, TimeoutError):
                    last = DeciderTimeout(f"Decider timed out after {self.timeout_s}s")
                else:
                    last = DeciderUnavailable(f"no Decider server at {self.url}: {exc.reason}")
            except json.JSONDecodeError as exc:
                raise DeciderMalformedResponse(f"Decider returned non-JSON: {exc}") from exc
            if attempt < self.retries:
                time.sleep(self.backoff_s * (2 ** attempt))
        assert last is not None
        raise last


def _validate_payload(payload: Any, questions: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
        raise DeciderMalformedResponse("response has no 'answers' object")
    answers = payload["answers"]
    for name, q in questions.items():
        a = answers.get(name)
        if not isinstance(a, dict):
            raise DeciderMalformedResponse(f"missing answer for '{name}'")
        kind = q["type"]
        if kind not in a:
            raise DeciderMalformedResponse(f"answer '{name}' lacks '{kind}' field")
        if kind == "noul":
            v = a["noul"]
            if not isinstance(v, (int, float)) or not 0.0 <= float(v) <= 1.0:
                raise DeciderMalformedResponse(f"noul '{name}' out of range: {v!r}")
        if kind == "choice" and a["choice"] not in q.get("criteria", {}):
            raise DeciderMalformedResponse(f"choice '{name}' returned unknown option {a['choice']!r}")
    return payload
