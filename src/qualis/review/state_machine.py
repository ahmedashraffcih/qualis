"""Three-state lifecycle for rules: draft → needs_evidence → active.

(plus a terminal ``deprecated`` state for retirement.)

Returns new immutable Rule objects; never mutates in-place.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from qualis.domain.enums import RuleStatus

if TYPE_CHECKING:
    from qualis.domain.models import Rule


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""


def accept(rule: Rule, approver: str) -> Rule:
    """Promote a draft or needs_evidence rule to active.

    Records the approver. Active and deprecated rules cannot be accepted.
    """
    if rule.status not in (RuleStatus.DRAFT, RuleStatus.NEEDS_EVIDENCE):
        raise InvalidTransitionError(
            f"Cannot accept rule {rule.id!r} in status {rule.status.value!r} "
            f"(only DRAFT or NEEDS_EVIDENCE can be accepted)"
        )
    return dataclasses.replace(rule, status=RuleStatus.ACTIVE, approved_by=approver)


def send_back(rule: Rule, reason: str) -> Rule:
    """Move a draft rule to needs_evidence with a recorded reason.

    Only DRAFT rules can be sent back (an ACTIVE rule should be edited
    or deprecated; a NEEDS_EVIDENCE rule should be re-reviewed).
    """
    if rule.status != RuleStatus.DRAFT:
        raise InvalidTransitionError(
            f"Cannot send back rule {rule.id!r} in status {rule.status.value!r} "
            "(only DRAFT can be sent back)"
        )
    new_metadata = {**rule.metadata, "needs_evidence_reason": reason}
    return dataclasses.replace(
        rule,
        status=RuleStatus.NEEDS_EVIDENCE,
        metadata=new_metadata,
    )


def reject(rule: Rule) -> Rule | None:
    """Reject a draft or needs_evidence rule.

    Returns ``None`` to signal the rule should be dropped from the
    rulebook entirely. ACTIVE rules cannot be rejected — use deprecate.
    """
    if rule.status not in (RuleStatus.DRAFT, RuleStatus.NEEDS_EVIDENCE):
        raise InvalidTransitionError(
            f"Cannot reject rule {rule.id!r} in status {rule.status.value!r} "
            "(active rules must be deprecated)"
        )
    return None


def deprecate(rule: Rule, date: str) -> Rule:
    """Retire an active rule with an ISO date.

    Only ACTIVE rules can be deprecated.
    """
    if rule.status != RuleStatus.ACTIVE:
        raise InvalidTransitionError(
            f"Cannot deprecate rule {rule.id!r} in status {rule.status.value!r} "
            "(only ACTIVE rules can be deprecated)"
        )
    return dataclasses.replace(
        rule, status=RuleStatus.DEPRECATED, deprecated_at=date,
    )
