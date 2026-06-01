"""ReferenceDataPort -- load the set of valid values for a reference table.

Used by the ``reference_lookup`` check to verify that values in a target
column resolve to known values in a reference dataset.

Implementations can source reference data from anywhere: a file (CSV/Parquet),
a database table, an HTTP endpoint, a hardcoded list. The check engine
doesn't care.
"""

from __future__ import annotations

from typing import Protocol


class ReferenceDataPort(Protocol):
    def load_values(self, reference: str, key_column: str) -> list[str]:
        """Return the set of valid values for *key_column* in *reference*.

        Raises ``KeyError`` if the reference is not registered / not found.
        """
        ...
