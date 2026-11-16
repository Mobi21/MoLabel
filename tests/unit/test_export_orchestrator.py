"""Tests for export orchestration (EX-001, EX-003, EX-007, EX-013, EX-014).

Covers ExportOrchestrator, PackagerRegistry, PathContract, CanonicalPath,
DeterminismCheck, and conflict resolution.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from molabel.core.export.atomic_writer import ConflictResolution
from molabel.core.export.export_builder import (
    ExportBuilder,
)
from molabel.core.export.export_orchestrator import (
    ExportOrchestrator,
    ExportRequest,
    ExportResult,
    PackagerRegistry,
    PathContract,
)
from molabel.core.types import (
    ExportArtifact,
    PluginMetadata,
    Record,
    ReviewEvent,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DATASET_ID = UUID("00000000-0000-0000-0000-000000000001")


def _make_record(
    text: str = "sample",
    record_id: UUID | None = None,
) -> Record:
    rid = record_id or uuid4()
    return Record(
        id=rid,
        dataset_id=_DATASET_ID,
        stable_fields={"text": text},
        payload={"text": text},
    )


def _make_review_event(record_id: UUID, labels: dict[str, Any]) -> ReviewEvent:
    return ReviewEvent(
        id=uuid4(),
        record_id=record_id,
        source="human",
        decision="accept",
        labels=labels,
    )


class FakePackager:
    """Minimal ExportPackagerPlugin for testing."""

    def __init__(self, fmt: str = "jsonl") -> None:
        self._fmt = fmt
        self._metadata = PluginMetadata(
            plugin_id=f"test.exporter.{fmt}",
            version="0.1.0",
            compatible_core=">=0.1",
            description=f"Test {fmt} exporter",
        )

    @property
    def metadata(self) -> PluginMetadata:
        return self._metadata

    @property
    def supported_formats(self) -> list[str]:
        return [self._fmt]

    def package(
        self,
        records: list[Record],
        labels: dict[str, list[ReviewEvent]],
        config: dict[str, Any],
    ) -> ExportArtifact:
        lines = []
        for r in records:
            text = r.stable_fields.get("text", "")
            lines.append(f'{{"id": "{r.id}", "text": "{text}"}}')
        data = ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
        return ExportArtifact(
            data=data,
            format=self._fmt,
            record_count=len(records),
            checksum=hashlib.sha256(data).hexdigest(),
        )

    def validate_export(self, artifact: ExportArtifact) -> ValidationResult:
        return ValidationResult(is_valid=True)

    def get_export_schema(self) -> dict[str, Any]:
        return {"format_notes": f"Test {self._fmt} format"}


class FailingPackager(FakePackager):
    """A packager that raises during package()."""

    def package(
        self,
        records: list[Record],
        labels: dict[str, list[ReviewEvent]],
        config: dict[str, Any],
    ) -> ExportArtifact:
        raise RuntimeError("Packaging failed")


class InvalidPackager(FakePackager):
    """A packager whose validate_export always fails."""

    def validate_export(self, artifact: ExportArtifact) -> ValidationResult:
        from molabel.core.types import ValidationError

        return ValidationResult(
            is_valid=False,
            errors=[ValidationError(message="Bad export data")],
        )


# ---------------------------------------------------------------------------
# EX-003: PackagerRegistry
# ---------------------------------------------------------------------------


class TestPackagerRegistry:
    def test_register_and_get(self) -> None:
        registry = PackagerRegistry()
        packager = FakePackager("jsonl")
        registry.register("jsonl", packager)
        assert registry.get("jsonl") is packager

    def test_get_missing_returns_none(self) -> None:
        registry = PackagerRegistry()
        assert registry.get("nonexistent") is None

    def test_list_formats(self) -> None:
        registry = PackagerRegistry()
        registry.register("csv", FakePackager("csv"))
        registry.register("jsonl", FakePackager("jsonl"))
        assert registry.list_formats() == ["csv", "jsonl"]

    def test_has_format(self) -> None:
        registry = PackagerRegistry()
        registry.register("parquet", FakePackager("parquet"))
        assert registry.has_format("parquet") is True
        assert registry.has_format("csv") is False

    def test_register_overwrites(self) -> None:
        registry = PackagerRegistry()
        p1 = FakePackager("jsonl")
        p2 = FakePackager("jsonl")
        registry.register("jsonl", p1)
        registry.register("jsonl", p2)
        assert registry.get("jsonl") is p2

    def test_register_multiple_formats(self) -> None:
        registry = PackagerRegistry()
        registry.register("jsonl", FakePackager("jsonl"))
        registry.register("csv", FakePackager("csv"))
        registry.register("parquet", FakePackager("parquet"))
        assert len(registry.list_formats()) == 3


# ---------------------------------------------------------------------------
# EX-007: PathContract and CanonicalPath
# ---------------------------------------------------------------------------


class TestPathContract:
    def test_resolve_jsonl(self) -> None:
        contract = PathContract(base_dir=Path("workbench/exports"))
        cp = contract.resolve("my_project", "my_dataset", "jsonl")
        assert cp.latest_path == Path(
            "workbench/exports/my_project/my_dataset/jsonl/latest.jsonl"
        )

    def test_resolve_csv(self) -> None:
        contract = PathContract(base_dir=Path("workbench/exports"))
        cp = contract.resolve("proj", "ds", "csv")
        assert cp.filename == "latest.csv"

    def test_resolve_parquet(self) -> None:
        contract = PathContract(base_dir=Path("exports"))
        cp = contract.resolve("p", "d", "parquet")
        assert cp.latest_path == Path("exports/p/d/parquet/latest.parquet")

    def test_directory(self) -> None:
        contract = PathContract(base_dir=Path("out"))
        cp = contract.resolve("proj", "ds", "jsonl")
        assert cp.directory == Path("out/proj/ds/jsonl")

    def test_versioned_path(self) -> None:
        from datetime import UTC, datetime

        contract = PathContract(base_dir=Path("workbench/exports"))
        ts = datetime(2026, 3, 24, 12, 0, 0, tzinfo=UTC)
        vp = contract.versioned_path("proj", "ds", "jsonl", timestamp=ts)
        assert vp == Path("workbench/exports/proj/ds/jsonl/20260324T120000Z.jsonl")

    def test_versioned_path_auto_timestamp(self) -> None:
        contract = PathContract(base_dir=Path("out"))
        vp = contract.versioned_path("p", "d", "csv")
        assert vp.suffix == ".csv"
        assert "p/d/csv/" in vp.as_posix()


# ---------------------------------------------------------------------------
# EX-001: ExportOrchestrator
# ---------------------------------------------------------------------------


class TestExportOrchestrator:
    def _make_orchestrator(
        self, tmp_path: Path, packager: Any | None = None
    ) -> ExportOrchestrator:
        registry = PackagerRegistry()
        pkg = packager or FakePackager("jsonl")
        registry.register("jsonl", pkg)
        contract = PathContract(base_dir=tmp_path / "exports")
        return ExportOrchestrator(
            packager_registry=registry,
            path_contract=contract,
        )

    def test_export_success(self, tmp_path: Path) -> None:
        orchestrator = self._make_orchestrator(tmp_path)
        r1 = _make_record("hello")
        labels = {str(r1.id): [_make_review_event(r1.id, {"sentiment": "pos"})]}

        request = ExportRequest(
            project="proj",
            dataset="ds",
            format="jsonl",
            records=[r1],
            labels=labels,
        )
        result = orchestrator.export(request)

        assert result.success is True
        assert result.manifest is not None
        assert result.manifest.record_count == 1
        assert result.manifest.format == "jsonl"
        assert result.manifest.project == "proj"
        assert result.determinism is not None
        assert result.determinism.deterministic is True

    def test_export_unknown_format(self, tmp_path: Path) -> None:
        orchestrator = self._make_orchestrator(tmp_path)
        request = ExportRequest(
            project="proj",
            dataset="ds",
            format="unknown_format",
            records=[],
            labels={},
        )
        result = orchestrator.export(request)
        assert result.success is False
        assert "No packager" in (result.error or "")

    def test_export_packaging_failure(self, tmp_path: Path) -> None:
        orchestrator = self._make_orchestrator(tmp_path, FailingPackager("jsonl"))
        request = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[_make_record()],
            labels={},
        )
        result = orchestrator.export(request)
        assert result.success is False
        assert "Packaging failed" in (result.error or "")

    def test_export_validation_failure(self, tmp_path: Path) -> None:
        orchestrator = self._make_orchestrator(tmp_path, InvalidPackager("jsonl"))
        request = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[_make_record()],
            labels={},
        )
        result = orchestrator.export(request)
        assert result.success is False
        assert "validation failed" in (result.error or "").lower()

    def test_export_writes_to_canonical_path(self, tmp_path: Path) -> None:
        orchestrator = self._make_orchestrator(tmp_path)
        r1 = _make_record("test")
        request = ExportRequest(
            project="proj",
            dataset="ds",
            format="jsonl",
            records=[r1],
            labels={},
            conflict_resolution=ConflictResolution.force("test"),
        )
        result = orchestrator.export(request)
        assert result.success is True
        expected_path = tmp_path / "exports/proj/ds/jsonl/latest.jsonl"
        assert expected_path.exists()

    def test_export_manifest_has_correct_fields(self, tmp_path: Path) -> None:
        orchestrator = self._make_orchestrator(tmp_path)
        request = ExportRequest(
            project="myproj",
            dataset="myds",
            format="jsonl",
            records=[_make_record()],
            labels={},
        )
        result = orchestrator.export(request)
        assert result.success
        m = result.manifest
        assert m is not None
        assert m.project == "myproj"
        assert m.dataset == "myds"
        assert m.format == "jsonl"
        assert m.content_hash != ""
        assert m.file_size_bytes > 0
        assert "labels" in m.inclusion_flags

    def test_export_with_config(self, tmp_path: Path) -> None:
        orchestrator = self._make_orchestrator(tmp_path)
        config = ExportBuilder().include_labels().include_agent_labels().build()
        request = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[_make_record()],
            labels={},
            config=config,
        )
        result = orchestrator.export(request)
        assert result.success
        assert result.manifest is not None
        assert result.manifest.inclusion_flags["agent_labels"] is True


# ---------------------------------------------------------------------------
# EX-013: Export determinism
# ---------------------------------------------------------------------------


class TestExportDeterminism:
    def test_records_sorted_by_id(self, tmp_path: Path) -> None:
        """Verify records are sorted by ID for deterministic output."""
        registry = PackagerRegistry()
        registry.register("jsonl", FakePackager("jsonl"))
        contract = PathContract(base_dir=tmp_path / "exports")
        orchestrator = ExportOrchestrator(
            packager_registry=registry,
            path_contract=contract,
        )

        # Create records with specific IDs (out of order)
        r1 = _make_record("z_last", UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
        r2 = _make_record("a_first", UUID("00000000-0000-0000-0000-000000000002"))

        request = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[r1, r2],  # deliberately out of order
            labels={},
        )
        result = orchestrator.export(request)
        assert result.success
        assert result.determinism is not None
        assert result.determinism.deterministic is True
        assert result.determinism.ordering_key == "record_id"

    def test_deterministic_hash_consistent(self, tmp_path: Path) -> None:
        """Running export twice produces the same content hash."""
        registry = PackagerRegistry()
        registry.register("jsonl", FakePackager("jsonl"))

        r1 = _make_record("hello", UUID("00000000-0000-0000-0000-000000000010"))
        labels: dict[str, list[ReviewEvent]] = {}

        results: list[ExportResult] = []
        for i in range(2):
            contract = PathContract(base_dir=tmp_path / f"exports_{i}")
            orchestrator = ExportOrchestrator(
                packager_registry=registry,
                path_contract=contract,
            )
            request = ExportRequest(
                project="p",
                dataset="d",
                format="jsonl",
                records=[r1],
                labels=labels,
            )
            results.append(orchestrator.export(request))

        assert results[0].success and results[1].success
        assert results[0].determinism is not None
        assert results[1].determinism is not None
        hash_0 = results[0].determinism.content_hash
        hash_1 = results[1].determinism.content_hash
        assert hash_0 == hash_1

    def test_content_hash_not_empty(self, tmp_path: Path) -> None:
        registry = PackagerRegistry()
        registry.register("jsonl", FakePackager("jsonl"))
        contract = PathContract(base_dir=tmp_path / "exports")
        orchestrator = ExportOrchestrator(
            packager_registry=registry,
            path_contract=contract,
        )
        request = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[_make_record()],
            labels={},
        )
        result = orchestrator.export(request)
        assert result.success
        assert result.determinism is not None
        assert len(result.determinism.content_hash) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# EX-014: Conflict resolution (via orchestrator)
# ---------------------------------------------------------------------------


class TestExportConflictResolution:
    def test_conflict_on_second_write_without_resolution(self, tmp_path: Path) -> None:
        registry = PackagerRegistry()
        registry.register("jsonl", FakePackager("jsonl"))
        contract = PathContract(base_dir=tmp_path / "exports")
        orchestrator = ExportOrchestrator(
            packager_registry=registry,
            path_contract=contract,
        )

        r1 = _make_record("first")
        request1 = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[r1],
            labels={},
        )
        result1 = orchestrator.export(request1)
        assert result1.success

        # Second write with different data, no resolution
        r2 = _make_record("second")
        request2 = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[r2],
            labels={},
        )
        result2 = orchestrator.export(request2)
        assert result2.success is False
        assert "conflict" in (result2.error or "").lower()

    def test_force_resolution_overwrites(self, tmp_path: Path) -> None:
        registry = PackagerRegistry()
        registry.register("jsonl", FakePackager("jsonl"))
        contract = PathContract(base_dir=tmp_path / "exports")
        orchestrator = ExportOrchestrator(
            packager_registry=registry,
            path_contract=contract,
        )

        r1 = _make_record("first")
        request1 = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[r1],
            labels={},
        )
        orchestrator.export(request1)

        r2 = _make_record("second")
        request2 = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[r2],
            labels={},
            conflict_resolution=ConflictResolution.force("Intentional overwrite"),
        )
        result2 = orchestrator.export(request2)
        assert result2.success is True

    def test_identical_content_no_conflict(self, tmp_path: Path) -> None:
        registry = PackagerRegistry()
        registry.register("jsonl", FakePackager("jsonl"))
        contract = PathContract(base_dir=tmp_path / "exports")
        orchestrator = ExportOrchestrator(
            packager_registry=registry,
            path_contract=contract,
        )

        rid = UUID("00000000-0000-0000-0000-000000000099")
        r1 = _make_record("same", rid)
        request = ExportRequest(
            project="p",
            dataset="d",
            format="jsonl",
            records=[r1],
            labels={},
        )
        # Write twice with identical data
        result1 = orchestrator.export(request)
        assert result1.success
        result2 = orchestrator.export(request)
        # Content hash is the same, so no conflict
        assert result2.success is True
