"""Regression test for issue #843: MemoryStore.add must validate metadata types."""
from pathlib import Path

import pytest

from genesis.memory import MemoryStore


@pytest.mark.parametrize(
    "bad",
    [
        {"tags": {"a", "b"}},
        {"blob": b"raw bytes"},
        {"obj": object()},
        {"nested": {"inner": {"x", "y"}}},
        {"items": [1, object()]},
        {1: "non-string key"},
        {"ratio": float("nan")},
    ],
)
def test_add_rejects_unsupported_metadata_but_keeps_json_safe_metadata(tmp_path: Path, bad):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    good = {"name": "x", "count": 3, "score": 0.5, "ok": True, "none": None, "reasons": ["a", "b"], "nested": {"k": 1}}
    item = store.add(
        memory_type="semantic",
        topic="metadata check",
        content="good metadata",
        source_type="test",
        source_ref="good",
        metadata=good,
    )
    assert item.metadata == good
    with pytest.raises(ValueError, match="metadata"):
        store.add(
            memory_type="semantic",
            topic="metadata check",
            content="bad metadata",
            source_type="test",
            source_ref="bad",
            metadata=bad,
        )
