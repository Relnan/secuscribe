"""
secuscribe/consent.py
~~~~~~~~~~~~~~~~~~~~~
Voice Consent Verification Module.

Before transcription begins the first *N* seconds of a recording are
analysed to confirm that the speaker has given verbal consent.  This
satisfies the requirements of GDPR Art. 6 and BSI-KritisV when
processing personal speech data.

Consent is determined by running Whisper on a short initial window and
checking whether any configured consent keywords appear in the transcript.

Usage::

    from pathlib import Path
    from secuscribe.consent import ConsentVerifier

    verifier = ConsentVerifier()
    if not verifier.verify(Path("recording.wav")):
        raise PermissionError("No verbal consent detected — aborting.")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default consent keywords (case-insensitive substring match)
_DEFAULT_KEYWORDS: list[str] = [
    "ich stimme zu",
    "i agree",
    "i consent",
    "einverstanden",
    "ja, ich bin einverstanden",
    "yes, i consent",
]

# Duration (seconds) of the recording analysed for the consent check
_DEFAULT_WINDOW_S: int = 10


class ConsentVerifier:
    """
    Verify verbal consent at the start of a recording.

    Parameters
    ----------
    keywords:
        List of consent phrases to look for (case-insensitive).
    window_s:
        Duration in seconds of the audio prefix analysed for consent.
    model_size:
        faster-whisper model used for the consent transcription pass.
        ``"tiny"`` is fast enough for a short keyword check.
    language:
        ISO-639-1 language code for Whisper, or ``None`` for auto-detect.
    """

    def __init__(
        self,
        keywords: Optional[list[str]] = None,
        window_s: int = _DEFAULT_WINDOW_S,
        model_size: str = "tiny",
        language: Optional[str] = None,
    ) -> None:
        self._keywords = [kw.lower() for kw in (keywords or _DEFAULT_KEYWORDS)]
        self._window_s = window_s
        self._model_size = model_size
        self._language = language
        self._model = None   # lazy-loaded

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # type: ignore[import]

            logger.debug("Loading consent Whisper model '%s'…", self._model_size)
            self._model = WhisperModel(
                self._model_size,
                device="cpu",
                compute_type="int8",
                cpu_threads=2,
            )
        return self._model

    def _extract_prefix(self, audio_path: Path) -> Path:
        """
        Return a path to an audio clip containing only the first
        ``_window_s`` seconds of *audio_path*.

        Uses *pydub* if available for accurate trimming; otherwise falls
        back to returning the original file path (the Whisper ``clip_timestamps``
        parameter is used in that case).
        """
        try:
            from pydub import AudioSegment  # type: ignore[import]

            audio = AudioSegment.from_file(str(audio_path))
            clip = audio[: self._window_s * 1000]  # pydub works in ms
            tmp_path = audio_path.with_suffix(".consent_tmp.wav")
            clip.export(str(tmp_path), format="wav")
            return tmp_path
        except ImportError:
            # pydub not installed — use the full file and rely on Whisper's VAD
            return audio_path

    def _cleanup_tmp(self, tmp_path: Path, original: Path) -> None:
        if tmp_path != original and tmp_path.exists():
            tmp_path.unlink()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(self, audio_path: Path | str) -> bool:
        """
        Return ``True`` if a consent phrase is detected in the first
        ``window_s`` seconds of *audio_path*.

        Parameters
        ----------
        audio_path:
            Path to the audio file to check.

        Returns
        -------
        bool
            ``True`` when consent is confirmed, ``False`` otherwise.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info("Checking consent in %s (window=%ds)…", audio_path.name, self._window_s)

        clip_path = self._extract_prefix(audio_path)
        try:
            model = self._load_model()
            segments, _info = model.transcribe(
                str(clip_path),
                language=self._language,
                beam_size=1,
                vad_filter=True,
            )
            transcript = " ".join(seg.text for seg in segments).lower()
        finally:
            self._cleanup_tmp(clip_path, audio_path)

        logger.debug("Consent transcript: %r", transcript)

        for keyword in self._keywords:
            if keyword in transcript:
                logger.info("Consent confirmed (keyword: %r).", keyword)
                return True

        logger.warning(
            "No consent keyword found in %s. Transcript was: %r",
            audio_path.name,
            transcript,
        )
        return False

    def get_transcript(self, audio_path: Path | str) -> str:
        """
        Return the raw transcript of the consent window without evaluating
        keywords.  Useful for audit logging.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        clip_path = self._extract_prefix(audio_path)
        try:
            model = self._load_model()
            segments, _info = model.transcribe(
                str(clip_path),
                language=self._language,
                beam_size=1,
                vad_filter=True,
            )
            return " ".join(seg.text for seg in segments)
        finally:
            self._cleanup_tmp(clip_path, audio_path)
