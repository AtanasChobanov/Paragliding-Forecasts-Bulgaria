"""Small injectable HTTP transport with conservative GFS retry behaviour."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GfsTransportError(RuntimeError):
    """Network failure after the permitted retry policy."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def header(self, name: str) -> str | None:
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return None


class HttpTransport:
    """Protocol-like base kept deliberately simple for deterministic fake tests."""

    def request(
        self, url: str, *, method: str = "GET", headers: Mapping[str, str] | None = None
    ) -> HttpResponse:
        raise NotImplementedError


class UrllibTransport(HttpTransport):
    """Production transport; callers validate status/body before persistence."""

    def request(
        self, url: str, *, method: str = "GET", headers: Mapping[str, str] | None = None
    ) -> HttpResponse:
        request = Request(url, method=method, headers=dict(headers or {}))
        try:
            with urlopen(request, timeout=30) as response:
                return HttpResponse(
                    response.status, dict(response.headers.items()), response.read()
                )
        except HTTPError as error:
            return HttpResponse(
                error.code, dict(error.headers.items()) if error.headers else {}, error.read()
            )
        except (TimeoutError, URLError, OSError) as error:
            raise GfsTransportError("GFS transport request failed.") from error


@dataclass(frozen=True)
class RetryPolicy:
    """No more than an initial attempt and two conservative retries."""

    max_attempts: int = 3
    maximum_retry_after_seconds: int = 900


def _retry_delay(response: HttpResponse | None, attempt: int) -> float | None:
    if response is None:
        return (30.0, 120.0)[attempt - 1]
    if response.status == 408:
        return 60.0 if attempt == 1 else None
    if response.status in {502, 503, 504}:
        return (30.0, 120.0)[attempt - 1]
    if response.status == 429:
        return (120.0, 600.0)[attempt - 1]
    return None


def retry_after_seconds(value: str | None, *, now: Callable[[], float] = time.time) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - now())
        except (TypeError, ValueError, IndexError):
            return None


class RetryingTransport(HttpTransport):
    """Retries only clearly transient source failures; all other statuses return once."""

    def __init__(
        self,
        upstream: HttpTransport,
        *,
        policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.upstream = upstream
        self.policy = policy or RetryPolicy()
        self.sleeper = sleeper
        self.random_uniform = random_uniform

    def request(
        self, url: str, *, method: str = "GET", headers: Mapping[str, str] | None = None
    ) -> HttpResponse:
        for attempt in range(1, self.policy.max_attempts + 1):
            response: HttpResponse | None = None
            try:
                response = self.upstream.request(url, method=method, headers=headers)
            except GfsTransportError:
                if attempt == self.policy.max_attempts:
                    raise
            else:
                if response.status not in {408, 429, 502, 503, 504}:
                    return response
                if attempt == self.policy.max_attempts:
                    raise GfsTransportError(
                        f"GFS transient HTTP {response.status} exhausted retries."
                    )
            delay = _retry_delay(response, attempt)
            if delay is None:
                return response  # pragma: no cover - defensive; statuses above define delays
            server_delay = retry_after_seconds(response.header("Retry-After")) if response else None
            if server_delay is not None:
                delay = max(delay, server_delay)
            if delay > self.policy.maximum_retry_after_seconds:
                raise GfsTransportError("GFS Retry-After exceeds the configured safe wait cap.")
            self.sleeper(delay + self.random_uniform(0.0, min(15.0, delay * 0.1)))
        raise AssertionError("Unreachable retry state.")
