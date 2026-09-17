from pathlib import Path

from paragliding_forecasts_ml.ingestion.igra.artifacts import IgraArtifactStore


def test_artifact_reference_rehashes_exact_written_bytes(tmp_path: Path) -> None:
    store = IgraArtifactStore.create_fresh(
        "00000000-0000-4000-8000-000000000000", project_root=tmp_path
    )
    path = store.interim_dir / "example.json"
    reference = store.write_bytes(path, "example", b"{}\n", media_type="application/json")
    assert store.verify_reference(reference) == path


def test_publish_directory_verifies_and_reuses_an_existing_boundary(tmp_path: Path) -> None:
    store = IgraArtifactStore.create_fresh(
        "00000000-0000-4000-8000-000000000000", project_root=tmp_path
    )
    destination = store.interim_dir / "shared-boundary"
    destination.mkdir()
    (destination / "winner.json").write_bytes(b"winner\n")
    work = store.create_work_directory() / "boundary"
    work.mkdir()
    (work / "candidate.json").write_bytes(b"candidate\n")

    assert store.publish_directory(work, destination) == destination
    assert (destination / "winner.json").read_bytes() == b"winner\n"
    assert not work.exists()
