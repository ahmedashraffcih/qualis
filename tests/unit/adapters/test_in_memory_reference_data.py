from __future__ import annotations

import pytest

from qualis.adapters.in_memory.reference_data import InMemoryReferenceData


def test_register_and_load_values() -> None:
    ref = InMemoryReferenceData()
    ref.register("country_codes", "code", ["US", "GB", "DE"])
    values = ref.load_values("country_codes", "code")
    assert set(values) == {"US", "GB", "DE"}


def test_load_unknown_reference_raises() -> None:
    ref = InMemoryReferenceData()
    with pytest.raises(KeyError):
        ref.load_values("nonexistent", "code")


def test_register_overwrites() -> None:
    ref = InMemoryReferenceData()
    ref.register("x", "y", ["A"])
    ref.register("x", "y", ["A", "B"])
    assert set(ref.load_values("x", "y")) == {"A", "B"}
