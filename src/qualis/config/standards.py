"""Validate a Rule's metadata against a programme's RuleMetadataSchema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qualis.domain.models import Rule
    from qualis.domain.standards import RuleMetadataSchema


@dataclass(frozen=True)
class StandardsValidator:
    """Run a Rule through a metadata standard and report missing/invalid fields.

    Returns a list of human-readable issue strings. Empty list = conformant.
    """

    schema: RuleMetadataSchema

    def validate(self, rule: Rule) -> list[str]:
        issues: list[str] = []
        for field in self.schema.fields:
            value = rule.metadata.get(field.name)
            if value is None:
                if field.required:
                    issues.append(
                        f"Rule {rule.id!r} is missing required metadata field "
                        f"{field.name!r}"
                    )
                continue
            if field.allowed_values is not None and value not in field.allowed_values:
                issues.append(
                    f"Rule {rule.id!r} metadata field {field.name!r} has value "
                    f"{value!r}, which is not in allowed_values "
                    f"{field.allowed_values!r}"
                )
        return issues
