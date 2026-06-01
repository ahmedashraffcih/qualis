"""In-memory ReferenceDataPort -- dict-backed, for testing and small datasets."""

from __future__ import annotations


class InMemoryReferenceData:
    """ReferenceDataPort backed by a dict.

    Use ``register(reference, key_column, values)`` to load data;
    ``load_values(reference, key_column)`` to retrieve it.
    """

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], list[str]] = {}

    def register(self, reference: str, key_column: str, values: list[str]) -> None:
        self._data[(reference, key_column)] = list(values)

    def load_values(self, reference: str, key_column: str) -> list[str]:
        key = (reference, key_column)
        if key not in self._data:
            raise KeyError(
                f"Reference {reference!r} with key column {key_column!r} not registered"
            )
        return list(self._data[key])
