from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from paragliding_forecasts_ml.ingestion.igra.pipeline import fresh, resume
from paragliding_forecasts_ml.ingestion.igra.transport import BytesIgraResponse, IgraTransport

FIXTURES = Path(__file__).parents[2] / "fixtures" / "igra"


class FakeIgraTransport(IgraTransport):
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def request(self, url: str, *, method: str, headers=None):
        content = self.objects[url]
        content_type = "application/zip" if url.endswith(".zip") else "text/plain"
        return BytesIgraResponse(
            200,
            {
                "Content-Length": str(len(content)),
                "Content-Type": content_type,
                "ETag": f'"{len(content)}"',
                "Last-Modified": "Mon, 15 Sep 2025 00:00:00 GMT",
            },
            url,
            b"" if method == "HEAD" else content,
        )


def test_fake_fresh_then_offline_resume(tmp_path: Path) -> None:
    raw = _zip("BUM00015614-data.txt", (FIXTURES / "raw-selected-soundings.txt").read_bytes())
    derived = _zip("BUM00015614-drvd.txt", (FIXTURES / "derived-selected-soundings.txt").read_bytes())
    urls = {
        "https://www.ncei.noaa.gov/pub/data/igra/igra2-station-list.txt": (
            FIXTURES / "station-list-sample.txt"
        ).read_bytes(),
        "https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/access/data-por/BUM00015614-data.txt.zip": raw,
        "https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/access/derived-por/BUM00015614-drvd.txt.zip": derived,
        "https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/doc/igra2-data-format.txt": b"raw format\n",
        "https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/doc/igra2-derived-format.txt": b"derived format\n",
    }
    result = fresh(
        station_id="BUM00015614",
        dates_utc=("2025-08-02",),
        nominal_hours=(),
        archive="period-of-record",
        maximum_total_mib=1,
        project_root=tmp_path,
        transport=FakeIgraTransport(urls),
    )
    assert result["exit_code"] == 0
    resumed = resume(run_key=str(result["run_key"]), project_root=tmp_path)
    assert resumed["run_key"] == result["run_key"]
    assert resumed["network_mode"] == "cache_reuse"


def _zip(member_name: str, content: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(member_name, content)
    return output.getvalue()