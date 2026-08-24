from __future__ import annotations

from paragliding_forecasts_ml.ingestion.copernicus.elevation_cli import (
    _file_environment,
    main,
)


def test_cli_refuses_network_without_explicit_acknowledgement(capsys) -> None:
    assert main([]) == 2
    assert "Refusing network access" in capsys.readouterr().err


def test_file_environment_reads_only_owned_settings(tmp_path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        """
# comment
CDSE_CLIENT_ID='client-id'
CDSE_CLIENT_SECRET="client-secret"
DATABASE_URL=file:./data/local/weather.db
UNRELATED=not-loaded
""".lstrip(),
        encoding="utf-8",
    )

    assert _file_environment(path) == {
        "CDSE_CLIENT_ID": "client-id",
        "CDSE_CLIENT_SECRET": "client-secret",
        "DATABASE_URL": "file:./data/local/weather.db",
    }
