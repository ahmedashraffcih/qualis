"""Pluggable standards / metadata schemas.

Every programme has its own required metadata model: ID, dimension,
CDE flag, glossary term, owner, threshold, frequency, etc. A rule is
"not finished" until it conforms to that programme's standard.

This module defines the schema; ``src/qualis/config/standards.py`` adds
the validator that checks rule.metadata against the schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StandardField:
    """One field a programme requires (or permits) on rule metadata.

    name           -- key the rule's metadata dict must use
    required       -- if True, validator fails when rule omits this field
    description    -- human-readable explanation (surfaced in CLI prompts)
    allowed_values -- if set, the value must be one of these (enum-style)
    """

    name: str
    required: bool = False
    description: str = ""
    allowed_values: list[str] | None = None


@dataclass(frozen=True)
class RuleMetadataSchema:
    """The set of fields a programme requires on every rule.

    The empty schema (``RuleMetadataSchema()``) is the framework default
    and validates anything. Programmes plug in their own schema via
    ``StandardsValidator(schema=...)``.
    """

    fields: list[StandardField] = field(default_factory=list)

    def get_field(self, name: str) -> StandardField | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None
