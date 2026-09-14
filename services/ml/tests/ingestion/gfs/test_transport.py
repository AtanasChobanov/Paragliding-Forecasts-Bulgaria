from __future__ import annotations

import pytest

from paragliding_forecasts_ml.ingestion.gfs.transport import (
    GfsTransportError,
    HttpResponse,
    HttpTransport,
    RetryingTransport,
)


class FakeTransport(HttpTransport):
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def request(self, url, *, method="GET", headers=None):
        self.calls += 1
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_retries_429_with_retry_after_then_succeeds() -> None:
    fake = FakeTransport(
        (HttpResponse(429, {"Retry-After": "120"}, b""), HttpResponse(206, {}, b"ok"))
    )
    delays: list[float] = []
    transport = RetryingTransport(fake, sleeper=delays.append, random_uniform=lambda _a, _b: 0)

    assert transport.request("https://example.invalid").status == 206
    assert fake.calls == 2
    assert delays == [120.0]


def test_fails_fast_for_500_and_non_retryable_400() -> None:
    for status in (400, 500):
        fake = FakeTransport((HttpResponse(status, {}, b""),))
        transport = RetryingTransport(fake, sleeper=lambda _delay: None)
        assert transport.request("https://example.invalid").status == status
        assert fake.calls == 1


def test_stops_after_bounded_transient_retries() -> None:
    fake = FakeTransport(
        (HttpResponse(503, {}, b""), HttpResponse(503, {}, b""), HttpResponse(503, {}, b""))
    )
    transport = RetryingTransport(
        fake, sleeper=lambda _delay: None, random_uniform=lambda _a, _b: 0
    )

    with pytest.raises(GfsTransportError, match="exhausted"):
        transport.request("https://example.invalid")
    assert fake.calls == 3
