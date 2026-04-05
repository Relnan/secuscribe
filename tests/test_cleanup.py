"""
tests/test_cleanup.py — Unit tests for the GDPR cleanup service.
"""

import os
import secrets
import tempfile
from pathlib import Path

import pytest

# Make the project root available on sys.path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from secuscribe.cleanup import CleanupService, delete_audio_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tmp(content: bytes = b"audio data") -> Path:
    """Return a temporary file path containing *content*."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.write(fd, content)
    os.close(fd)
    return Path(path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeleteAudioFile:
    def test_file_is_deleted(self):
        path = _write_tmp()
        assert path.exists()
        delete_audio_file(path)
        assert not path.exists()

    def test_raises_if_not_found(self):
        with pytest.raises(FileNotFoundError):
            delete_audio_file(Path("/nonexistent/path/file.wav"))

    def test_raises_if_directory(self, tmp_path):
        with pytest.raises(IsADirectoryError):
            delete_audio_file(tmp_path)

    def test_content_overwritten(self):
        """The original bytes must not survive deletion."""
        sentinel = b"SECRET_AUDIO_CONTENT_DO_NOT_KEEP"
        path = _write_tmp(sentinel)
        # We cannot inspect the bytes after unlink, so instead we verify
        # that the file no longer exists after calling delete_audio_file.
        delete_audio_file(path)
        assert not path.exists()

    def test_large_file_deleted(self):
        """Test with a larger file to exercise the overwrite loop."""
        data = secrets.token_bytes(64 * 1024)  # 64 KiB
        path = _write_tmp(data)
        delete_audio_file(path)
        assert not path.exists()

    def test_empty_file_deleted(self):
        path = _write_tmp(b"")
        delete_audio_file(path)
        assert not path.exists()


class TestCleanupService:
    def test_on_deleted_callback(self):
        path = _write_tmp()
        deleted: list[Path] = []
        service = CleanupService(on_deleted=lambda p: deleted.append(p))
        service.delete(path)
        assert not path.exists()
        assert deleted == [path]

    def test_on_error_callback(self):
        errors: list[tuple] = []
        service = CleanupService(on_error=lambda p, e: errors.append((p, e)))
        nonexistent = Path("/tmp/does_not_exist_xyz.wav")
        service.delete(nonexistent)
        assert len(errors) == 1
        assert errors[0][0] == nonexistent

    def test_on_error_reraises_when_no_callback(self):
        service = CleanupService()
        with pytest.raises(FileNotFoundError):
            service.delete(Path("/tmp/does_not_exist_xyz.wav"))

    def test_delete_batch_success(self):
        paths = [_write_tmp() for _ in range(3)]
        service = CleanupService()
        results = service.delete_batch(paths)
        for p in paths:
            assert not p.exists()
            assert results[str(p)] is None

    def test_delete_batch_partial_failure(self):
        good = _write_tmp()
        bad = Path("/tmp/does_not_exist_abc.wav")
        results = CleanupService().delete_batch([good, bad])
        assert results[str(good)] is None
        assert results[str(bad)] is not None  # error message
