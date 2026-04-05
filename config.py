"""
config.py — SecuScribe resource profiles and application settings.

Two RAM profiles are supported:
  - PROFILE_8GB  : Optimised for systems with ~8 GB RAM (small Whisper model, single batch).
  - PROFILE_24GB : Optimised for systems with ~24 GB RAM (large Whisper model, parallel batches).

Select a profile by setting the environment variable SECUSCRIBE_PROFILE to "8GB" or "24GB"
(defaults to "8GB").
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Paths (all relative to the project root; override via env-vars if needed)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
WATCH_DIR = Path(os.getenv("SECUSCRIBE_WATCH_DIR", BASE_DIR / "input"))
OUTPUT_DIR = Path(os.getenv("SECUSCRIBE_OUTPUT_DIR", BASE_DIR / "output"))
GLOSSARY_FILE = Path(os.getenv("SECUSCRIBE_GLOSSARY", BASE_DIR / "glossary.json"))
GPG_HOME = Path(os.getenv("GNUPGHOME", Path.home() / ".gnupg"))

# ---------------------------------------------------------------------------
# Dataclass for a single resource profile
# ---------------------------------------------------------------------------


@dataclass
class ResourceProfile:
    """Hardware-specific tuning parameters."""

    name: str

    # Whisper model size: "tiny", "base", "small", "medium", "large-v3", …
    whisper_model: str

    # Number of CPU threads used by CTranslate2 / faster-whisper
    cpu_threads: int

    # Number of parallel audio segments processed at once
    num_workers: int

    # Compute type passed to faster-whisper ("int8", "int8_float16", "float16", "float32")
    compute_type: str

    # Beam size for Whisper decoding
    beam_size: int

    # Maximum seconds of audio loaded into memory at once during diarization
    diarization_chunk_s: int

    # FastAPI / uvicorn concurrency limit
    web_max_workers: int

    # Maximum upload size in bytes (default: 200 MB)
    max_upload_bytes: int = 200 * 1024 * 1024

    # Supported audio MIME types for upload validation
    allowed_mime_types: list[str] = field(
        default_factory=lambda: [
            "audio/wav",
            "audio/x-wav",
            "audio/mpeg",
            "audio/mp3",
            "audio/ogg",
            "audio/flac",
            "audio/x-flac",
        ]
    )


# ---------------------------------------------------------------------------
# Predefined profiles
# ---------------------------------------------------------------------------

PROFILE_8GB = ResourceProfile(
    name="8GB",
    whisper_model="small",
    cpu_threads=4,
    num_workers=1,
    compute_type="int8",
    beam_size=3,
    diarization_chunk_s=30,
    web_max_workers=2,
)

PROFILE_24GB = ResourceProfile(
    name="24GB",
    whisper_model="large-v3",
    cpu_threads=8,
    num_workers=2,
    compute_type="int8",
    beam_size=5,
    diarization_chunk_s=60,
    web_max_workers=4,
)

_PROFILES: dict[str, ResourceProfile] = {
    "8GB": PROFILE_8GB,
    "24GB": PROFILE_24GB,
}

# ---------------------------------------------------------------------------
# Active profile (selected at import time)
# ---------------------------------------------------------------------------

ProfileName = Literal["8GB", "24GB"]

_selected: str = os.getenv("SECUSCRIBE_PROFILE", "8GB").upper()
if _selected not in _PROFILES:
    raise ValueError(
        f"Unknown SECUSCRIBE_PROFILE '{_selected}'. Valid options: {list(_PROFILES)}"
    )

ACTIVE_PROFILE: ResourceProfile = _PROFILES[_selected]

# ---------------------------------------------------------------------------
# Application-level settings (independent of RAM profile)
# ---------------------------------------------------------------------------

# Language hint for Whisper ("de" for German, "en" for English, None for auto-detect)
TRANSCRIPTION_LANGUAGE: str | None = os.getenv("SECUSCRIBE_LANG", None)

# Minimum duration of the consent window at the start of a recording (in seconds)
CONSENT_CHECK_WINDOW_S: int = int(os.getenv("SECUSCRIBE_CONSENT_WINDOW", "10"))

# Keywords / phrases that constitute verbal consent (case-insensitive, any match suffices)
CONSENT_KEYWORDS: list[str] = [
    "ich stimme zu",
    "i agree",
    "i consent",
    "einverstanden",
    "ja, ich bin einverstanden",
    "yes, i consent",
]

# Fuzzy-match threshold (0–100) for glossary substitution
FUZZY_THRESHOLD: int = int(os.getenv("SECUSCRIBE_FUZZY_THRESHOLD", "85"))

# GPG recipient key ID / fingerprint used to encrypt output (empty → no encryption)
GPG_RECIPIENT: str = os.getenv("SECUSCRIBE_GPG_RECIPIENT", "")

# FastAPI host / port
WEB_HOST: str = os.getenv("SECUSCRIBE_WEB_HOST", "127.0.0.1")
WEB_PORT: int = int(os.getenv("SECUSCRIBE_WEB_PORT", "8000"))

# Ensure required directories exist at import time
WATCH_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
