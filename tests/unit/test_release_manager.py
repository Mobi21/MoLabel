"""Tests for release lifecycle management (EX-002, EX-008, EX-010, EX-011).

Covers ReleaseManager, state machine transitions, preflight checks,
HuggingFace preflight, and human signoff.
"""

from __future__ import annotations

from typing import Any

import pytest

from molabel.core.release.release_manager import (
    GateResult,
    ReleaseManager,
)
from molabel.core.types import ReleaseStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeGateRunner:
    """A gate runner that returns configurable results."""

    def __init__(self, results: dict[str, bool] | None = None) -> None:
        self._results = results or {}

    def run_gate(self, gate_id: str, context: dict[str, Any]) -> GateResult:
        passed = self._results.get(gate_id, True)
        return GateResult(
            gate_id=gate_id,
            passed=passed,
            message=f"Gate {gate_id} {'passed' if passed else 'failed'}.",
        )


class FailingGateRunner:
    """A gate runner that raises exceptions."""

    def run_gate(self, gate_id: str, context: dict[str, Any]) -> GateResult:
        raise RuntimeError(f"Gate {gate_id} crashed")


# ---------------------------------------------------------------------------
# EX-010: Release lifecycle state machine
# ---------------------------------------------------------------------------


class TestReleaseStateMachine:
    def test_create_release(self) -> None:
        mgr = ReleaseManager()
        state = mgr.create_release("rel-001")
        assert state.release_id == "rel-001"
        assert state.current_status == ReleaseStatus.draft

    def test_create_duplicate_raises(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("rel-001")
        with pytest.raises(ValueError, match="already exists"):
            mgr.create_release("rel-001")

    def test_get_state(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("rel-001")
        state = mgr.get_state("rel-001")
        assert state is not None
        assert state.current_status == ReleaseStatus.draft

    def test_get_state_missing(self) -> None:
        mgr = ReleaseManager()
        assert mgr.get_state("nonexistent") is None

    def test_draft_to_validating(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        t = mgr.transition("r1", ReleaseStatus.validating, triggered_by="user1")
        assert t.from_status == ReleaseStatus.draft
        assert t.to_status == ReleaseStatus.validating
        assert t.triggered_by == "user1"
        assert mgr.get_state("r1").current_status == ReleaseStatus.validating

    def test_validating_to_pending_approval(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        mgr.transition("r1", ReleaseStatus.validating)
        mgr.transition("r1", ReleaseStatus.pending_approval)
        assert mgr.get_state("r1").current_status == ReleaseStatus.pending_approval

    def test_pending_to_approved_requires_signoff(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        mgr.transition("r1", ReleaseStatus.validating)
        mgr.transition("r1", ReleaseStatus.pending_approval)
        with pytest.raises(PermissionError, match="signoff"):
            mgr.transition("r1", ReleaseStatus.approved)

    def test_pending_to_approved_after_signoff(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        mgr.transition("r1", ReleaseStatus.validating)
        mgr.transition("r1", ReleaseStatus.pending_approval)
        mgr.sign_off("r1", signed_off_by="admin")
        t = mgr.transition("r1", ReleaseStatus.approved)
        assert t.to_status == ReleaseStatus.approved

    def test_approved_to_released(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        mgr.transition("r1", ReleaseStatus.validating)
        mgr.transition("r1", ReleaseStatus.pending_approval)
        mgr.sign_off("r1", signed_off_by="admin")
        mgr.transition("r1", ReleaseStatus.approved)
        mgr.transition("r1", ReleaseStatus.released)
        state = mgr.get_state("r1")
        assert state.current_status == ReleaseStatus.released
        assert state.is_terminal is True

    def test_invalid_transition_raises(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        with pytest.raises(ValueError, match="Invalid transition"):
            mgr.transition("r1", ReleaseStatus.released)

    def test_transition_nonexistent_release(self) -> None:
        mgr = ReleaseManager()
        with pytest.raises(ValueError, match="not found"):
            mgr.transition("none", ReleaseStatus.validating)

    def test_rejected_to_draft(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        mgr.transition("r1", ReleaseStatus.rejected)
        mgr.transition("r1", ReleaseStatus.draft)
        assert mgr.get_state("r1").current_status == ReleaseStatus.draft

    def test_revoked_is_terminal(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        mgr.transition("r1", ReleaseStatus.validating)
        mgr.transition("r1", ReleaseStatus.pending_approval)
        mgr.sign_off("r1", signed_off_by="admin")
        mgr.transition("r1", ReleaseStatus.approved)
        mgr.transition("r1", ReleaseStatus.revoked)
        state = mgr.get_state("r1")
        assert state.is_terminal is True
        with pytest.raises(ValueError, match="Invalid transition"):
            mgr.transition("r1", ReleaseStatus.draft)

    def test_transition_history(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        mgr.transition("r1", ReleaseStatus.validating, triggered_by="a")
        mgr.transition("r1", ReleaseStatus.pending_approval, triggered_by="b")

        state = mgr.get_state("r1")
        assert len(state.transitions) == 2
        assert state.transitions[0].triggered_by == "a"
        assert state.transitions[1].triggered_by == "b"

    def test_get_valid_transitions(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        valid = mgr.get_valid_transitions("r1")
        assert ReleaseStatus.validating in valid
        assert ReleaseStatus.rejected in valid
        assert ReleaseStatus.released not in valid

    def test_get_valid_transitions_missing(self) -> None:
        mgr = ReleaseManager()
        assert mgr.get_valid_transitions("nonexistent") == []


# ---------------------------------------------------------------------------
# EX-011: Human signoff
# ---------------------------------------------------------------------------


class TestSignoff:
    def test_signoff_in_pending_approval(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        mgr.transition("r1", ReleaseStatus.validating)
        mgr.transition("r1", ReleaseStatus.pending_approval)
        record = mgr.sign_off("r1", signed_off_by="admin", comment="Looks good")
        assert record.signed_off_by == "admin"
        assert record.comment == "Looks good"
        assert record.signed_off_at is not None

    def test_signoff_wrong_state_raises(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        with pytest.raises(ValueError, match="pending_approval"):
            mgr.sign_off("r1", signed_off_by="admin")

    def test_signoff_nonexistent_release(self) -> None:
        mgr = ReleaseManager()
        with pytest.raises(ValueError, match="not found"):
            mgr.sign_off("none", signed_off_by="admin")

    def test_signoff_tracked_on_state(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        mgr.transition("r1", ReleaseStatus.validating)
        mgr.transition("r1", ReleaseStatus.pending_approval)
        mgr.sign_off("r1", signed_off_by="reviewer_42")
        state = mgr.get_state("r1")
        assert state.signoff is not None
        assert state.signoff.signed_off_by == "reviewer_42"


# ---------------------------------------------------------------------------
# EX-008: Preflight checks
# ---------------------------------------------------------------------------


class TestPreflight:
    def test_preflight_passes_without_gates(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        result = mgr.run_preflight("r1")
        assert result.passed is True
        assert len(result.checks) > 0

    def test_preflight_with_gates(self) -> None:
        runner = FakeGateRunner({"gate_a": True, "gate_b": True})
        mgr = ReleaseManager(gate_runner=runner)
        mgr.create_release("r1")
        result = mgr.run_preflight("r1", gate_ids=["gate_a", "gate_b"])
        assert result.passed is True
        assert len(result.gate_results) == 2

    def test_preflight_fails_with_failing_gate(self) -> None:
        runner = FakeGateRunner({"gate_a": True, "gate_b": False})
        mgr = ReleaseManager(gate_runner=runner)
        mgr.create_release("r1")
        result = mgr.run_preflight("r1", gate_ids=["gate_a", "gate_b"])
        assert result.passed is False
        assert "gate:gate_b" in result.summary

    def test_preflight_nonexistent_release(self) -> None:
        mgr = ReleaseManager()
        result = mgr.run_preflight("nonexistent")
        assert result.passed is False
        assert "not found" in result.summary.lower()

    def test_preflight_privacy_gate(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        result = mgr.run_preflight(
            "r1",
            privacy_gate=True,
            context={"privacy_compliant": True},
        )
        assert result.passed is True
        check_names = [c.check_name for c in result.checks]
        assert "privacy_gate" in check_names

    def test_preflight_privacy_gate_fails(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        result = mgr.run_preflight(
            "r1",
            privacy_gate=True,
            context={"privacy_compliant": False},
        )
        assert result.passed is False

    def test_preflight_license_gate(self) -> None:
        mgr = ReleaseManager()
        mgr.create_release("r1")
        result = mgr.run_preflight(
            "r1",
            license_gate=True,
            context={"license_compliant": True},
        )
        assert result.passed is True

    def test_preflight_gate_exception(self) -> None:
        runner = FailingGateRunner()
        mgr = ReleaseManager(gate_runner=runner)
        mgr.create_release("r1")
        result = mgr.run_preflight("r1", gate_ids=["broken_gate"])
        assert result.passed is False
        assert len(result.gate_results) == 1
        assert result.gate_results[0].passed is False


# ---------------------------------------------------------------------------
# EX-002: HuggingFace preflight
# ---------------------------------------------------------------------------


class TestHFPreflight:
    def test_no_token(self) -> None:
        mgr = ReleaseManager()
        result = mgr.hf_preflight(token=None, repo_id="user/ds")
        assert result.passed is False
        assert result.token_valid is False

    def test_no_repo_id(self) -> None:
        mgr = ReleaseManager()
        result = mgr.hf_preflight(token="valid_token", repo_id=None)
        assert result.passed is False
        assert "repo_id" in (result.error or "").lower()

    def test_dry_run(self) -> None:
        mgr = ReleaseManager()
        result = mgr.hf_preflight(
            token="test_token",
            repo_id="user/dataset",
            dry_run=True,
        )
        assert result.passed is True
        assert result.dry_run is True

    def test_valid_token_and_permissions(self) -> None:
        mgr = ReleaseManager()
        result = mgr.hf_preflight(
            token="valid_token",
            repo_id="user/ds",
            token_validator=lambda t: True,
            permission_checker=lambda t, r: {"has_write": True, "repo_exists": True},
        )
        assert result.passed is True
        assert result.token_valid is True
        assert result.has_write_permission is True
        assert result.repo_exists is True

    def test_invalid_token(self) -> None:
        mgr = ReleaseManager()
        result = mgr.hf_preflight(
            token="bad_token",
            repo_id="user/ds",
            token_validator=lambda t: False,
        )
        assert result.passed is False
        assert result.token_valid is False

    def test_token_validator_exception(self) -> None:
        mgr = ReleaseManager()

        def failing_validator(t: str) -> bool:
            raise ConnectionError("Network error")

        result = mgr.hf_preflight(
            token="token",
            repo_id="user/ds",
            token_validator=failing_validator,
        )
        assert result.passed is False
        assert "Network error" in (result.error or "")

    def test_no_write_permission(self) -> None:
        mgr = ReleaseManager()
        result = mgr.hf_preflight(
            token="valid",
            repo_id="user/ds",
            token_validator=lambda t: True,
            permission_checker=lambda t, r: {"has_write": False, "repo_exists": True},
        )
        assert result.passed is False
        assert result.has_write_permission is False

    def test_permission_checker_exception(self) -> None:
        mgr = ReleaseManager()

        def failing_checker(t: str, r: str) -> dict[str, Any]:
            raise PermissionError("Access denied")

        result = mgr.hf_preflight(
            token="valid",
            repo_id="user/ds",
            token_validator=lambda t: True,
            permission_checker=failing_checker,
        )
        assert result.passed is False
        assert "Access denied" in (result.error or "")
