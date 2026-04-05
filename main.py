"""
main.py — SecuScribe CLI entry point.

Usage
-----
  # Start the shared-folder watcher (Local Mode):
  python main.py watch

  # Start the FastAPI web server (Web Mode):
  python main.py serve

  # Transcribe a single file directly:
  python main.py transcribe <audio_file>

Environment variables
---------------------
  SECUSCRIBE_PROFILE   "8GB" (default) or "24GB"
  SECUSCRIBE_WATCH_DIR  input directory for Local Mode
  SECUSCRIBE_OUTPUT_DIR output directory for transcripts
  SECUSCRIBE_GPG_RECIPIENT  GPG key ID for encryption (optional)
  SECUSCRIBE_LANG      Whisper language hint, e.g. "de" or "en"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("secuscribe")


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------


def _cmd_watch(args: argparse.Namespace) -> None:
    import config as cfg
    from secuscribe.watcher import FolderWatcher

    profile = cfg.ACTIVE_PROFILE
    watcher = FolderWatcher(
        watch_dir=cfg.WATCH_DIR,
        output_dir=cfg.OUTPUT_DIR,
        model_size=profile.whisper_model,
        compute_type=profile.compute_type,
        cpu_threads=profile.cpu_threads,
        num_workers=profile.num_workers,
        beam_size=profile.beam_size,
        language=cfg.TRANSCRIPTION_LANGUAGE,
        glossary_path=cfg.GLOSSARY_FILE if cfg.GLOSSARY_FILE.exists() else None,
        fuzzy_threshold=cfg.FUZZY_THRESHOLD,
        gpg_recipient=cfg.GPG_RECIPIENT,
        verify_consent=not args.no_consent,
        consent_keywords=cfg.CONSENT_KEYWORDS,
        consent_window_s=cfg.CONSENT_CHECK_WINDOW_S,
    )
    logger.info("SecuScribe Local Mode — profile: %s", profile.name)
    watcher.start(block=True)


def _cmd_serve(args: argparse.Namespace) -> None:
    import config as cfg

    try:
        import uvicorn  # type: ignore[import]
    except ImportError:
        logger.error("uvicorn is required for web mode: pip install uvicorn[standard]")
        sys.exit(1)

    logger.info(
        "SecuScribe Web Mode — %s:%s (profile: %s)",
        cfg.WEB_HOST,
        cfg.WEB_PORT,
        cfg.ACTIVE_PROFILE.name,
    )
    uvicorn.run(
        "secuscribe.web_server:app",
        host=cfg.WEB_HOST,
        port=cfg.WEB_PORT,
        workers=cfg.ACTIVE_PROFILE.web_max_workers,
        log_level="info",
    )


def _cmd_transcribe(args: argparse.Namespace) -> None:
    import config as cfg
    from secuscribe.cleanup import CleanupService
    from secuscribe.consent import ConsentVerifier
    from secuscribe.transcription import transcribe

    audio_path = Path(args.audio_file)
    if not audio_path.exists():
        logger.error("File not found: %s", audio_path)
        sys.exit(1)

    profile = cfg.ACTIVE_PROFILE

    # Consent check
    if not args.no_consent:
        verifier = ConsentVerifier(
            keywords=cfg.CONSENT_KEYWORDS,
            window_s=cfg.CONSENT_CHECK_WINDOW_S,
        )
        if not verifier.verify(audio_path):
            logger.error("Consent not confirmed — aborting.")
            if args.delete:
                CleanupService().delete(audio_path)
            sys.exit(2)

    result = transcribe(
        audio_path,
        model_size=profile.whisper_model,
        compute_type=profile.compute_type,
        cpu_threads=profile.cpu_threads,
        num_workers=profile.num_workers,
        beam_size=profile.beam_size,
        language=cfg.TRANSCRIPTION_LANGUAGE,
        glossary_path=cfg.GLOSSARY_FILE if cfg.GLOSSARY_FILE.exists() else None,
        fuzzy_threshold=cfg.FUZZY_THRESHOLD,
    )

    # Write output
    output_dir = Path(args.output_dir) if args.output_dir else cfg.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = audio_path.stem
    json_path = output_dir / f"{stem}.json"
    txt_path = output_dir / f"{stem}.txt"

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(result.to_dict(), fh, ensure_ascii=False, indent=2)
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(result.full_text)

    logger.info("Transcript saved: %s, %s", json_path, txt_path)

    # GPG encryption
    if cfg.GPG_RECIPIENT:
        from secuscribe.encryption import GPGEncryptor

        enc = GPGEncryptor(recipient=cfg.GPG_RECIPIENT)
        enc.encrypt_file(json_path)
        enc.encrypt_file(txt_path)

    # GDPR deletion
    if args.delete:
        CleanupService().delete(audio_path)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="secuscribe",
        description="SecuScribe — Secure offline transcription engine.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # watch sub-command
    p_watch = sub.add_parser("watch", help="Start the shared-folder watcher (Local Mode).")
    p_watch.add_argument(
        "--no-consent",
        action="store_true",
        help="Skip verbal consent verification.",
    )

    # serve sub-command
    sub.add_parser("serve", help="Start the FastAPI web server (Web Mode).")

    # transcribe sub-command
    p_transcribe = sub.add_parser("transcribe", help="Transcribe a single audio file.")
    p_transcribe.add_argument("audio_file", help="Path to the audio file.")
    p_transcribe.add_argument(
        "--no-consent",
        action="store_true",
        help="Skip verbal consent verification.",
    )
    p_transcribe.add_argument(
        "--delete",
        action="store_true",
        help="Securely delete the audio file after transcription (GDPR).",
    )
    p_transcribe.add_argument(
        "--output-dir",
        help="Directory for transcript output files.",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    commands = {
        "watch": _cmd_watch,
        "serve": _cmd_serve,
        "transcribe": _cmd_transcribe,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
