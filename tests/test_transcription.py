"""
tests/test_transcription.py — Unit tests for the transcription module.

The GlossaryCorrector and _assign_speaker helpers can be tested without
loading any ML models.  Tests that require WhisperModel are skipped when
faster-whisper is not installed.
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from secuscribe.transcription import (
    GlossaryCorrector,
    Segment,
    TranscriptionResult,
    _assign_speaker,
)


# ---------------------------------------------------------------------------
# GlossaryCorrector
# ---------------------------------------------------------------------------


class TestGlossaryCorrector:
    def _make_corrector(self, data: dict, threshold: int = 85) -> GlossaryCorrector:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(data, fh)
            path = Path(fh.name)
        return GlossaryCorrector(path, threshold=threshold)

    def test_exact_match(self):
        corrector = self._make_corrector({"BSI": ["Besi", "B SI"]})
        assert corrector.correct("Besi prüft das System") == "BSI prüft das System"

    def test_canonical_passthrough(self):
        corrector = self._make_corrector({"BSI": ["Besi"]})
        assert corrector.correct("BSI prüft das System") == "BSI prüft das System"

    def test_no_match_below_threshold(self):
        corrector = self._make_corrector({"Zertifikat": ["Zertifikat"]}, threshold=99)
        # "Banana" is far from "Zertifikat" — no substitution expected
        result = corrector.correct("Banana ist kein Sicherheitsbegriff")
        assert "Banana" in result

    def test_missing_glossary_file(self, tmp_path):
        corrector = GlossaryCorrector(tmp_path / "nonexistent.json")
        assert corrector.correct("some text") == "some text"

    def test_empty_text(self):
        corrector = self._make_corrector({"BSI": ["Besi"]})
        assert corrector.correct("") == ""

    def test_punctuation_preserved(self):
        corrector = self._make_corrector({"BSI": ["Besi"]})
        result = corrector.correct("Laut Besi, muss das System geprüft werden.")
        assert "BSI," in result

    def test_multiple_replacements(self):
        corrector = self._make_corrector(
            {"BSI": ["Besi"], "TLS": ["T.L.S."]}
        )
        result = corrector.correct("Besi empfiehlt T.L.S. Verschlüsselung")
        assert "BSI" in result
        assert "TLS" in result


# ---------------------------------------------------------------------------
# _assign_speaker
# ---------------------------------------------------------------------------


class TestAssignSpeaker:
    def test_empty_diarization(self):
        assert _assign_speaker(0.0, 5.0, {}) == "UNKNOWN"

    def test_exact_match(self):
        diarization = {(0.0, 5.0): "SPEAKER_00"}
        assert _assign_speaker(0.0, 5.0, diarization) == "SPEAKER_00"

    def test_best_overlap(self):
        diarization = {
            (0.0, 3.0): "SPEAKER_00",
            (3.0, 10.0): "SPEAKER_01",
        }
        # Segment mostly overlaps SPEAKER_01
        assert _assign_speaker(2.0, 9.0, diarization) == "SPEAKER_01"

    def test_no_overlap(self):
        diarization = {(10.0, 20.0): "SPEAKER_00"}
        assert _assign_speaker(0.0, 5.0, diarization) == "UNKNOWN"


# ---------------------------------------------------------------------------
# Segment / TranscriptionResult
# ---------------------------------------------------------------------------


class TestSegment:
    def test_corrected_text_defaults_to_text(self):
        seg = Segment(start=0.0, end=1.0, text="Hello")
        assert seg.corrected_text == "Hello"

    def test_corrected_text_override(self):
        seg = Segment(start=0.0, end=1.0, text="Besi", corrected_text="BSI")
        assert seg.corrected_text == "BSI"


class TestTranscriptionResult:
    def _make_result(self) -> TranscriptionResult:
        return TranscriptionResult(
            audio_path=Path("test.wav"),
            language="de",
            segments=[
                Segment(0.0, 2.0, "Hallo Welt", speaker="SPEAKER_00"),
                Segment(2.0, 4.0, "Wie geht es?", speaker="SPEAKER_01"),
            ],
        )

    def test_full_text_contains_speaker(self):
        result = self._make_result()
        assert "SPEAKER_00" in result.full_text
        assert "SPEAKER_01" in result.full_text

    def test_to_dict_structure(self):
        result = self._make_result()
        d = result.to_dict()
        assert d["language"] == "de"
        assert len(d["segments"]) == 2
        assert d["segments"][0]["speaker"] == "SPEAKER_00"
        assert "text" in d["segments"][0]
