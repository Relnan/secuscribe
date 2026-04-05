"""
tests/test_web_server.py — Integration-style tests for the FastAPI endpoints.

Uses FastAPI's TestClient so no real server is needed and no ML models
are loaded (the pipeline is mocked out).
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import app after path is set
from secuscribe.web_server import app, _ALLOWED_CONTENT_TYPES

try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /upload — content-type validation
# ---------------------------------------------------------------------------


def test_upload_rejects_unsupported_mime(client):
    resp = client.post(
        "/upload",
        files={"file": ("test.exe", b"binary", "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_upload_rejects_too_large(client, monkeypatch):
    """Files exceeding max_upload_bytes must be rejected."""
    # Patch the helper that returns the max size
    monkeypatch.setattr("secuscribe.web_server._get_max_upload_bytes", lambda: 10)
    resp = client.post(
        "/upload",
        files={"file": ("big.wav", b"x" * 100, "audio/wav")},
    )
    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# /upload — pipeline mocked
# ---------------------------------------------------------------------------


def _mock_transcription_result():
    from secuscribe.transcription import Segment, TranscriptionResult

    return TranscriptionResult(
        audio_path=Path("test.wav"),
        language="de",
        segments=[
            Segment(0.0, 2.0, "Ich stimme zu", speaker="SPEAKER_00")
        ],
    )


@patch("secuscribe.consent.ConsentVerifier")
@patch("secuscribe.transcription.transcribe")
def test_upload_success(mock_transcribe, mock_consent_cls, client):
    """A valid WAV upload with consent confirmed returns transcript JSON."""
    mock_consent_cls.return_value.verify.return_value = True
    mock_transcribe.return_value = _mock_transcription_result()

    resp = client.post(
        "/upload",
        files={"file": ("test.wav", b"\x00" * 44, "audio/wav")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "segments" in body
    assert body["language"] == "de"


@patch("secuscribe.consent.ConsentVerifier")
@patch("secuscribe.transcription.transcribe")
def test_upload_no_consent_returns_422(mock_transcribe, mock_consent_cls, client):
    """Upload without verbal consent must return HTTP 422."""
    mock_consent_cls.return_value.verify.return_value = False

    resp = client.post(
        "/upload",
        files={"file": ("test.wav", b"\x00" * 44, "audio/wav")},
    )
    assert resp.status_code == 422
    mock_transcribe.assert_not_called()


# ---------------------------------------------------------------------------
# Allowed MIME type set sanity checks
# ---------------------------------------------------------------------------


def test_allowed_mime_types_not_empty():
    assert len(_ALLOWED_CONTENT_TYPES) > 0


def test_wav_in_allowed_types():
    assert "audio/wav" in _ALLOWED_CONTENT_TYPES
