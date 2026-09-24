from __future__ import annotations

import pytest

from genesis.learned_capabilities import list_capabilities, run_capability


def test_audio_understanding_is_registered() -> None:
    names = {capability.name for capability in list_capabilities()}
    assert "audio_understanding" in names


def test_audio_understanding_normalizes_bounded_asr_evidence() -> None:
    result = run_capability(
        "audio_understanding",
        [
            {"text": "hello world", "start": 0.0, "end": 1.2, "confidence": 0.93},
            {"text": "second phrase", "start": 1.2, "end": 2.0},
        ],
        source="qwen-asr:test.wav",
        language="en",
    )

    assert result["kind"] == "audio_understanding"
    assert result["source"] == "qwen-asr:test.wav"
    assert result["language"] == "en"
    assert result["segment_count"] == 2
    assert result["transcript"] == "hello world second phrase"
    assert result["segments"][0]["confidence"] == 0.93


def test_audio_understanding_rejects_raw_bytes_and_invalid_timing() -> None:
    with pytest.raises(TypeError, match="upstream bounded speech recognizer"):
        run_capability("audio_understanding", b"raw-audio")

    with pytest.raises(ValueError, match="timing"):
        run_capability(
            "audio_understanding",
            [{"text": "bad timing", "start": 2.0, "end": 1.0}],
        )


def test_audio_understanding_rejects_unbounded_or_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="character limit"):
        run_capability("audio_understanding", ["abcdefghij"], max_chars=5)

    with pytest.raises(ValueError, match="confidence"):
        run_capability(
            "audio_understanding",
            [{"text": "bad confidence", "confidence": 1.5}],
        )
