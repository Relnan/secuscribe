"""
secuscribe/watcher.py
~~~~~~~~~~~~~~~~~~~~~
Local Mode — Shared Folder Monitor.

Uses *watchdog* to watch an input directory for new audio files.  When a
file appears it is queued for the full processing pipeline:

1. Consent verification
2. Transcription (faster-whisper + diarization + fuzzy glossary)
3. Output writing (JSON + plain text)
4. Optional GPG encryption
5. Secure GDPR deletion of the original audio file

Usage::

    from secuscribe.watcher import FolderWatcher

    watcher = FolderWatcher()
    watcher.start()          # blocks until KeyboardInterrupt / stop()
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# File extensions that are treated as audio files
_AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus"}
)

# Seconds to wait after a file-creation event before processing
# (gives the writer time to finish copying the file)
_SETTLE_SECONDS: float = 2.0


class _AudioEventHandler(FileSystemEventHandler):
    """Push new audio file paths onto a queue for the worker thread."""

    def __init__(self, file_queue: queue.Queue) -> None:
        super().__init__()
        self._queue = file_queue

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in _AUDIO_EXTENSIONS:
            logger.info("New audio file detected: %s", path.name)
            self._queue.put(path)


class FolderWatcher:
    """
    Watch *watch_dir* for new audio files and run the full pipeline.

    Parameters
    ----------
    watch_dir:
        Directory to monitor.  Defaults to ``config.WATCH_DIR``.
    output_dir:
        Directory where transcripts are written.  Defaults to
        ``config.OUTPUT_DIR``.
    model_size, compute_type, cpu_threads, num_workers, beam_size:
        Passed through to :func:`~secuscribe.transcription.transcribe`.
    language:
        Whisper language hint or ``None`` for auto-detect.
    glossary_path:
        Path to a JSON glossary file, or ``None`` to skip correction.
    fuzzy_threshold:
        Minimum fuzzy-match score for glossary substitution.
    diarization_model:
        Local path to a pyannote pipeline or ``None`` to skip diarization.
    gpg_recipient:
        GPG key ID for output encryption, or ``""`` to skip encryption.
    verify_consent:
        If ``True``, audio files without verbal consent are rejected.
    consent_keywords:
        Override the default consent keyword list.
    consent_window_s:
        Duration (seconds) of the consent check window.
    """

    def __init__(
        self,
        watch_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        *,
        model_size: str = "small",
        compute_type: str = "int8",
        cpu_threads: int = 4,
        num_workers: int = 1,
        beam_size: int = 3,
        language: Optional[str] = None,
        glossary_path: Optional[Path] = None,
        fuzzy_threshold: int = 85,
        diarization_model: Optional[str] = None,
        gpg_recipient: str = "",
        verify_consent: bool = True,
        consent_keywords: Optional[list[str]] = None,
        consent_window_s: int = 10,
    ) -> None:
        import config as cfg  # type: ignore[import]

        self._watch_dir = watch_dir or cfg.WATCH_DIR
        self._output_dir = output_dir or cfg.OUTPUT_DIR
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._transcription_kwargs = dict(
            model_size=model_size,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
            num_workers=num_workers,
            beam_size=beam_size,
            language=language,
            glossary_path=glossary_path,
            fuzzy_threshold=fuzzy_threshold,
            diarization_model=diarization_model,
        )

        self._gpg_recipient = gpg_recipient
        self._verify_consent = verify_consent
        self._consent_kwargs = dict(
            keywords=consent_keywords,
            window_s=consent_window_s,
        )

        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._observer: Optional[Observer] = None
        self._worker_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _process(self, audio_path: Path) -> None:
        """Run the full pipeline for a single audio file."""
        from secuscribe.cleanup import CleanupService
        from secuscribe.consent import ConsentVerifier
        from secuscribe.transcription import transcribe

        # ---- 1. Consent check ------------------------------------------
        if self._verify_consent:
            verifier = ConsentVerifier(**self._consent_kwargs)
            if not verifier.verify(audio_path):
                logger.warning(
                    "Consent not confirmed for %s — file will be securely deleted.",
                    audio_path.name,
                )
                CleanupService().delete(audio_path)
                return

        # ---- 2. Transcription ------------------------------------------
        result = transcribe(audio_path, **self._transcription_kwargs)

        # ---- 3. Write output -------------------------------------------
        stem = audio_path.stem
        json_path = self._output_dir / f"{stem}.json"
        txt_path = self._output_dir / f"{stem}.txt"

        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh, ensure_ascii=False, indent=2)
        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(result.full_text)

        logger.info("Transcript written: %s, %s", json_path.name, txt_path.name)

        # ---- 4. GPG encryption -----------------------------------------
        if self._gpg_recipient:
            from secuscribe.encryption import GPGEncryptor

            enc = GPGEncryptor(recipient=self._gpg_recipient)
            enc.encrypt_file(json_path)
            enc.encrypt_file(txt_path)

        # ---- 5. Secure delete ------------------------------------------
        CleanupService().delete(audio_path)

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        """Background worker: dequeue and process audio files."""
        while not self._stop_event.is_set():
            try:
                audio_path: Path = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # Wait for the file to be fully written
            time.sleep(_SETTLE_SECONDS)
            if not audio_path.exists():
                logger.warning("File vanished before processing: %s", audio_path)
                self._queue.task_done()
                continue

            try:
                self._process(audio_path)
            except Exception as exc:  # noqa: BLE001
                logger.error("Pipeline error for %s: %s", audio_path.name, exc, exc_info=True)
            finally:
                self._queue.task_done()

    def start(self, *, block: bool = True) -> None:
        """
        Start watching the input directory.

        Parameters
        ----------
        block:
            If ``True`` (default), block until :meth:`stop` is called or
            a ``KeyboardInterrupt`` is received.
        """
        logger.info("Watching %s for new audio files…", self._watch_dir)

        event_handler = _AudioEventHandler(self._queue)
        self._observer = Observer()
        self._observer.schedule(event_handler, str(self._watch_dir), recursive=False)
        self._observer.start()

        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()

        if block:
            try:
                while self._observer.is_alive():
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()

    def stop(self) -> None:
        """Stop the watcher and worker thread gracefully."""
        logger.info("Stopping folder watcher…")
        self._stop_event.set()
        if self._observer:
            self._observer.stop()
            self._observer.join()
        if self._worker_thread:
            self._worker_thread.join(timeout=10)
        logger.info("Folder watcher stopped.")
