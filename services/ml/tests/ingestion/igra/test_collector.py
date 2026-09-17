import zipfile
from pathlib import Path

from paragliding_forecasts_ml.ingestion.igra.collector import _verify_zip_payloads
from paragliding_forecasts_ml.ingestion.igra.inventory import load_source_policy
from paragliding_forecasts_ml.ingestion.igra.models import IgraRemoteObject


def test_zip_guard_accepts_only_the_expected_member(tmp_path: Path) -> None:
    payload = tmp_path / "payloads"
    payload.mkdir()
    archive_path = payload / "raw.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BUM00015614-data.txt", b"# record\n")
    item = IgraRemoteObject(
        artifact_key="period_of_record_zip",
        url="https://ncei.noaa.gov/raw.zip",
        final_url="https://ncei.noaa.gov/raw.zip",
        safe_basename="raw.zip",
        media_class="zip",
        expected_member_name="BUM00015614-data.txt",
        head_status=200,
        content_length=archive_path.stat().st_size,
        etag='"one"',
    )
    policy, _ = load_source_policy()
    _verify_zip_payloads(payload, (item,), policy)
