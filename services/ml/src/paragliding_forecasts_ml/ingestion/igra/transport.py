"""Injectable streaming HTTPS transport with the IGRA retry policy."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class IgraTransportError(RuntimeError):
    """A permitted source request failed or exhausted bounded retries."""


@dataclass
class IgraHttpResponse:
    """A response whose body remains streamable until the caller consumes or closes it."""

    status: int
    headers: Mapping[str, str]
    final_url: str
    body: object

    def header(self, name: str) -> str | None:
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return None

    def iter_chunks(self, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        try:
            while chunk := self.body.read(chunk_size):
                yield chunk
        finally:
            self.close()

    def close(self) -> None:
        close = getattr(self.body, "close", None)
        if close is not None:
            close()


class IgraTransport:
    """Small fakeable transport surface; a resume path must never construct it."""

    def request(
        self, url: str, *, method: str, headers: Mapping[str, str] | None = None
    ) -> IgraHttpResponse:
        raise NotImplementedError


class UrllibIgraTransport(IgraTransport):
    """Standard-library production transport; response bytes are never collected here."""

    def request(
        self, url: str, *, method: str, headers: Mapping[str, str] | None = None
    ) -> IgraHttpResponse:
        request = Request(url, method=method, headers=dict(headers or {}))
        try:
            response = urlopen(request, timeout=30)
            return IgraHttpResponse(
                status=response.status,
                headers=dict(response.headers.items()),
                final_url=response.geturl(),
                body=response,
            )
        except HTTPError as error:
            return IgraHttpResponse(
                status=error.code,
                headers=dict(error.headers.items()) if error.headers else {},
                final_url=error.geturl(),
                body=error,
            )
        except (TimeoutError, URLError, OSError) as error:
            raise IgraTransportError("IGRA transport request failed.") from error


@dataclass(frozen=True)
class IgraRetryPolicy:
    maximum_attempts: int = 3
    maximum_retry_after_seconds: int = 900


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


class RetryingIgraTransport(IgraTransport):
    """Retry only the exact transient HTTP statuses accepted by the source policy."""

    def __init__(
        self,
        upstream: IgraTransport,
        *,
        policy: IgraRetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.upstream = upstream
        self.policy = policy or IgraRetryPolicy()
        self.sleeper = sleeper
        self.random_uniform = random_uniform

    def request(
        self, url: str, *, method: str, headers: Mapping[str, str] | None = None
    ) -> IgraHttpResponse:
        for attempt in range(1, self.policy.maximum_attempts + 1):
            response: IgraHttpResponse | None = None
            try:
                response = self.upstream.request(url, method=method, headers=headers)
            except IgraTransportError:
                if attempt == self.policy.maximum_attempts:
                    raise
            else:
                if response.status not in {408, 429, 502, 503, 504}:
                    return response
                response.close()
                if attempt == self.policy.maximum_attempts:
                    raise IgraTransportError(
                        f"IGRA transient HTTP {response.status} exhausted retries."
                    )
            delay = (30.0, 120.0)[attempt - 1]
            retry_after = retry_after_seconds(response.header("Retry-After")) if response else None
            if retry_after is not None:
                delay = max(delay, retry_after)
            if delay > self.policy.maximum_retry_after_seconds:
                raise IgraTransportError("IGRA Retry-After exceeds the safe wait cap.")
            self.sleeper(delay + self.random_uniform(0.0, min(15.0, delay * 0.1)))
        raise AssertionError("Unreachable IGRA retry state.")


class BytesIgraResponse(IgraHttpResponse):
    """Convenience response for deterministic fake transports in unit tests."""

    def __init__(self, status: int, headers: Mapping[str, str], url: str, content: bytes) -> None:
        super().__init__(status=status, headers=headers, final_url=url, body=BytesIO(content))
