from paragliding_forecasts_ml.ingestion.igra.cli import _write, main


def test_write_pretty_prints_sorted_json(capsys) -> None:
    _write({"z": 1, "a": {"nested": True}})

    assert capsys.readouterr().out == ('{\n  "a": {\n    "nested": true\n  },\n  "z": 1\n}\n')


def test_fresh_requires_explicit_live_network_authority(capsys) -> None:
    exit_code = main(
        [
            "fresh",
            "--station-id",
            "BUM00015614",
            "--date",
            "2025-08-02",
            "--maximum-total-mib",
            "80",
        ]
    )
    assert exit_code == 1
    assert "allow-live-network" in capsys.readouterr().err


def test_resume_does_not_accept_a_live_network_option() -> None:
    # argparse rejects this option before any resume transport could be constructed.
    try:
        main(
            ["resume", "--run-key", "00000000-0000-4000-8000-000000000000", "--allow-live-network"]
        )
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("resume unexpectedly accepted a live-network option")
