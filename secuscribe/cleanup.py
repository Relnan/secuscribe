"""
secuscribe/cleanup.py
~~~~~~~~~~~~~~~~~~~~~
GDPR-compliant secure cleanup service.

Audio files are overwritten with random bytes before deletion so that the
content cannot be recovered from the storage medium — satisfying the
"right to erasure" obligation under GDPR Art. 17 and BSI TR-02102
recommendations for data-at-rest disposal.

Usage::

    from secuscribe.cleanup import delete_audio_file, CleanupService

    # One-shot deletion
    delete_audio_file(Path("recording.wav"))

    # Register a callback that is called after every deletion
    service = CleanupService(on_deleted=lambda p: print(f"Deleted {p}"))
    service.delete(Path("recording.wav"))
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Number of overwrite passes.  3 passes satisfy most regulatory requirements
# and BSI guidelines for magnetic and flash storage.
_OVERWRITE_PASSES: int = 3


def _secure_overwrite(path: Path) -> None:
    """
    Overwrite the file at *path* with cryptographically random bytes in
    *_OVERWRITE_PASSES* passes before deletion.

    Raises :exc:`OSError` if the file cannot be opened or written.
    """
    size = path.stat().st_size
    if size == 0:
        return  # Nothing to overwrite

    with open(path, "r+b") as fh:
        for _ in range(_OVERWRITE_PASSES):
            fh.seek(0)
            fh.write(secrets.token_bytes(size))
            fh.flush()
            os.fsync(fh.fileno())


def delete_audio_file(path: Path | str) -> None:
    """
    Securely delete an audio file.

    The file is overwritten with random data before being unlinked so that
    forensic recovery is computationally infeasible.

    Parameters
    ----------
    path:
        Absolute or relative path to the audio file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    OSError
        If the file cannot be overwritten or deleted.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise IsADirectoryError(f"Path is not a regular file: {path}")

    logger.info("Securely deleting %s…", path)
    _secure_overwrite(path)
    path.unlink()
    logger.info("Deleted: %s", path)


class CleanupService:
    """
    High-level GDPR cleanup service.

    Wraps :func:`delete_audio_file` and optionally invokes a callback
    after each successful deletion so that callers can update audit logs
    or UI state.

    Parameters
    ----------
    on_deleted:
        Optional callable receiving the deleted :class:`~pathlib.Path`.
    on_error:
        Optional callable receiving ``(Path, Exception)`` when deletion
        fails.  If omitted the error is logged and re-raised.
    """

    def __init__(
        self,
        on_deleted: Optional[Callable[[Path], None]] = None,
        on_error: Optional[Callable[[Path, Exception], None]] = None,
    ) -> None:
        self._on_deleted = on_deleted
        self._on_error = on_error

    def delete(self, path: Path | str) -> None:
        """Securely delete *path* and fire registered callbacks."""
        path = Path(path)
        try:
            delete_audio_file(path)
        except Exception as exc:  # noqa: BLE001
            if self._on_error:
                self._on_error(path, exc)
            else:
                logger.error("Failed to delete %s: %s", path, exc)
                raise
            return

        if self._on_deleted:
            self._on_deleted(path)

    def delete_batch(self, paths: list[Path | str]) -> dict[str, Optional[str]]:
        """
        Delete multiple files and return a result mapping.

        Returns
        -------
        dict
            Maps str path → ``None`` on success, or an error message string
            on failure.
        """
        results: dict[str, Optional[str]] = {}
        for p in paths:
            p = Path(p)
            try:
                delete_audio_file(p)
                results[str(p)] = None
            except Exception as exc:  # noqa: BLE001
                logger.error("Batch delete failed for %s: %s", p, exc)
                results[str(p)] = str(exc)
        return results
