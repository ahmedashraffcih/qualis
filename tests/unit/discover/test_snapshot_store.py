from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest

from qualis.discover.snapshot_store import CorruptSnapshotError, SnapshotStore
from qualis.domain.snapshot import ColumnSnapshot, ProfileSnapshot


def _sample_snapshot(table: str = "users") -> ProfileSnapshot:
    return ProfileSnapshot(
        table=table,
        captured_at="2026-06-01T12:00:00+00:00",
        row_count=1000,
        columns=(
            ColumnSnapshot(
                column="email",
                inferred_type="string",
                total_count=1000,
                null_count=10,
                null_fraction=0.01,
                distinct_count=995,
                distinct_fraction=0.995,
                min_value=None,
                max_value=None,
                sample_values=("a@x.com", "b@x.com"),
            ),
        ),
    )


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    snap = _sample_snapshot()
    store.save(snap)
    loaded = store.load("users")
    assert loaded == snap


def test_save_writes_human_readable_json(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    written = store.save(_sample_snapshot())
    text = written.read_text()
    assert "captured_at" in text
    assert "a@x.com" in text


def test_exists_and_list(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    assert not store.exists("users")
    assert store.list_tables() == []
    store.save(_sample_snapshot("users"))
    store.save(_sample_snapshot("orders"))
    assert store.exists("users")
    assert sorted(store.list_tables()) == ["orders", "users"]


def test_store_creates_root_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "deeper"
    SnapshotStore(nested)
    assert nested.is_dir()


def test_qualified_table_name_is_filename_safe(tmp_path: Path) -> None:
    """A dataset like ``schema.users`` becomes a flat filename."""
    store = SnapshotStore(tmp_path)
    snap = _sample_snapshot("public.users")
    written = store.save(snap)
    assert written.name == "public_users.json"
    loaded = store.load("public.users")
    assert loaded.table == "public.users"


def test_corrupted_json_raises_clear_error(tmp_path: Path) -> None:
    """Regression: malformed JSON used to raise json.JSONDecodeError stack trace."""
    store = SnapshotStore(tmp_path)
    bad = store.path_for("broken")
    bad.write_text("{ this is not valid json")
    with pytest.raises(CorruptSnapshotError, match="not valid JSON"):
        store.load("broken")


def test_shape_mismatch_raises_clear_error(tmp_path: Path) -> None:
    """A JSON file with the wrong shape (e.g. v0.4.0 per-rule format) gives a clear error."""
    store = SnapshotStore(tmp_path)
    legacy = store.path_for("legacy_table")
    # Older shape used ``rule_id`` and ``dataset`` keys; missing ``table``.
    legacy.write_text(
        '{"rule_id": "R1", "dataset": "ds", "captured_at": "x", '
        '"row_count": 10, "columns": []}'
    )
    with pytest.raises(CorruptSnapshotError, match="unexpected shape"):
        store.load("legacy_table")
