from __future__ import annotations

from pathlib import Path

import pytest

from qualis.config.context_loader import load_context_from_file
from qualis.domain.context import DatasetContext

FIXTURE = (
    Path(__file__).parent.parent.parent / "fixtures" / "context" / "example_context.yaml"
)


def test_loads_dataset_name() -> None:
    ctx = load_context_from_file(FIXTURE)
    assert isinstance(ctx, DatasetContext)
    assert ctx.dataset == "accidents"


def test_loads_business_grain() -> None:
    ctx = load_context_from_file(FIXTURE)
    assert ctx.business_grain is not None
    assert "accident_id" in ctx.business_grain


def test_loads_columns() -> None:
    ctx = load_context_from_file(FIXTURE)
    assert "severity_code" in ctx.columns
    assert "location_id" in ctx.columns


def test_loads_sentinels() -> None:
    ctx = load_context_from_file(FIXTURE)
    severity = ctx.columns["severity_code"]
    assert len(severity.sentinels) == 1
    assert severity.sentinels[0].value == "0"
    assert severity.sentinels[0].meaning == "unknown"


def test_loads_exceptions() -> None:
    ctx = load_context_from_file(FIXTURE)
    severity = ctx.columns["severity_code"]
    assert severity.exceptions == ["LEGACY_FATAL"]


def test_loads_notes() -> None:
    ctx = load_context_from_file(FIXTURE)
    assert "data-entry placeholder" in ctx.columns["severity_code"].notes
    assert "unmapped roads" in ctx.columns["location_id"].notes


def test_column_without_sentinels_has_empty_list() -> None:
    ctx = load_context_from_file(FIXTURE)
    location = ctx.columns["location_id"]
    assert location.sentinels == []
    assert location.exceptions == []


def test_missing_file_raises_filenotfound(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_context_from_file(tmp_path / "nonexistent.yaml")


def test_minimum_yaml_with_only_dataset(tmp_path: Path) -> None:
    p = tmp_path / "minimal.yaml"
    p.write_text("dataset: my_table\n", encoding="utf-8")
    ctx = load_context_from_file(p)
    assert ctx.dataset == "my_table"
    assert ctx.columns == {}
    assert ctx.business_grain is None


def test_fixture_without_provenance_yields_none() -> None:
    ctx = load_context_from_file(FIXTURE)
    assert ctx.provenance is None


def test_loads_provenance_block(tmp_path: Path) -> None:
    p = tmp_path / "ctx.yaml"
    p.write_text(
        "dataset: predictions\n"
        "provenance:\n"
        "  model_id: claude-opus-4-8\n"
        "  checkpoint: ckpt-2026-05-30\n",
        encoding="utf-8",
    )
    ctx = load_context_from_file(p)
    assert ctx.provenance is not None
    assert ctx.provenance.model_id == "claude-opus-4-8"
    assert ctx.provenance.checkpoint == "ckpt-2026-05-30"


def test_provenance_partial_fields_default_to_none(tmp_path: Path) -> None:
    p = tmp_path / "ctx.yaml"
    p.write_text(
        "dataset: predictions\nprovenance:\n  model_id: m1\n",
        encoding="utf-8",
    )
    ctx = load_context_from_file(p)
    assert ctx.provenance is not None
    assert ctx.provenance.model_id == "m1"
    assert ctx.provenance.checkpoint is None


def test_provenance_unknown_keys_ignored(tmp_path: Path) -> None:
    """Loader convention: unknown keys are dropped, never an error."""
    p = tmp_path / "ctx.yaml"
    p.write_text(
        "dataset: predictions\n"
        "provenance:\n"
        "  model_id: m1\n"
        "  temperature: 0.7\n",
        encoding="utf-8",
    )
    ctx = load_context_from_file(p)
    assert ctx.provenance is not None
    assert ctx.provenance.model_id == "m1"


def test_provenance_values_coerced_to_str(tmp_path: Path) -> None:
    """A numeric checkpoint (YAML int) must come back as a string."""
    p = tmp_path / "ctx.yaml"
    p.write_text(
        "dataset: predictions\nprovenance:\n  checkpoint: 20260530\n",
        encoding="utf-8",
    )
    ctx = load_context_from_file(p)
    assert ctx.provenance is not None
    assert ctx.provenance.checkpoint == "20260530"


def test_empty_provenance_block_yields_none(tmp_path: Path) -> None:
    """`provenance:` with no fields is treated as absent, not an empty shell."""
    p = tmp_path / "ctx.yaml"
    p.write_text("dataset: predictions\nprovenance:\n", encoding="utf-8")
    ctx = load_context_from_file(p)
    assert ctx.provenance is None
