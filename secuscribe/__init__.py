"""
SecuScribe — Secure offline transcription engine.

Packages:
  transcription  Core engine: faster-whisper + diarization + fuzzy glossary
  cleanup        GDPR-compliant secure file deletion
  encryption     GnuPG output-file encryption wrapper
  consent        Voice consent verification
  watcher        Local mode: watchdog shared-folder monitor
  web_server     Web mode: FastAPI upload endpoint
"""

__version__ = "0.1.0"
__all__ = [
    "transcription",
    "cleanup",
    "encryption",
    "consent",
    "watcher",
    "web_server",
]
