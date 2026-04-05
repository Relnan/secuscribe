"""
secuscribe/transcription.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Core Engine: offline transcription with faster-whisper, optional speaker
diarization via pyannote.audio, and a fuzzy-logic glossary system for
domain-specific technical terms.

All operations are strictly local — no network calls are made.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """A single transcribed (and optionally diarized) segment."""

    start: float          # segment start time in seconds
    end: float            # segment end time in seconds
    text: str             # raw transcribed text
    speaker: str = "UNKNOWN"
    corrected_text: str = ""  # text after glossary substitution

    def __post_init__(self) -> None:
        if not self.corrected_text:
            self.corrected_text = self.text


@dataclass
class TranscriptionResult:
    """Full result returned by :func:`transcribe`."""

    audio_path: Path
    language: str
    segments: list[Segment] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Return the full corrected transcript as a single string."""
        return "\n".join(
            f"[{s.speaker}] ({s.start:.1f}s – {s.end:.1f}s): {s.corrected_text}"
            for s in self.segments
        )

    def to_dict(self) -> dict:
        return {
            "audio_path": str(self.audio_path),
            "language": self.language,
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "speaker": s.speaker,
                    "text": s.corrected_text,
                }
                for s in self.segments
            ],
        }


# ---------------------------------------------------------------------------
# Glossary system
# ---------------------------------------------------------------------------


class GlossaryCorrector:
    """
    Fuzzy-logic glossary corrector.

    Loads a JSON file mapping common mis-transcriptions (or phonetically
    similar words) to their correct technical equivalents, then replaces
    matching tokens in transcript segments.

    The JSON file must be an object of the form::

        {
            "Verschlüsselung": ["Verschluesselung", "Verschluessellung"],
            "BSI": ["B.S.I.", "B SI", "Besi"],
            ...
        }

    Keys are the *canonical* technical terms; values are lists of phonetic
    variants / likely mis-transcriptions.
    """

    def __init__(self, glossary_path: Path, threshold: int = 85) -> None:
        self._threshold = threshold
        self._lookup: dict[str, str] = {}   # variant → canonical
        if glossary_path.exists():
            self._load(glossary_path)
        else:
            logger.info("Glossary file not found at %s — skipping glossary correction.", glossary_path)

    def _load(self, path: Path) -> None:
        with open(path, encoding="utf-8") as fh:
            data: dict[str, list[str]] = json.load(fh)
        for canonical, variants in data.items():
            self._lookup[canonical.lower()] = canonical
            for variant in variants:
                self._lookup[variant.lower()] = canonical
        logger.debug("Loaded %d glossary entries from %s.", len(self._lookup), path)

    def correct(self, text: str) -> str:
        """
        Apply fuzzy-matched glossary corrections to *text*.

        Each whitespace-separated token is compared against all known
        variants; if a match above *threshold* is found the token is
        replaced with the canonical term.
        """
        if not self._lookup:
            return text

        tokens = text.split()
        corrected: list[str] = []
        choices = list(self._lookup.keys())

        for token in tokens:
            clean = token.strip(".,;:!?\"'")
            match = process.extractOne(
                clean.lower(),
                choices,
                scorer=fuzz.WRatio,
                score_cutoff=self._threshold,
            )
            if match:
                canonical = self._lookup[match[0]]
                # Preserve surrounding punctuation
                corrected.append(token.replace(clean, canonical))
            else:
                corrected.append(token)

        return " ".join(corrected)


# ---------------------------------------------------------------------------
# Diarization (optional — requires pyannote.audio + pre-downloaded models)
# ---------------------------------------------------------------------------


class SpeakerDiarizer:
    """
    Thin wrapper around *pyannote.audio* pipeline.

    If pyannote is not installed (or the model is not available locally),
    this class is a no-op and all segments will be labelled "UNKNOWN".

    Activate by passing ``diarization_model`` to :func:`transcribe`; the
    string must point to a *local* directory that contains a valid
    pyannote pipeline (copied from the HuggingFace hub before air-gapping
    the system).
    """

    def __init__(self, model_path: str | None = None) -> None:
        self._pipeline = None
        if model_path is None:
            return
        try:
            from pyannote.audio import Pipeline  # type: ignore[import]
            self._pipeline = Pipeline.from_pretrained(model_path)
            logger.info("Speaker diarization pipeline loaded from %s.", model_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not load diarization pipeline from '%s': %s. "
                "Speaker labels will be 'UNKNOWN'.",
                model_path,
                exc,
            )

    @property
    def available(self) -> bool:
        return self._pipeline is not None

    def diarize(self, audio_path: Path) -> dict[tuple[float, float], str]:
        """
        Return a dict mapping (start, end) float pairs to speaker labels.

        Returns an empty dict when the pipeline is unavailable.
        """
        if not self.available:
            return {}
        try:
            diarization = self._pipeline(str(audio_path))
            result: dict[tuple[float, float], str] = {}
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                result[(turn.start, turn.end)] = speaker
            return result
        except Exception as exc:  # noqa: BLE001
            logger.error("Diarization failed: %s", exc)
            return {}


def _assign_speaker(
    start: float,
    end: float,
    diarization: dict[tuple[float, float], str],
) -> str:
    """Return the speaker label with the greatest overlap with [start, end]."""
    if not diarization:
        return "UNKNOWN"

    best_speaker = "UNKNOWN"
    best_overlap = 0.0

    for (d_start, d_end), speaker in diarization.items():
        overlap = max(0.0, min(end, d_end) - max(start, d_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker

    return best_speaker


# ---------------------------------------------------------------------------
# Public transcription function
# ---------------------------------------------------------------------------


def transcribe(
    audio_path: Path | str,
    *,
    model_size: str = "small",
    language: Optional[str] = None,
    compute_type: str = "int8",
    cpu_threads: int = 4,
    num_workers: int = 1,
    beam_size: int = 3,
    glossary_path: Optional[Path] = None,
    fuzzy_threshold: int = 85,
    diarization_model: Optional[str] = None,
) -> TranscriptionResult:
    """
    Transcribe an audio file entirely offline.

    Parameters
    ----------
    audio_path:
        Path to the audio file to transcribe.
    model_size:
        faster-whisper model size (e.g. ``"small"``, ``"large-v3"``).
        The model must already be present in the local model cache.
    language:
        ISO-639-1 language code (``"de"``, ``"en"``, …) or ``None`` for
        automatic language detection.
    compute_type:
        CTranslate2 quantisation type (``"int8"`` recommended for CPU).
    cpu_threads:
        Number of CPU threads for CTranslate2.
    num_workers:
        Number of parallel decoding workers.
    beam_size:
        Decoding beam width.
    glossary_path:
        Path to a JSON glossary file.  Pass ``None`` to skip correction.
    fuzzy_threshold:
        Minimum fuzzy-match score (0–100) for a glossary substitution.
    diarization_model:
        Local path to a pyannote.audio pipeline directory, or ``None`` to
        skip diarization.

    Returns
    -------
    TranscriptionResult
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    logger.info("Loading Whisper model '%s' (compute=%s)…", model_size, compute_type)
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "faster-whisper is required for transcription. "
            "Install it with: pip install faster-whisper"
        ) from exc
    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        num_workers=num_workers,
    )

    diarizer = SpeakerDiarizer(diarization_model)
    corrector = GlossaryCorrector(
        glossary_path or Path(os.devnull),
        threshold=fuzzy_threshold,
    )

    logger.info("Starting transcription of %s…", audio_path.name)
    raw_segments, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=beam_size,
        vad_filter=True,
    )

    diarization_map = diarizer.diarize(audio_path) if diarizer.available else {}

    segments: list[Segment] = []
    for seg in raw_segments:
        speaker = _assign_speaker(seg.start, seg.end, diarization_map)
        corrected = corrector.correct(seg.text)
        segments.append(
            Segment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                speaker=speaker,
                corrected_text=corrected,
            )
        )
        logger.debug("[%s] %.1f–%.1f: %s", speaker, seg.start, seg.end, corrected)

    result = TranscriptionResult(
        audio_path=audio_path,
        language=info.language,
        segments=segments,
    )
    logger.info(
        "Transcription complete: %d segment(s), language='%s'.",
        len(segments),
        info.language,
    )
    return result
