from __future__ import annotations

import pytest

from qualis.domain.enums import DQDimension, RuleStatus, RuleType, Severity
from qualis.domain.models import Rule
from qualis.domain.params import NotNullParams
from qualis.review.state_machine import (
    InvalidTransitionError,
    accept,
    deprecate,
    reject,
    send_back,
)


def _rule(status: RuleStatus = RuleStatus.DRAFT) -> Rule:
    return Rule(
        id="r", name="r", dimension=DQDimension.COMPLETENESS,
        rule_type=RuleType.AGGREGATE, severity=Severity.CRITICAL,
        dataset="d", column="c", check="not_null", params=NotNullParams(),
        status=status,
    )


class TestAccept:
    def test_draft_to_active(self) -> None:
        r = accept(_rule(RuleStatus.DRAFT), approver="alice")
        assert r.status == RuleStatus.ACTIVE
        assert r.approved_by == "alice"

    def test_needs_evidence_to_active(self) -> None:
        r = accept(_rule(RuleStatus.NEEDS_EVIDENCE), approver="alice")
        assert r.status == RuleStatus.ACTIVE
        assert r.approved_by == "alice"

    def test_active_cannot_be_accepted_again(self) -> None:
        with pytest.raises(InvalidTransitionError):
            accept(_rule(RuleStatus.ACTIVE), approver="alice")

    def test_deprecated_cannot_be_accepted(self) -> None:
        with pytest.raises(InvalidTransitionError):
            accept(_rule(RuleStatus.DEPRECATED), approver="alice")


class TestSendBack:
    def test_draft_to_needs_evidence(self) -> None:
        r = send_back(_rule(RuleStatus.DRAFT), reason="confirm 0 is a valid code")
        assert r.status == RuleStatus.NEEDS_EVIDENCE
        assert r.metadata["needs_evidence_reason"] == "confirm 0 is a valid code"

    def test_active_cannot_be_sent_back(self) -> None:
        with pytest.raises(InvalidTransitionError):
            send_back(_rule(RuleStatus.ACTIVE), reason="x")


class TestReject:
    def test_draft_returns_none(self) -> None:
        """Reject removes the rule entirely — represented by None."""
        assert reject(_rule(RuleStatus.DRAFT)) is None

    def test_needs_evidence_returns_none(self) -> None:
        assert reject(_rule(RuleStatus.NEEDS_EVIDENCE)) is None

    def test_active_cannot_be_rejected(self) -> None:
        """Active rules must be deprecated, not rejected."""
        with pytest.raises(InvalidTransitionError):
            reject(_rule(RuleStatus.ACTIVE))


class TestDeprecate:
    def test_active_to_deprecated(self) -> None:
        r = deprecate(_rule(RuleStatus.ACTIVE), date="2026-05-31")
        assert r.status == RuleStatus.DEPRECATED
        assert r.deprecated_at == "2026-05-31"

    def test_draft_cannot_be_deprecated(self) -> None:
        """Only active rules can be deprecated; drafts should be rejected."""
        with pytest.raises(InvalidTransitionError):
            deprecate(_rule(RuleStatus.DRAFT), date="2026-05-31")
