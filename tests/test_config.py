"""
tests/test_config.py — Unit tests for the configuration module.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestActiveProfile:
    def test_default_profile_is_8gb(self, monkeypatch):
        monkeypatch.delenv("SECUSCRIBE_PROFILE", raising=False)
        # Re-import with the env cleared
        if "config" in sys.modules:
            del sys.modules["config"]
        import config as cfg
        assert cfg.ACTIVE_PROFILE.name == "8GB"

    def test_24gb_profile_selected(self, monkeypatch):
        monkeypatch.setenv("SECUSCRIBE_PROFILE", "24GB")
        if "config" in sys.modules:
            del sys.modules["config"]
        import config as cfg
        assert cfg.ACTIVE_PROFILE.name == "24GB"
        assert cfg.ACTIVE_PROFILE.whisper_model == "large-v3"

    def test_invalid_profile_raises(self, monkeypatch):
        monkeypatch.setenv("SECUSCRIBE_PROFILE", "INVALID")
        if "config" in sys.modules:
            del sys.modules["config"]
        with pytest.raises(ValueError, match="INVALID"):
            import config  # noqa: F401


class TestResourceProfile:
    def test_8gb_uses_small_model(self):
        if "config" in sys.modules:
            del sys.modules["config"]
        os.environ.pop("SECUSCRIBE_PROFILE", None)
        import config as cfg
        profile = cfg.PROFILE_8GB
        assert profile.whisper_model == "small"
        assert profile.compute_type == "int8"

    def test_24gb_uses_large_model(self):
        if "config" in sys.modules:
            del sys.modules["config"]
        import config as cfg
        profile = cfg.PROFILE_24GB
        assert profile.whisper_model == "large-v3"
        assert profile.cpu_threads >= 8

    def test_allowed_mime_types_not_empty(self):
        if "config" in sys.modules:
            del sys.modules["config"]
        import config as cfg
        assert len(cfg.ACTIVE_PROFILE.allowed_mime_types) > 0

    def test_max_upload_bytes_positive(self):
        if "config" in sys.modules:
            del sys.modules["config"]
        import config as cfg
        assert cfg.ACTIVE_PROFILE.max_upload_bytes > 0


class TestDirectories:
    def test_watch_dir_created(self):
        if "config" in sys.modules:
            del sys.modules["config"]
        import config as cfg
        assert cfg.WATCH_DIR.exists()

    def test_output_dir_created(self):
        if "config" in sys.modules:
            del sys.modules["config"]
        import config as cfg
        assert cfg.OUTPUT_DIR.exists()
