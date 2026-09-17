from paragliding_forecasts_ml.ingestion.igra.transport import BytesIgraResponse, IgraTransport, RetryingIgraTransport


class TransientTransport(IgraTransport):
    def __init__(self) -> None:
        self.calls = 0

    def request(self, url: str, *, method: str, headers=None):
        self.calls += 1
        if self.calls == 1:
            return BytesIgraResponse(503, {}, url, b"")
        return BytesIgraResponse(200, {}, url, b"")


def test_retry_retries_a_transient_response() -> None:
    upstream = TransientTransport()
    response = RetryingIgraTransport(upstream, sleeper=lambda _: None, random_uniform=lambda _a, _b: 0).request(
        "https://ncei.noaa.gov/example", method="HEAD"
    )
    assert response.status == 200
    assert upstream.calls == 2