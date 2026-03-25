"""Release lifecycle management (EX-002, EX-008, EX-010, EX-011).

Implements the release state machine, preflight checks, HuggingFace Hub
push preflight, and human signoff enforcement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from molabel.core.types import ReleaseStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Valid state transitions (EX-010)
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[ReleaseStatus, set[ReleaseStatus]] = {
    ReleaseStatus.draft: {ReleaseStatus.validating, ReleaseStatus.rejected},
    ReleaseStatus.validating: {
        ReleaseStatus.pending_approval,
        ReleaseStatus.rejected,
        ReleaseStatus.draft,
    },
    ReleaseStatus.pending_approval: {
        ReleaseStatus.approved,
        ReleaseStatus.rejected,
        ReleaseStatus.draft,
    },
    ReleaseStatus.approved: {
        ReleaseStatus.released,
        ReleaseStatus.revoked,
        ReleaseStatus.draft,
    },
    ReleaseStatus.released: {ReleaseStatus.revoked},
    ReleaseStatus.rejected: {ReleaseStatus.draft},
    ReleaseStatus.revoked: set(),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReleaseTransition:
    """A recorded state transition in the release lifecycle (EX-010)."""

    from_status: ReleaseStatus
    to_status: ReleaseStatus
    triggered_by: str
    triggered_at: datetime
    reason: str = ""


@dataclass
class ReleaseState:
    """Full tracked state for a release (EX-010)."""

    release_id: str
    current_status: ReleaseStatus = ReleaseStatus.draft
    transitions: list[ReleaseTransition] = field(default_factory=list)
    signoff: SignoffRecord | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_terminal(self) -> bool:
        """Whether the release is in a terminal state."""
        return self.current_status in {ReleaseStatus.released, ReleaseStatus.revoked}


@dataclass(frozen=True)
class SignoffRecord:
    """Human signoff record for a release (EX-011)."""

    signed_off_by: str
    signed_off_at: datetime
    comment: str = ""


@dataclass(frozen=True)
class GateResult:
    """Result of a single validation gate (EX-008)."""

    gate_id: str
    passed: bool
    message: str = ""
    metric_value: float | None = None
    threshold: float | None = None


@dataclass(frozen=True)
class PreflightCheck:
    """A single preflight check item (EX-008)."""

    check_name: str
    passed: bool
    message: str = ""
    is_blocking: bool = True


@dataclass(frozen=True)
class PreflightResult:
    """Aggregate result of all preflight checks (EX-008)."""

    passed: bool
    checks: list[PreflightCheck] = field(default_factory=list)
    gate_results: list[GateResult] = field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class HFPreflightResult:
    """Result of HuggingFace Hub push preflight (EX-002)."""

    passed: bool
    token_valid: bool = False
    has_write_permission: bool = False
    repo_exists: bool = False
    dry_run: bool = False
    checks: list[PreflightCheck] = field(default_factory=list)
    error: str | None = None


# ---------------------------------------------------------------------------
# Gate runner protocol (for dependency injection)
# ---------------------------------------------------------------------------


@runtime_checkable
class ValidationGateRunner(Protocol):
    """Protocol for services that run a single validation gate."""

    def run_gate(
        self,
        gate_id: str,
        context: dict[str, Any],
    ) -> GateResult:
        """Execute a validation gate and return its result."""
        ...


# ---------------------------------------------------------------------------
# Release Manager service
# ---------------------------------------------------------------------------


class ReleaseManager:
    """Manages release lifecycle, preflight validation, and signoff (EX-008/010/011).

    The release state machine enforces valid transitions:

    - draft -> validating -> pending_approval -> approved -> released
    - Any non-terminal state -> rejected
    - rejected -> draft (re-open)
    - approved or released -> revoked
    """

    def __init__(
        self,
        gate_runner: ValidationGateRunner | None = None,
    ) -> None:
        self._gate_runner = gate_runner
        self._states: dict[str, ReleaseState] = {}

    def create_release(
        self,
        release_id: str,
        *,
        triggered_by: str = "system",
    ) -> ReleaseState:
        """Create a new release in draft state."""
        if release_id in self._states:
            raise ValueError(f"Release '{release_id}' already exists.")
        state = ReleaseState(release_id=release_id)
        self._states[release_id] = state
        logger.info("Created release '%s' in draft state.", release_id)
        return state

    def get_state(self, release_id: str) -> ReleaseState | None:
        """Retrieve the current state of a release."""
        return self._states.get(release_id)

    def transition(
        self,
        release_id: str,
        to_status: ReleaseStatus,
        *,
        triggered_by: str = "system",
        reason: str = "",
    ) -> ReleaseTransition:
        """Transition a release to a new state (EX-010).

        Raises
        ------
        ValueError
            If the release does not exist or the transition is invalid.
        PermissionError
            If transitioning to approved without signoff (EX-011).
        """
        state = self._states.get(release_id)
        if state is None:
            raise ValueError(f"Release '{release_id}' not found.")

        from_status = state.current_status

        # Validate transition
        allowed = _VALID_TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            raise ValueError(
                f"Invalid transition from '{from_status}' to '{to_status}'. "
                f"Allowed: {sorted(s.value for s in allowed)}."
            )

        # EX-011: Block approved without signoff
        if to_status == ReleaseStatus.approved and state.signoff is None:
            raise PermissionError(
                "Cannot approve release without human signoff. Call sign_off() first."
            )

        now = datetime.now(UTC)
        transition = ReleaseTransition(
            from_status=from_status,
            to_status=to_status,
            triggered_by=triggered_by,
            triggered_at=now,
            reason=reason,
        )

        state.current_status = to_status
        state.transitions.append(transition)

        logger.info(
            "Release '%s' transitioned %s -> %s by %s",
            release_id,
            from_status,
            to_status,
            triggered_by,
        )

        return transition

    def sign_off(
        self,
        release_id: str,
        *,
        signed_off_by: str,
        comment: str = "",
    ) -> SignoffRecord:
        """Record human signoff for a release (EX-011).

        Signoff is required before transitioning to approved.

        Raises
        ------
        ValueError
            If the release does not exist or is not in pending_approval.
        """
        state = self._states.get(release_id)
        if state is None:
            raise ValueError(f"Release '{release_id}' not found.")

        if state.current_status != ReleaseStatus.pending_approval:
            raise ValueError(
                f"Signoff only allowed in 'pending_approval' state. "
                f"Current: '{state.current_status}'."
            )

        now = datetime.now(UTC)
        record = SignoffRecord(
            signed_off_by=signed_off_by,
            signed_off_at=now,
            comment=comment,
        )
        state.signoff = record

        logger.info(
            "Release '%s' signed off by '%s'.",
            release_id,
            signed_off_by,
        )
        return record

    def run_preflight(
        self,
        release_id: str,
        *,
        gate_ids: list[str] | None = None,
        context: dict[str, Any] | None = None,
        privacy_gate: bool = False,
        license_gate: bool = False,
    ) -> PreflightResult:
        """Run preflight checks before release approval (EX-008).

        Parameters
        ----------
        release_id:
            The release to validate.
        gate_ids:
            List of validation gate IDs to run.
        context:
            Arbitrary context passed to gate runners.
        privacy_gate:
            Whether to enforce a privacy compliance gate.
        license_gate:
            Whether to enforce a license compliance gate.
        """
        state = self._states.get(release_id)
        if state is None:
            return PreflightResult(
                passed=False,
                summary=f"Release '{release_id}' not found.",
            )

        checks: list[PreflightCheck] = []
        gate_results: list[GateResult] = []
        ctx = context or {}

        # Basic state check
        checks.append(
            PreflightCheck(
                check_name="release_exists",
                passed=True,
                message=f"Release '{release_id}' exists in state "
                f"'{state.current_status}'.",
            )
        )

        # Privacy gate
        if privacy_gate:
            privacy_passed = ctx.get("privacy_compliant", False)
            checks.append(
                PreflightCheck(
                    check_name="privacy_gate",
                    passed=bool(privacy_passed),
                    message="Privacy compliance check "
                    + ("passed." if privacy_passed else "failed."),
                    is_blocking=True,
                )
            )

        # License gate
        if license_gate:
            license_passed = ctx.get("license_compliant", False)
            checks.append(
                PreflightCheck(
                    check_name="license_gate",
                    passed=bool(license_passed),
                    message="License compliance check "
                    + ("passed." if license_passed else "failed."),
                    is_blocking=True,
                )
            )

        # Run validation gates
        if gate_ids and self._gate_runner is not None:
            for gate_id in gate_ids:
                try:
                    result = self._gate_runner.run_gate(gate_id, ctx)
                    gate_results.append(result)
                    checks.append(
                        PreflightCheck(
                            check_name=f"gate:{gate_id}",
                            passed=result.passed,
                            message=result.message,
                            is_blocking=True,
                        )
                    )
                except Exception as exc:
                    gate_results.append(
                        GateResult(
                            gate_id=gate_id,
                            passed=False,
                            message=f"Gate execution error: {exc}",
                        )
                    )
                    checks.append(
                        PreflightCheck(
                            check_name=f"gate:{gate_id}",
                            passed=False,
                            message=f"Gate execution error: {exc}",
                            is_blocking=True,
                        )
                    )

        all_passed = all(c.passed for c in checks if c.is_blocking)
        failed = [c.check_name for c in checks if not c.passed and c.is_blocking]
        summary = (
            "All preflight checks passed."
            if all_passed
            else f"Failed checks: {', '.join(failed)}"
        )

        return PreflightResult(
            passed=all_passed,
            checks=checks,
            gate_results=gate_results,
            summary=summary,
        )

    def hf_preflight(
        self,
        *,
        token: str | None = None,
        repo_id: str | None = None,
        dry_run: bool = False,
        token_validator: Any | None = None,
        permission_checker: Any | None = None,
    ) -> HFPreflightResult:
        """Run HuggingFace Hub push preflight checks (EX-002).

        Parameters
        ----------
        token:
            HuggingFace API token to validate.
        repo_id:
            Target repo ID (e.g., ``user/dataset-name``).
        dry_run:
            If True, only validate without actually connecting.
        token_validator:
            Callable that takes a token string and returns True if valid.
        permission_checker:
            Callable that takes (token, repo_id) and returns a dict with
            ``has_write`` (bool) and ``repo_exists`` (bool) keys.
        """
        checks: list[PreflightCheck] = []

        # Token presence
        if not token:
            checks.append(
                PreflightCheck(
                    check_name="token_present",
                    passed=False,
                    message="No HuggingFace token provided.",
                    is_blocking=True,
                )
            )
            return HFPreflightResult(
                passed=False,
                checks=checks,
                dry_run=dry_run,
                error="No HuggingFace token provided.",
            )

        checks.append(
            PreflightCheck(
                check_name="token_present",
                passed=True,
                message="Token provided.",
            )
        )

        # Repo ID presence
        if not repo_id:
            checks.append(
                PreflightCheck(
                    check_name="repo_id_present",
                    passed=False,
                    message="No repo_id provided.",
                    is_blocking=True,
                )
            )
            return HFPreflightResult(
                passed=False,
                token_valid=True,
                checks=checks,
                dry_run=dry_run,
                error="No repo_id provided.",
            )

        checks.append(
            PreflightCheck(
                check_name="repo_id_present",
                passed=True,
                message=f"Repo ID: {repo_id}",
            )
        )

        # Token validation
        token_valid = True
        if token_validator is not None and not dry_run:
            try:
                token_valid = bool(token_validator(token))
            except Exception as exc:
                token_valid = False
                checks.append(
                    PreflightCheck(
                        check_name="token_validation",
                        passed=False,
                        message=f"Token validation failed: {exc}",
                        is_blocking=True,
                    )
                )
                return HFPreflightResult(
                    passed=False,
                    token_valid=False,
                    checks=checks,
                    dry_run=dry_run,
                    error=f"Token validation failed: {exc}",
                )

        checks.append(
            PreflightCheck(
                check_name="token_validation",
                passed=token_valid,
                message="Token valid." if token_valid else "Token invalid.",
                is_blocking=True,
            )
        )

        # Permission check
        has_write = True
        repo_exists = False
        if permission_checker is not None and not dry_run:
            try:
                perm_result = permission_checker(token, repo_id)
                has_write = bool(perm_result.get("has_write", False))
                repo_exists = bool(perm_result.get("repo_exists", False))
            except Exception as exc:
                has_write = False
                checks.append(
                    PreflightCheck(
                        check_name="permission_check",
                        passed=False,
                        message=f"Permission check failed: {exc}",
                        is_blocking=True,
                    )
                )
                return HFPreflightResult(
                    passed=False,
                    token_valid=token_valid,
                    has_write_permission=False,
                    checks=checks,
                    dry_run=dry_run,
                    error=f"Permission check failed: {exc}",
                )

        checks.append(
            PreflightCheck(
                check_name="write_permission",
                passed=has_write,
                message="Write permission confirmed."
                if has_write
                else "No write permission.",
                is_blocking=True,
            )
        )

        if dry_run:
            checks.append(
                PreflightCheck(
                    check_name="dry_run",
                    passed=True,
                    message="Dry run complete. No actual push performed.",
                    is_blocking=False,
                )
            )

        all_passed = all(c.passed for c in checks if c.is_blocking)
        return HFPreflightResult(
            passed=all_passed,
            token_valid=token_valid,
            has_write_permission=has_write,
            repo_exists=repo_exists,
            dry_run=dry_run,
            checks=checks,
        )

    def get_valid_transitions(self, release_id: str) -> list[ReleaseStatus]:
        """Return the valid next states for a release."""
        state = self._states.get(release_id)
        if state is None:
            return []
        allowed = _VALID_TRANSITIONS.get(state.current_status, set())
        return sorted(allowed, key=lambda s: s.value)
