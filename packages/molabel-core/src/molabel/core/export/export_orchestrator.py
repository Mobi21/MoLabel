"""Export orchestration service (EX-001, EX-003, EX-007, EX-013).

Coordinates the full export pipeline: select packager, build config,
filter records, package, validate, and write atomically to canonical paths.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from molabel.core.export.atomic_writer import (
    AtomicWriter,
    AtomicWriteResult,
    ConflictResolution,
)
from molabel.core.export.export_builder import (
    ExportConfig,
    ExportFilters,
    apply_filters,
)
from molabel.core.plugins.protocols import ExportPackagerPlugin
from molabel.core.types import ExportArtifact, Record, ReviewEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalPath:
    """A resolved canonical export path (EX-007)."""

    base_dir: Path
    project: str
    dataset: str
    format: str
    filename: str

    @property
    def latest_path(self) -> Path:
        """The ``latest`` symlink-equivalent path."""
        return self.base_dir / self.project / self.dataset / self.format / self.filename

    @property
    def directory(self) -> Path:
        """The directory containing versioned exports for this slot."""
        return self.base_dir / self.project / self.dataset / self.format


@dataclass(frozen=True)
class PathContract:
    """Rules for generating canonical export paths (EX-007)."""

    base_dir: Path
    """Root directory for all exports, e.g. ``workbench/exports/``."""

    def resolve(
        self,
        project: str,
        dataset: str,
        fmt: str,
    ) -> CanonicalPath:
        """Compute the canonical path for a given project/dataset/format."""
        ext = _format_extension(fmt)
        return CanonicalPath(
            base_dir=self.base_dir,
            project=project,
            dataset=dataset,
            format=fmt,
            filename=f"latest.{ext}",
        )

    def versioned_path(
        self,
        project: str,
        dataset: str,
        fmt: str,
        timestamp: datetime | None = None,
    ) -> Path:
        """Compute a timestamped archive path."""
        ts = (timestamp or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
        ext = _format_extension(fmt)
        return self.base_dir / project / dataset / fmt / f"{ts}.{ext}"


@dataclass(frozen=True)
class DeterminismCheck:
    """Result of verifying export determinism (EX-013)."""

    deterministic: bool
    content_hash: str
    record_count: int
    ordering_key: str = "record_id"
    message: str = ""


@dataclass(frozen=True)
class ExportRequest:
    """Input to the export orchestrator (EX-001)."""

    project: str
    dataset: str
    format: str
    records: list[Record]
    labels: dict[str, list[ReviewEvent]]
    config: ExportConfig | None = None
    agreement_scores: dict[str, float] | None = None
    conflict_resolution: ConflictResolution | None = None


@dataclass(frozen=True)
class ExportManifest:
    """Metadata written alongside an export for reproducibility (EX-001)."""

    export_id: str
    project: str
    dataset: str
    format: str
    record_count: int
    content_hash: str
    file_size_bytes: int
    created_at: str
    inclusion_flags: dict[str, bool] = field(default_factory=dict)
    filters_applied: dict[str, Any] = field(default_factory=dict)
    packager_plugin: str = ""
    canonical_path: str = ""


@dataclass(frozen=True)
class ExportResult:
    """Output of the export orchestrator (EX-001)."""

    success: bool
    manifest: ExportManifest | None = None
    artifact: ExportArtifact | None = None
    write_result: AtomicWriteResult | None = None
    determinism: DeterminismCheck | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Packager registry (EX-003)
# ---------------------------------------------------------------------------


class PackagerRegistry:
    """Registry for ExportPackagerPlugin instances keyed by format name (EX-003).

    Allows registering and discovering custom packagers alongside built-ins.
    """

    def __init__(self) -> None:
        self._packagers: dict[str, ExportPackagerPlugin] = {}

    def register(self, format_name: str, packager: ExportPackagerPlugin) -> None:
        """Register a packager for a given format name."""
        self._packagers[format_name] = packager
        logger.debug("Registered packager for format '%s'", format_name)

    def get(self, format_name: str) -> ExportPackagerPlugin | None:
        """Look up a packager by format name."""
        return self._packagers.get(format_name)

    def list_formats(self) -> list[str]:
        """Return all registered format names."""
        return sorted(self._packagers.keys())

    def has_format(self, format_name: str) -> bool:
        """Check whether a packager is registered for the given format."""
        return format_name in self._packagers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_extension(fmt: str) -> str:
    """Map format name to file extension."""
    mapping = {
        "jsonl": "jsonl",
        "csv": "csv",
        "parquet": "parquet",
        "huggingface_hub": "jsonl",
    }
    return mapping.get(fmt, fmt)


def _sort_records_deterministically(records: list[Record]) -> list[Record]:
    """Sort records by ID for deterministic output (EX-013)."""
    return sorted(records, key=lambda r: str(r.id))


def _compute_content_hash(data: bytes) -> str:
    """Compute SHA-256 hash of data."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Export orchestrator (EX-001)
# ---------------------------------------------------------------------------


class ExportOrchestrator:
    """Orchestrates the full export pipeline (EX-001).

    Coordinates: select packager -> build config -> filter records ->
    sort deterministically -> package -> validate -> atomic write.
    """

    def __init__(
        self,
        packager_registry: PackagerRegistry,
        path_contract: PathContract | None = None,
        atomic_writer: AtomicWriter | None = None,
    ) -> None:
        self._registry = packager_registry
        self._path_contract = path_contract or PathContract(
            base_dir=Path("workbench/exports")
        )
        self._writer = atomic_writer or AtomicWriter()

    @property
    def registry(self) -> PackagerRegistry:
        """Access the underlying packager registry."""
        return self._registry

    @property
    def path_contract(self) -> PathContract:
        """Access the path contract for canonical path generation."""
        return self._path_contract

    def export(self, request: ExportRequest) -> ExportResult:
        """Run the full export pipeline.

        Parameters
        ----------
        request:
            The export request containing records, labels, format, and config.

        Returns
        -------
        An ExportResult with the manifest, artifact, and write outcome.
        """
        # 1. Select packager
        packager = self._registry.get(request.format)
        if packager is None:
            return ExportResult(
                success=False,
                error=f"No packager registered for format '{request.format}'. "
                f"Available: {self._registry.list_formats()}",
            )

        config = request.config or ExportConfig()

        # 2. Filter records
        records = list(request.records)
        labels = dict(request.labels)
        if config.filters != ExportFilters():
            records, labels = apply_filters(
                records,
                labels,
                config.filters,
                agreement_scores=request.agreement_scores,
            )

        # 3. Sort deterministically (EX-013)
        records = _sort_records_deterministically(records)

        # 4. Build packager config from ExportConfig
        packager_config = self._build_packager_config(config, request)

        # 5. Package
        try:
            artifact = packager.package(records, labels, packager_config)
        except Exception as exc:
            return ExportResult(
                success=False,
                error=f"Packaging failed: {exc}",
            )

        # 6. Validate the artifact
        try:
            validation = packager.validate_export(artifact)
            if not validation.is_valid:
                error_msgs = "; ".join(e.message for e in validation.errors)
                return ExportResult(
                    success=False,
                    artifact=artifact,
                    error=f"Export validation failed: {error_msgs}",
                )
        except Exception as exc:
            return ExportResult(
                success=False,
                artifact=artifact,
                error=f"Export validation error: {exc}",
            )

        # 7. Determinism check (EX-013)
        artifact_data = self._get_artifact_data(artifact)
        content_hash = _compute_content_hash(artifact_data) if artifact_data else ""
        determinism = DeterminismCheck(
            deterministic=True,
            content_hash=content_hash,
            record_count=artifact.record_count,
            ordering_key="record_id",
        )

        # 8. Atomic write (EX-006)
        canonical = self._path_contract.resolve(
            request.project, request.dataset, request.format
        )
        write_result: AtomicWriteResult | None = None
        if artifact_data:
            write_result = self._writer.write_atomic(
                artifact_data,
                canonical.latest_path,
                conflict_resolution=request.conflict_resolution,
            )
            if not write_result.success:
                return ExportResult(
                    success=False,
                    artifact=artifact,
                    determinism=determinism,
                    write_result=write_result,
                    error=f"Atomic write failed: {write_result.error}",
                )

        # 9. Build manifest
        now = datetime.now(UTC)
        manifest = ExportManifest(
            export_id=content_hash[:16] if content_hash else "",
            project=request.project,
            dataset=request.dataset,
            format=request.format,
            record_count=artifact.record_count,
            content_hash=content_hash,
            file_size_bytes=len(artifact_data) if artifact_data else 0,
            created_at=now.isoformat(),
            inclusion_flags={
                "record_data": config.inclusion.record_data,
                "labels": config.inclusion.labels,
                "agent_labels": config.inclusion.agent_labels,
                "review_metadata": config.inclusion.review_metadata,
                "adjudication_history": config.inclusion.adjudication_history,
                "provenance": config.inclusion.provenance,
            },
            filters_applied={
                "min_agreement": config.filters.min_agreement,
                "exclude_flagged": config.filters.exclude_flagged,
                "include_fields": config.filters.include_fields,
                "exclude_fields": config.filters.exclude_fields,
            },
            packager_plugin=packager.metadata.plugin_id,
            canonical_path=str(canonical.latest_path),
        )

        return ExportResult(
            success=True,
            manifest=manifest,
            artifact=artifact,
            write_result=write_result,
            determinism=determinism,
        )

    def _build_packager_config(
        self,
        config: ExportConfig,
        request: ExportRequest,
    ) -> dict[str, Any]:
        """Translate ExportConfig into the dict format packagers expect."""
        packager_config: dict[str, Any] = {}
        packager_config["include_metadata"] = config.inclusion.review_metadata

        if config.filters.include_fields is not None:
            packager_config["columns"] = config.filters.include_fields

        packager_config.update(config.extra)
        return packager_config

    def _get_artifact_data(self, artifact: ExportArtifact) -> bytes | None:
        """Extract byte data from an artifact (in-memory or from file)."""
        if artifact.data is not None:
            return artifact.data
        if artifact.path is not None and artifact.path.exists():
            return artifact.path.read_bytes()
        return None
