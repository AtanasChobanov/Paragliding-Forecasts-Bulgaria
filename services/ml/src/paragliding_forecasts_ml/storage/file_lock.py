"""Process locks for local workflows. The OS releases ownership on process exit."""

import errno
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class LockBusyError(RuntimeError):
    """A cooperating command already holds this lock."""


@contextmanager
def file_lock(path: Path, *, blocking: bool = False) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Lock {path.name} must be a regular local file.")
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            # Lock the first byte. Windows permits locking beyond the end of a file.
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
            except OSError as error:
                if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise LockBusyError(f"Lock {path.name} is held by another process.") from error
                raise
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError as error:
                raise LockBusyError(f"Lock {path.name} is held by another process.") from error
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def weather_run_lock(root: Path, run_key: str) -> Path:
    from ..ingestion.atmosphere.contracts import UUID_V4_PATTERN

    if UUID_V4_PATTERN.fullmatch(run_key) is None:
        raise ValueError("Weather run lock requires a lowercase UUID v4.")
    return root / "data" / "local" / "weather-run-locks" / f"{run_key}.lock"
