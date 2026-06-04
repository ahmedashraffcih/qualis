from __future__ import annotations

from pathlib import Path  # noqa: TC003

from qualis.discover.snapshot_store import SnapshotStore
from qualis.domain.snapshot import ColumnSnapshot, ProfileSnapshot


def _sample_snapshot(rule_id: str = "R1") -> ProfileSnapshot:
    return ProfileSnapshot(
        rule_id=rule_id,
        dataset="public",
        table="users",
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
    loaded = store.load("R1")
    assert loaded == snap


def test_save_writes_human_readable_json(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    snap = _sample_snapshot()
    written = store.save(snap)
    text = written.read_text()
    assert "rule_id" in text
    assert "a@x.com" in text
    # sorted keys → "captured_at" sorts before "rule_id"
    assert text.index('"captured_at"') < text.index('"rule_id"')


def test_exists_and_list(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path)
    assert not store.exists("R1")
    assert store.list_rule_ids() == []
    store.save(_sample_snapshot("R1"))
    store.save(_sample_snapshot("R2"))
    assert store.exists("R1")
    assert store.list_rule_ids() == ["R1", "R2"]


def test_store_creates_root_if_missing(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "deeper"
    SnapshotStore(nested)
    assert nested.is_dir()
