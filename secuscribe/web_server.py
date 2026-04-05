"""
secuscribe/web_server.py
~~~~~~~~~~~~~~~~~~~~~~~~
Web Mode — lightweight FastAPI upload endpoint.

Provides a minimal HTTP interface for manual audio file uploads on
air-gapped networks.  The server only listens on localhost by default
(127.0.0.1) and should be placed behind an mTLS reverse-proxy (e.g.
nginx) for network-accessible deployments.

Endpoints
---------
POST /upload
    Accept an audio file, run the full pipeline, and return the transcript.

GET  /health
    Liveness probe — returns ``{"status": "ok"}``.

Usage::

    uvicorn secuscribe.web_server:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SecuScribe",
    description=(
        "Secure offline transcription service — "
        "air-gap ready, GDPR-compliant, BSI-hardened."
    ),
    version="0.1.0",
    docs_url="/docs",    # Disable in production by setting to None
    redoc_url=None,
)

# ---------------------------------------------------------------------------
# Allowed MIME types (validated before processing)
# ---------------------------------------------------------------------------

_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
        "audio/flac",
        "audio/x-flac",
        "audio/mp4",
        "audio/x-m4a",
        "audio/opus",
    }
)

# Maximum upload size (bytes).  Overridden by config.ACTIVE_PROFILE.
_DEFAULT_MAX_BYTES: int = 200 * 1024 * 1024  # 200 MB


def _get_max_upload_bytes() -> int:
    """Return the configured maximum upload size in bytes."""
    try:
        import config as cfg  # type: ignore[import]

        return cfg.ACTIVE_PROFILE.max_upload_bytes
    except ImportError:
        return _DEFAULT_MAX_BYTES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_pipeline_kwargs() -> dict:
    """Return keyword arguments for the pipeline from the active config."""
    try:
        import config as cfg  # type: ignore[import]

        profile = cfg.ACTIVE_PROFILE
        return dict(
            model_size=profile.whisper_model,
            compute_type=profile.compute_type,
            cpu_threads=profile.cpu_threads,
            num_workers=profile.num_workers,
            beam_size=profile.beam_size,
            language=cfg.TRANSCRIPTION_LANGUAGE,
            glossary_path=cfg.GLOSSARY_FILE if cfg.GLOSSARY_FILE.exists() else None,
            fuzzy_threshold=cfg.FUZZY_THRESHOLD,
            gpg_recipient=cfg.GPG_RECIPIENT,
            verify_consent=True,
            consent_window_s=cfg.CONSENT_CHECK_WINDOW_S,
            consent_keywords=cfg.CONSENT_KEYWORDS,
        )
    except ImportError:
        # Fallback defaults when running without config.py (e.g. in tests)
        return dict(
            model_size="small",
            compute_type="int8",
            cpu_threads=4,
            num_workers=1,
            beam_size=3,
            language=None,
            glossary_path=None,
            fuzzy_threshold=85,
            gpg_recipient="",
            verify_consent=True,
            consent_window_s=10,
            consent_keywords=None,
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["monitoring"])
async def health() -> JSONResponse:
    """Liveness probe."""
    return JSONResponse({"status": "ok"})


@app.post("/upload", tags=["transcription"])
async def upload_audio(
    file: Annotated[UploadFile, File(description="Audio file to transcribe")],
) -> JSONResponse:
    """
    Upload an audio file and receive a JSON transcript.

    The audio is:
    1. Saved to a temporary directory.
    2. Checked for verbal consent (configurable).
    3. Transcribed with faster-whisper.
    4. Optionally encrypted with GPG.
    5. Securely deleted from temporary storage (GDPR).

    Returns the transcript JSON on success.
    """
    # ---- Validate content type -----------------------------------------
    content_type = file.content_type or ""
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported media type '{content_type}'. "
                f"Accepted types: {sorted(_ALLOWED_CONTENT_TYPES)}"
            ),
        )

    # ---- Read upload into a secure temp file ---------------------------
    kwargs = _build_pipeline_kwargs()

    with tempfile.TemporaryDirectory(prefix="secuscribe_") as tmpdir:
        tmp_path = Path(tmpdir) / (file.filename or "upload.audio")
        data = await file.read()
        max_bytes: int = _get_max_upload_bytes()

        if len(data) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds maximum allowed size of {max_bytes} bytes.",
            )

        tmp_path.write_bytes(data)
        logger.info("Received upload: %s (%d bytes)", tmp_path.name, len(data))

        # ---- Consent check -------------------------------------------------
        from secuscribe.consent import ConsentVerifier

        verifier = ConsentVerifier(
            keywords=kwargs.get("consent_keywords"),
            window_s=kwargs.get("consent_window_s", 10),
        )
        if kwargs.get("verify_consent", True) and not verifier.verify(tmp_path):
            raise HTTPException(
                status_code=422,
                detail=(
                    "No verbal consent detected in the first "
                    f"{kwargs.get('consent_window_s', 10)} seconds of the recording."
                ),
            )

        # ---- Transcription ------------------------------------------------
        from secuscribe.transcription import transcribe

        result = transcribe(
            tmp_path,
            model_size=kwargs["model_size"],
            language=kwargs.get("language"),
            compute_type=kwargs["compute_type"],
            cpu_threads=kwargs["cpu_threads"],
            num_workers=kwargs["num_workers"],
            beam_size=kwargs["beam_size"],
            glossary_path=kwargs.get("glossary_path"),
            fuzzy_threshold=kwargs.get("fuzzy_threshold", 85),
            diarization_model=None,
        )

        # ---- Optional GPG encryption of the JSON result -------------------
        gpg_recipient: str = kwargs.get("gpg_recipient", "")
        result_dict = result.to_dict()

        if gpg_recipient:
            from secuscribe.encryption import GPGEncryptor

            enc = GPGEncryptor(recipient=gpg_recipient)
            encrypted_text = enc.encrypt_string(json.dumps(result_dict, ensure_ascii=False))
            return JSONResponse({"encrypted": True, "ciphertext": encrypted_text})

        # tmp_path is deleted automatically when the TemporaryDirectory context exits
        return JSONResponse(result_dict)
