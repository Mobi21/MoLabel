"""Release management services for MoLabel core.

Provides release lifecycle state machine, preflight validation, human signoff,
frozen views, and release inspection/diff capabilities.
"""

from molabel.core.release.frozen_views import (
    FrozenSplit,
    FrozenView,
    FrozenViewManager,
    ReadinessReport,
    ReportManifest,
    ValidationSummary,
    ViewSnapshot,
)
from molabel.core.release.release_inspector import (
    ReleaseDiff,
    ReleaseInspection,
    ReleaseInspector,
    ReleaseReport,
)
from molabel.core.release.release_manager import (
    GateResult,
    HFPreflightResult,
    PreflightCheck,
    PreflightResult,
    ReleaseManager,
    ReleaseState,
    ReleaseTransition,
    SignoffRecord,
)

__all__ = [
    # frozen_views
    "FrozenSplit",
    "FrozenView",
    "FrozenViewManager",
    "ReadinessReport",
    "ReportManifest",
    "ValidationSummary",
    "ViewSnapshot",
    # release_inspector
    "ReleaseDiff",
    "ReleaseInspection",
    "ReleaseInspector",
    "ReleaseReport",
    # release_manager
    "GateResult",
    "HFPreflightResult",
    "PreflightCheck",
    "PreflightResult",
    "ReleaseManager",
    "ReleaseState",
    "ReleaseTransition",
    "SignoffRecord",
]
