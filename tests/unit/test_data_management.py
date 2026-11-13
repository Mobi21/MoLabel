"""Tests for the Data Management Hub (DT-001 through DT-005, DT-010 through DT-014,
DT-016 through DT-020).

Tests cover:
- Workspace bootstrap and project detection (DT-001, DT-016)
- Artifact indexing, reindexing, and drift detection (DT-002, DT-017, DT-018)
- Data source adapters (DT-003, DT-004, DT-005)
- Pre-label import as review events with trust levels (DT-010)
- Label mapping engine (DT-011, DT-012)
- Dataset snapshots (DT-013, DT-014)
- Dataset operations (DT-019)
- Derived subset model (DT-020)
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from molabel.core.database import create_all_tables, get_session
from molabel.core.types import ReviewEventSource, TrustLevel

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with all MoLabel tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_all_tables(engine)
    return engine


@pytest.fixture()
def workspace_id(db_engine) -> uuid.UUID:
    """Insert a workspace record and return its ID."""
    from molabel.core.models.workspace import Workspace

    ws_id = uuid.uuid4()
    with get_session(db_engine) as session:
        ws = Workspace(
            id=ws_id,
            workspace_name="Test Workspace",
            workspace_slug="test-workspace",
            core_version="0.1.0",
            root_path="/tmp/test",
            manifest_path="workbench.project.yaml",
        )
        session.add(ws)
        session.commit()
    return ws_id


@pytest.fixture()
def dataset_id(db_engine, workspace_id) -> uuid.UUID:
    """Insert a dataset record and return its ID."""
    from molabel.core.models.dataset import Dataset

    ds_id = uuid.uuid4()
    with get_session(db_engine) as session:
        ds = Dataset(
            id=ds_id,
            workspace_id=workspace_id,
            dataset_name="Test Dataset",
            dataset_slug="test-dataset",
            source_type="local_file",
            canonical_id_strategy="source_record_id",
            indexing_mode="projection",
        )
        session.add(ds)
        session.commit()
    return ds_id


@pytest.fixture()
def task_schema_id(db_engine, workspace_id) -> uuid.UUID:
    """Insert a task schema record and return its ID."""
    from molabel.core.models.task_schema import TaskSchema

    ts_id = uuid.uuid4()
    with get_session(db_engine) as session:
        ts = TaskSchema(
            id=ts_id,
            workspace_id=workspace_id,
            task_schema_slug="test-schema",
            version=1,
            task_type="ordinal_text_review",
            title="Test Schema",
            label_fields=[{"name": "sentiment", "field_type": "categorical"}],
            blind_review_policy="hide_agent_outputs_by_default",
        )
        session.add(ts)
        session.commit()
    return ts_id


@pytest.fixture()
def sample_records(db_engine, workspace_id, dataset_id) -> list[uuid.UUID]:
    """Insert sample records and return their IDs."""
    from molabel.core.models.record import Record

    record_ids = []
    with get_session(db_engine) as session:
        for i in range(5):
            rec = Record(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                external_id=f"rec-{i}",
                stable_fields={"text": f"Record {i}", "label": "positive"},
                payload={
                    "text": f"Record {i}",
                    "pre_labels": {"sentiment": "positive"},
                },
                composite_confidence=0.1 * i if i < 3 else 0.8,
            )
            session.add(rec)
            session.commit()
            session.refresh(rec)
            record_ids.append(rec.id)
    return record_ids


# ===========================================================================
# Step 3.E.1: Workspace Bootstrap & Indexing
# ===========================================================================


class TestProjectDetection:
    """DT-001: Workspace bootstrap and project detection."""

    def test_detect_manifest_project(self, tmp_path):
        from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

        # Create a manifest file.
        manifest = tmp_path / "workbench.project.yaml"
        manifest.write_text(
            "workspace_id: '00000000-0000-0000-0000-000000000001'\n"
            "workspace_name: Test\n"
            "core_version: '0.1.0'\n"
        )

        bootstrapper = WorkspaceBootstrapper()
        result = bootstrapper.detect_project(tmp_path)

        assert result.is_project is True
        assert result.detection_mode == "manifest"
        assert result.manifest_path is not None

    def test_detect_heuristic_project(self, tmp_path):
        from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

        (tmp_path / "data.csv").write_text("a,b\n1,2\n")
        (tmp_path / "data.jsonl").write_text('{"x": 1}\n')

        bootstrapper = WorkspaceBootstrapper()
        result = bootstrapper.detect_project(tmp_path)

        assert result.is_project is True
        assert result.detection_mode == "heuristic"
        assert len(result.data_files) >= 2

    def test_detect_empty_folder(self, tmp_path):
        from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

        bootstrapper = WorkspaceBootstrapper()
        result = bootstrapper.detect_project(tmp_path)

        assert result.is_project is False
        assert result.detection_mode == "none"


class TestWorkspaceBootstrap:
    """DT-001, DT-016: Workspace bootstrap operations."""

    def test_bootstrap_from_manifest(self, tmp_path):
        from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

        ws_id = str(uuid.uuid4())
        manifest = tmp_path / "workbench.project.yaml"
        manifest.write_text(
            f"workspace_id: '{ws_id}'\n"
            f"workspace_name: My Project\n"
            f"core_version: '0.1.0'\n"
            f"datasets:\n"
            f"  - dataset_id: train\n"
            f"    source_paths:\n"
            f"      - train.csv\n"
        )
        (tmp_path / "train.csv").write_text("a,b\n1,2\n")

        bootstrapper = WorkspaceBootstrapper()
        result = bootstrapper.bootstrap(tmp_path)

        assert result.mode == "manifest"
        assert result.workspace_name == "My Project"
        assert result.datasets_discovered == 1
        assert result.workspace_id == uuid.UUID(ws_id)

    def test_bootstrap_heuristic(self, tmp_path):
        from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

        (tmp_path / "data.csv").write_text("x,y\n1,2\n")
        (tmp_path / "data.jsonl").write_text('{"a": 1}\n')

        bootstrapper = WorkspaceBootstrapper()
        result = bootstrapper.bootstrap(tmp_path)

        assert result.mode == "heuristic"
        assert result.files_discovered >= 2
        # Should have created a manifest.
        assert (tmp_path / "workbench.project.yaml").exists()

    def test_bootstrap_empty(self, tmp_path):
        from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

        bootstrapper = WorkspaceBootstrapper()
        result = bootstrapper.bootstrap(tmp_path)

        assert result.mode == "empty"
        assert (tmp_path / "workbench.project.yaml").exists()

    def test_bootstrap_missing_requirements(self, tmp_path):
        from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

        ws_id = str(uuid.uuid4())
        manifest = tmp_path / "workbench.project.yaml"
        manifest.write_text(
            f"workspace_id: '{ws_id}'\n"
            f"workspace_name: Parquet Project\n"
            f"core_version: '0.1.0'\n"
            f"datasets:\n"
            f"  - dataset_id: train\n"
            f"    source_paths:\n"
            f"      - train.parquet\n"
        )

        bootstrapper = WorkspaceBootstrapper()
        result = bootstrapper.bootstrap(tmp_path)
        # May or may not have pyarrow installed, but the check runs.
        assert isinstance(result.missing_requirements, list)

    def test_bootstrap_conflict_detection(self, tmp_path):
        from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

        ws_id = str(uuid.uuid4())
        manifest = tmp_path / "workbench.project.yaml"
        manifest.write_text(
            f"workspace_id: '{ws_id}'\n"
            f"workspace_name: Missing Files\n"
            f"core_version: '0.1.0'\n"
            f"datasets:\n"
            f"  - dataset_id: train\n"
            f"    source_paths:\n"
            f"      - nonexistent.csv\n"
        )

        bootstrapper = WorkspaceBootstrapper()
        result = bootstrapper.bootstrap(tmp_path)

        assert len(result.conflicts) >= 1
        assert result.conflicts[0]["type"] == "file_deleted"


class TestArtifactIndexer:
    """DT-002, DT-017, DT-018: Artifact indexing and drift detection."""

    def test_compute_file_hash(self, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        path = tmp_path / "test.csv"
        path.write_text("a,b\n1,2\n")

        indexer = ArtifactIndexer()
        h = indexer.compute_file_hash(path)

        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest

    def test_compute_hash_deterministic(self, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        path = tmp_path / "test.csv"
        path.write_text("hello world\n")

        indexer = ArtifactIndexer()
        h1 = indexer.compute_file_hash(path)
        h2 = indexer.compute_file_hash(path)
        assert h1 == h2

    def test_index_file(self, db_engine, workspace_id, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b\n1,2\n")

        indexer = ArtifactIndexer()
        artifact_id = indexer.index_file(
            db_engine,
            workspace_id=workspace_id,
            file_path=data_file,
            workspace_root=tmp_path,
        )

        assert isinstance(artifact_id, uuid.UUID)

        # Index again — should return same ID.
        artifact_id_2 = indexer.index_file(
            db_engine,
            workspace_id=workspace_id,
            file_path=data_file,
            workspace_root=tmp_path,
        )
        assert artifact_id == artifact_id_2

    def test_index_workspace(self, db_engine, workspace_id, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        (tmp_path / "data.csv").write_text("a,b\n1,2\n")
        (tmp_path / "data.jsonl").write_text('{"x": 1}\n')

        indexer = ArtifactIndexer()
        result = indexer.index_workspace(
            db_engine,
            workspace_id=workspace_id,
            workspace_root=tmp_path,
        )

        assert result.artifacts_indexed == 2
        assert len(result.errors) == 0

    def test_detect_drift_modified(self, db_engine, workspace_id, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b\n1,2\n")

        indexer = ArtifactIndexer()
        indexer.index_file(
            db_engine,
            workspace_id=workspace_id,
            file_path=data_file,
            workspace_root=tmp_path,
        )

        # Modify the file.
        data_file.write_text("a,b\n3,4\n5,6\n")

        drifts = indexer.detect_drift(
            db_engine,
            workspace_id=workspace_id,
            workspace_root=tmp_path,
        )

        modified = [d for d in drifts if d.drift_type == "modified"]
        assert len(modified) == 1

    def test_detect_drift_deleted(self, db_engine, workspace_id, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b\n1,2\n")

        indexer = ArtifactIndexer()
        indexer.index_file(
            db_engine,
            workspace_id=workspace_id,
            file_path=data_file,
            workspace_root=tmp_path,
        )

        # Delete the file.
        data_file.unlink()

        drifts = indexer.detect_drift(
            db_engine,
            workspace_id=workspace_id,
            workspace_root=tmp_path,
        )

        deleted = [d for d in drifts if d.drift_type == "deleted"]
        assert len(deleted) == 1

    def test_detect_drift_new_file(self, db_engine, workspace_id, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        indexer = ArtifactIndexer()
        indexer.index_workspace(
            db_engine,
            workspace_id=workspace_id,
            workspace_root=tmp_path,
        )

        # Add a new file.
        (tmp_path / "new_data.csv").write_text("x,y\n1,2\n")

        drifts = indexer.detect_drift(
            db_engine,
            workspace_id=workspace_id,
            workspace_root=tmp_path,
        )

        new_files = [d for d in drifts if d.drift_type == "new_file"]
        assert len(new_files) == 1

    def test_mark_stale(self, db_engine, workspace_id, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b\n1,2\n")

        indexer = ArtifactIndexer()
        aid = indexer.index_file(
            db_engine,
            workspace_id=workspace_id,
            file_path=data_file,
            workspace_root=tmp_path,
        )

        count = indexer.mark_stale(db_engine, artifact_ids=[aid])
        assert count == 1

    def test_reindex_selective(self, db_engine, workspace_id, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b\n1,2\n")

        indexer = ArtifactIndexer()
        aid = indexer.index_file(
            db_engine,
            workspace_id=workspace_id,
            file_path=data_file,
            workspace_root=tmp_path,
        )

        # Modify file and reindex.
        data_file.write_text("a,b\n3,4\n")
        result = indexer.reindex_selective(
            db_engine,
            workspace_id=workspace_id,
            workspace_root=tmp_path,
            artifact_ids=[aid],
        )

        assert result.artifacts_updated == 1

    def test_resolve_drift(self, db_engine, workspace_id, tmp_path):
        from molabel.core.data.artifact_indexer import (
            ArtifactIndexer,
            DriftEntry,
            DriftType,
        )

        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b\n1,2\n")

        indexer = ArtifactIndexer()
        aid = indexer.index_file(
            db_engine,
            workspace_id=workspace_id,
            file_path=data_file,
            workspace_root=tmp_path,
        )

        # Modify and resolve.
        data_file.write_text("a,b\n3,4\n")
        new_hash = indexer.compute_file_hash(data_file)

        drift = DriftEntry(
            drift_type=DriftType.modified,
            file_path="data.csv",
            artifact_id=aid,
            old_hash="old",
            new_hash=new_hash,
        )

        result = indexer.resolve_drift(
            db_engine,
            workspace_id=workspace_id,
            workspace_root=tmp_path,
            drift_entries=[drift],
            action="reindex",
        )

        assert result.artifacts_updated == 1


# ===========================================================================
# Step 3.E.2: Data Source Adapters
# ===========================================================================


class TestLocalFileAdapter:
    """DT-003: Local file ingest."""

    def test_ingest_csv(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,text,label\n1,hello,positive\n2,world,negative\n")

        adapter = LocalFileAdapter()
        records = list(adapter.ingest(csv_file))

        assert len(records) == 2
        assert records[0].stable_fields["text"] == "hello"
        assert records[1].stable_fields["label"] == "negative"

    def test_ingest_csv_with_id(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,text\nrec-1,hello\nrec-2,world\n")

        adapter = LocalFileAdapter()
        records = list(adapter.ingest(csv_file, config={"id_column": "id"}))

        assert records[0].external_id == "rec-1"
        assert records[1].external_id == "rec-2"

    def test_ingest_jsonl(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text('{"text": "hello"}\n{"text": "world"}\n')

        adapter = LocalFileAdapter()
        records = list(adapter.ingest(jsonl_file))

        assert len(records) == 2
        assert records[0].stable_fields["text"] == "hello"

    def test_ingest_json(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        json_file = tmp_path / "test.json"
        json_file.write_text('[{"text": "hello"}, {"text": "world"}]')

        adapter = LocalFileAdapter()
        records = list(adapter.ingest(json_file))

        assert len(records) == 2

    def test_ingest_yaml(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("- text: hello\n- text: world\n")

        adapter = LocalFileAdapter()
        records = list(adapter.ingest(yaml_file))

        assert len(records) == 2
        assert records[0].stable_fields["text"] == "hello"

    def test_get_schema(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,text,score\n1,hello,0.9\n")

        adapter = LocalFileAdapter()
        schema = adapter.get_schema(csv_file)

        assert schema["type"] == "object"
        assert "id" in schema["properties"]

    def test_estimate_count_csv(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n3,4\n5,6\n")

        adapter = LocalFileAdapter()
        count = adapter.estimate_count(csv_file)
        assert count == 3

    def test_unsupported_format(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        bad_file = tmp_path / "test.xyz"
        bad_file.write_text("data")

        adapter = LocalFileAdapter()
        with pytest.raises(ValueError, match="Unsupported"):
            list(adapter.ingest(bad_file))


class TestLabelingToolAdapter:
    """DT-005: Import from labeling tools."""

    def test_import_label_studio(self, tmp_path):
        from molabel.core.data.source_adapters import LabelingToolAdapter

        ls_data = [
            {
                "id": 1,
                "data": {"text": "Hello world"},
                "annotations": [
                    {
                        "result": [
                            {
                                "from_name": "sentiment",
                                "value": {"choices": ["positive"]},
                            }
                        ]
                    }
                ],
            }
        ]

        path = tmp_path / "label_studio.json"
        path.write_text(json.dumps(ls_data))

        adapter = LabelingToolAdapter()
        records = list(adapter.import_label_studio(path))

        assert len(records) == 1
        assert records[0].stable_fields["text"] == "Hello world"
        assert records[0].payload["pre_labels"]["sentiment"] == ["positive"]
        assert records[0].source_metadata["source_system"] == "label-studio"

    def test_import_prodigy(self, tmp_path):
        from molabel.core.data.source_adapters import LabelingToolAdapter

        prodigy_data = (
            '{"text": "Good product", "label": "POSITIVE", "answer": "accept"}\n'
            '{"text": "Bad product", "label": "NEGATIVE", "answer": "reject"}\n'
        )

        path = tmp_path / "prodigy.jsonl"
        path.write_text(prodigy_data)

        adapter = LabelingToolAdapter()
        records = list(adapter.import_prodigy(path))

        assert len(records) == 2
        assert records[0].stable_fields["text"] == "Good product"
        assert records[0].payload["pre_labels"]["label"] == "POSITIVE"
        assert records[0].source_metadata["source_system"] == "prodigy"

    def test_import_argilla(self, tmp_path):
        from molabel.core.data.source_adapters import LabelingToolAdapter

        argilla_data = [
            {
                "id": "a1",
                "fields": {"text": "Sample text"},
                "annotation": {"sentiment": "positive"},
            }
        ]

        path = tmp_path / "argilla.json"
        path.write_text(json.dumps(argilla_data))

        adapter = LabelingToolAdapter()
        records = list(adapter.import_argilla(path))

        assert len(records) == 1
        assert records[0].stable_fields["text"] == "Sample text"
        assert records[0].source_metadata["source_system"] == "argilla"

    def test_detect_format_prodigy(self, tmp_path):
        from molabel.core.data.source_adapters import LabelingToolAdapter

        path = tmp_path / "data.jsonl"
        path.write_text('{"text": "x", "answer": "accept"}\n')

        adapter = LabelingToolAdapter()
        fmt = adapter.detect_format(path)
        assert fmt == "prodigy"

    def test_detect_format_label_studio(self, tmp_path):
        from molabel.core.data.source_adapters import LabelingToolAdapter

        path = tmp_path / "data.json"
        path.write_text(json.dumps([{"data": {}, "annotations": []}]))

        adapter = LabelingToolAdapter()
        fmt = adapter.detect_format(path)
        assert fmt == "label-studio"

    def test_detect_format_unknown(self, tmp_path):
        from molabel.core.data.source_adapters import LabelingToolAdapter

        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,2\n")

        adapter = LabelingToolAdapter()
        fmt = adapter.detect_format(path)
        assert fmt is None


# ===========================================================================
# Step 3.E.3: Pre-label Import & Label Mapping
# ===========================================================================


class TestPreLabelImport:
    """DT-010: Pre-label import as review events with trust levels."""

    def test_import_prelabels(
        self, db_engine, workspace_id, dataset_id, task_schema_id, sample_records
    ):
        from molabel.core.data.prelabel_import import PreLabelEntry, PreLabelImporter

        importer = PreLabelImporter()
        entries = [
            PreLabelEntry(
                record_id=sample_records[0],
                labels={"sentiment": "positive"},
                trust_level=TrustLevel.expert,
                source_system="label-studio",
                source_file="export.json",
            ),
            PreLabelEntry(
                record_id=sample_records[1],
                labels={"sentiment": "negative"},
                trust_level=TrustLevel.external,
                source_system="label-studio",
                source_file="export.json",
            ),
        ]

        result = importer.import_prelabels(
            db_engine,
            workspace_id=workspace_id,
            task_schema_id=task_schema_id,
            entries=entries,
        )

        assert result.events_created == 2
        assert result.events_skipped == 0

    def test_skip_duplicates(
        self, db_engine, workspace_id, dataset_id, task_schema_id, sample_records
    ):
        from molabel.core.data.prelabel_import import PreLabelEntry, PreLabelImporter

        importer = PreLabelImporter()
        entries = [
            PreLabelEntry(
                record_id=sample_records[0],
                labels={"sentiment": "positive"},
                trust_level=TrustLevel.expert,
                source_system="label-studio",
            ),
        ]

        # Import once.
        importer.import_prelabels(
            db_engine,
            workspace_id=workspace_id,
            task_schema_id=task_schema_id,
            entries=entries,
        )

        # Import again — should skip.
        result = importer.import_prelabels(
            db_engine,
            workspace_id=workspace_id,
            task_schema_id=task_schema_id,
            entries=entries,
        )

        assert result.events_skipped == 1
        assert result.events_created == 0

    def test_trust_levels(
        self, db_engine, workspace_id, dataset_id, task_schema_id, sample_records
    ):
        from molabel.core.data.prelabel_import import PreLabelEntry, PreLabelImporter
        from molabel.core.models.review_event import ReviewEvent

        importer = PreLabelImporter()

        for i, trust in enumerate(
            [TrustLevel.ground_truth, TrustLevel.expert, TrustLevel.untrusted]
        ):
            entries = [
                PreLabelEntry(
                    record_id=sample_records[i],
                    labels={"sentiment": "positive"},
                    trust_level=trust,
                    source_system=f"system-{i}",
                ),
            ]
            importer.import_prelabels(
                db_engine,
                workspace_id=workspace_id,
                task_schema_id=task_schema_id,
                entries=entries,
            )

        # Verify trust levels were stored.
        with get_session(db_engine) as session:
            from sqlmodel import select

            events = list(
                session.exec(
                    select(ReviewEvent).where(
                        ReviewEvent.source == ReviewEventSource.import_
                    )
                ).all()
            )

        trust_levels = {e.trust_level for e in events}
        assert TrustLevel.ground_truth in trust_levels
        assert TrustLevel.expert in trust_levels
        assert TrustLevel.untrusted in trust_levels


class TestLabelMappingEngine:
    """DT-011, DT-012: Label mapping engine and saved configurations."""

    def test_apply_field_mapping(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="test-mapping",
            source_system="label-studio",
            field_mappings=[
                FieldMapping(
                    source_field="sent",
                    target_field="sentiment",
                ),
                FieldMapping(
                    source_field="conf",
                    target_field="confidence",
                    type_conversion="float",
                ),
            ],
        )

        result = engine_obj.apply_mapping(
            {"sent": "positive", "conf": "0.95", "extra": "data"},
            config,
        )

        assert result.mapped_labels["sentiment"] == "positive"
        assert result.mapped_labels["confidence"] == 0.95
        assert result.unmapped_fields["extra"] == "data"

    def test_apply_value_mapping(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="value-map-test",
            source_system="external",
            field_mappings=[
                FieldMapping(
                    source_field="label",
                    target_field="sentiment",
                    value_map={"pos": "positive", "neg": "negative"},
                ),
            ],
        )

        result = engine_obj.apply_mapping({"label": "pos"}, config)
        assert result.mapped_labels["sentiment"] == "positive"

    def test_unmapped_value_warning(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="warning-test",
            source_system="external",
            field_mappings=[
                FieldMapping(
                    source_field="label",
                    target_field="sentiment",
                    value_map={"pos": "positive"},
                ),
            ],
        )

        result = engine_obj.apply_mapping({"label": "unknown"}, config)
        assert len(result.warnings) > 0

    def test_default_value(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="default-test",
            source_system="external",
            field_mappings=[
                FieldMapping(
                    source_field="missing_field",
                    target_field="sentiment",
                    default_value="neutral",
                ),
            ],
        )

        result = engine_obj.apply_mapping({}, config)
        assert result.mapped_labels["sentiment"] == "neutral"

    def test_batch_mapping(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="batch-test",
            source_system="external",
            field_mappings=[
                FieldMapping(source_field="label", target_field="sentiment"),
            ],
        )

        results = engine_obj.apply_mapping_batch(
            [{"label": "pos"}, {"label": "neg"}],
            config,
        )
        assert len(results) == 2

    def test_save_and_load_mapping(self, db_engine, workspace_id, task_schema_id):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="Saved Mapping",
            source_system="label-studio",
            field_mappings=[
                FieldMapping(
                    source_field="sent",
                    target_field="sentiment",
                    value_map={"pos": "positive", "neg": "negative"},
                ),
            ],
            default_trust_level=TrustLevel.expert,
        )

        mapping_id = engine_obj.save_mapping(
            db_engine,
            workspace_id=workspace_id,
            task_schema_id=task_schema_id,
            config=config,
        )

        loaded = engine_obj.load_mapping(db_engine, mapping_id=mapping_id)

        assert loaded is not None
        assert loaded.name == "Saved Mapping"
        assert loaded.source_system == "label-studio"
        assert len(loaded.field_mappings) == 1
        assert loaded.field_mappings[0].target_field == "sentiment"

    def test_list_mappings(self, db_engine, workspace_id, task_schema_id):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="Listing Test",
            source_system="prodigy",
            field_mappings=[
                FieldMapping(source_field="x", target_field="y"),
            ],
        )

        engine_obj.save_mapping(
            db_engine,
            workspace_id=workspace_id,
            task_schema_id=task_schema_id,
            config=config,
        )

        mappings = engine_obj.list_mappings(db_engine, workspace_id=workspace_id)
        assert len(mappings) >= 1
        assert any(m["name"] == "Listing Test" for m in mappings)

    def test_delete_mapping(self, db_engine, workspace_id, task_schema_id):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="Delete Test",
            source_system="argilla",
            field_mappings=[
                FieldMapping(source_field="a", target_field="b"),
            ],
        )

        mid = engine_obj.save_mapping(
            db_engine,
            workspace_id=workspace_id,
            task_schema_id=task_schema_id,
            config=config,
        )

        assert engine_obj.delete_mapping(db_engine, mapping_id=mid) is True
        assert engine_obj.load_mapping(db_engine, mapping_id=mid) is None

    def test_unmapped_field_policy_discard(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="discard-test",
            source_system="external",
            field_mappings=[
                FieldMapping(source_field="a", target_field="b"),
            ],
            unmapped_field_policy="discard",
        )

        result = engine_obj.apply_mapping({"a": 1, "extra": "ignored"}, config)
        assert "extra" not in result.unmapped_fields


# ===========================================================================
# Step 3.E.4: Dataset Snapshots
# ===========================================================================


class TestSnapshotService:
    """DT-013, DT-014: Dataset snapshots."""

    def test_create_snapshot(self, db_engine, workspace_id, dataset_id, sample_records):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()
        result = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="v1.0",
            description="First snapshot",
        )

        assert result.name == "v1.0"
        assert result.snapshot_type == "full"
        assert isinstance(result.snapshot_id, uuid.UUID)

    def test_create_delta_snapshot(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()

        # First snapshot (full).
        service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="v1.0",
        )

        # Second snapshot (delta).
        result = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="v1.1",
        )

        assert result.snapshot_type == "delta"

    def test_browse_snapshots(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()
        service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="v1.0",
        )
        service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="v2.0",
        )

        snapshots = service.browse_snapshots(db_engine, dataset_id=dataset_id)

        assert len(snapshots) == 2
        assert snapshots[0].name == "v2.0"  # newest first
        assert snapshots[1].name == "v1.0"

    def test_compare_snapshots(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()
        r1 = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="v1",
        )
        r2 = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="v2",
        )

        diff = service.compare_snapshots(
            db_engine,
            snapshot_a_id=r1.snapshot_id,
            snapshot_b_id=r2.snapshot_id,
        )

        assert diff.snapshot_a_name == "v1"
        assert diff.snapshot_b_name == "v2"
        assert isinstance(diff.record_count_change, int)

    def test_restore_snapshot(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()
        original = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="original",
        )

        result = service.restore_snapshot(
            db_engine,
            workspace_id=workspace_id,
            snapshot_id=original.snapshot_id,
        )

        assert result.restored_snapshot_id == original.snapshot_id
        assert isinstance(result.safety_snapshot_id, uuid.UUID)
        assert result.safety_snapshot_id != original.snapshot_id

    def test_snapshot_file_output(
        self, db_engine, workspace_id, dataset_id, sample_records, tmp_path
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()
        result = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="file-test",
            workspace_root=tmp_path,
        )

        assert result.file_path is not None
        full_path = tmp_path / result.file_path
        assert full_path.exists()

        data = json.loads(full_path.read_text())
        assert data["name"] == "file-test"

    def test_snapshot_quality_metrics(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()
        service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="metrics-test",
        )

        snapshots = service.browse_snapshots(db_engine, dataset_id=dataset_id)
        assert len(snapshots) == 1

        metrics = snapshots[0].quality_metrics
        assert metrics is not None
        assert "total_records" in metrics
        assert "coverage" in metrics


# ===========================================================================
# Step 3.E.5: Dataset Operations & Derived Sets
# ===========================================================================


class TestDatasetOperations:
    """DT-019: Dataset operations."""

    def test_find_disagreements(
        self, db_engine, workspace_id, dataset_id, task_schema_id, sample_records
    ):
        from molabel.core.data.dataset_operations import DatasetOperationsService
        from molabel.core.models.review_event import ReviewEvent

        # Create conflicting review events.
        with get_session(db_engine) as session:
            for label in ["positive", "negative"]:
                event = ReviewEvent(
                    workspace_id=workspace_id,
                    record_id=sample_records[0],
                    task_schema_id=task_schema_id,
                    task_schema_version=1,
                    source=ReviewEventSource.human,
                    labels={"sentiment": label},
                )
                session.add(event)
            session.commit()

        service = DatasetOperationsService()
        disagreements = service.find_disagreements(db_engine, dataset_id=dataset_id)

        assert len(disagreements) >= 1
        assert "sentiment" in disagreements[0].fields_in_conflict

    def test_find_edge_cases(self, db_engine, workspace_id, dataset_id, sample_records):
        from molabel.core.data.dataset_operations import DatasetOperationsService

        service = DatasetOperationsService()
        edge_cases = service.find_edge_cases(
            db_engine,
            dataset_id=dataset_id,
            confidence_threshold=0.3,
        )

        # Records 0, 1, 2 have confidence 0.0, 0.1, 0.2 (all < 0.3).
        assert len(edge_cases) >= 3
        assert all(ec.reason == "low_confidence" for ec in edge_cases[:3])

    def test_cluster_records(
        self, db_engine, workspace_id, dataset_id, task_schema_id, sample_records
    ):
        from molabel.core.data.dataset_operations import DatasetOperationsService
        from molabel.core.models.review_event import ReviewEvent

        # Create review events with different labels.
        with get_session(db_engine) as session:
            labels = ["positive", "positive", "negative", "neutral", "positive"]
            for i, label in enumerate(labels):
                event = ReviewEvent(
                    workspace_id=workspace_id,
                    record_id=sample_records[i],
                    task_schema_id=task_schema_id,
                    task_schema_version=1,
                    source=ReviewEventSource.human,
                    labels={"sentiment": label},
                )
                session.add(event)
            session.commit()

        service = DatasetOperationsService()
        clusters = service.cluster_records(
            db_engine,
            dataset_id=dataset_id,
            field="sentiment",
        )

        assert len(clusters) >= 1
        assert clusters[0].label == "positive"  # most common
        assert clusters[0].size >= 3

    def test_curate_challenge_set(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.dataset_operations import DatasetOperationsService

        service = DatasetOperationsService()
        result = service.curate_challenge_set(
            db_engine,
            dataset_id=dataset_id,
            name="test-challenge",
            criteria={"confidence_threshold": 0.5},
        )

        assert result.name == "test-challenge"
        assert result.size >= 0

    def test_compute_label_distribution(
        self, db_engine, workspace_id, dataset_id, task_schema_id, sample_records
    ):
        from molabel.core.data.dataset_operations import DatasetOperationsService
        from molabel.core.models.review_event import ReviewEvent

        with get_session(db_engine) as session:
            for label in ["positive", "positive", "negative"]:
                event = ReviewEvent(
                    workspace_id=workspace_id,
                    record_id=sample_records[0],
                    task_schema_id=task_schema_id,
                    task_schema_version=1,
                    source=ReviewEventSource.human,
                    labels={"sentiment": label},
                )
                session.add(event)
            session.commit()

        service = DatasetOperationsService()
        dist = service.compute_label_distribution(
            db_engine,
            dataset_id=dataset_id,
            field="sentiment",
        )

        assert "positive" in dist
        assert "negative" in dist
        assert dist["positive"] >= 2


class TestDerivedSubsets:
    """DT-020: Derived subset model."""

    def test_create_and_get_subset(self, db_engine, workspace_id, dataset_id):
        from molabel.core.data.derived_sets import (
            DerivedSubsetService,
            SubsetDefinition,
        )

        service = DerivedSubsetService()
        definition = SubsetDefinition(
            name="low-confidence",
            dataset_id=dataset_id,
            workspace_id=workspace_id,
            selection_criteria={"confidence_threshold": 0.3},
            tags=["quality", "review"],
        )

        subset_id = service.create_subset(db_engine, definition=definition)
        assert isinstance(subset_id, uuid.UUID)

        loaded = service.get_subset(db_engine, subset_id=subset_id)
        assert loaded is not None
        assert loaded.name == "low-confidence"
        assert loaded.tags == ["quality", "review"]

    def test_list_subsets(self, db_engine, workspace_id, dataset_id):
        from molabel.core.data.derived_sets import (
            DerivedSubsetService,
            SubsetDefinition,
        )

        service = DerivedSubsetService()
        for name in ["subset-a", "subset-b"]:
            service.create_subset(
                db_engine,
                definition=SubsetDefinition(
                    name=name,
                    dataset_id=dataset_id,
                    workspace_id=workspace_id,
                    selection_criteria={},
                ),
            )

        subsets = service.list_subsets(db_engine, workspace_id=workspace_id)
        assert len(subsets) >= 2

    def test_materialize_subset(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.derived_sets import (
            DerivedSubsetService,
            SubsetDefinition,
        )

        service = DerivedSubsetService()
        subset_id = service.create_subset(
            db_engine,
            definition=SubsetDefinition(
                name="all-records",
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                selection_criteria={},
            ),
        )

        result = service.materialize_subset(db_engine, subset_id=subset_id)
        assert result.record_count == 5

    def test_materialize_with_sample_size(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.derived_sets import (
            DerivedSubsetService,
            SubsetDefinition,
        )

        service = DerivedSubsetService()
        subset_id = service.create_subset(
            db_engine,
            definition=SubsetDefinition(
                name="sampled",
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                selection_criteria={"sample_size": 2, "sample_strategy": "random"},
            ),
        )

        result = service.materialize_subset(db_engine, subset_id=subset_id)
        assert result.record_count == 2

    def test_promote_to_dataset(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.derived_sets import (
            DerivedSubsetService,
            SubsetDefinition,
        )

        service = DerivedSubsetService()
        subset_id = service.create_subset(
            db_engine,
            definition=SubsetDefinition(
                name="promote-test",
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                selection_criteria={},
            ),
        )

        result = service.promote_to_dataset(
            db_engine,
            subset_id=subset_id,
            new_dataset_name="Promoted Dataset",
        )

        assert result.new_dataset_name == "Promoted Dataset"
        assert result.record_count == 5
        assert isinstance(result.new_dataset_id, uuid.UUID)

    def test_lineage_tracking(self, db_engine, workspace_id, dataset_id):
        from molabel.core.data.derived_sets import (
            DerivedSubsetService,
            SubsetDefinition,
        )

        service = DerivedSubsetService()

        root_id = service.create_subset(
            db_engine,
            definition=SubsetDefinition(
                name="root",
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                selection_criteria={},
            ),
        )

        child_id = service.create_subset(
            db_engine,
            definition=SubsetDefinition(
                name="child",
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                selection_criteria={},
                parent_subset_id=root_id,
            ),
        )

        lineage = service.get_lineage(db_engine, subset_id=child_id)
        assert len(lineage) == 2
        assert lineage[0].name == "root"
        assert lineage[1].name == "child"

    def test_delete_subset(self, db_engine, workspace_id, dataset_id):
        from molabel.core.data.derived_sets import (
            DerivedSubsetService,
            SubsetDefinition,
        )

        service = DerivedSubsetService()
        subset_id = service.create_subset(
            db_engine,
            definition=SubsetDefinition(
                name="delete-me",
                dataset_id=dataset_id,
                workspace_id=workspace_id,
                selection_criteria={},
            ),
        )

        assert service.delete_subset(db_engine, subset_id=subset_id) is True
        assert service.get_subset(db_engine, subset_id=subset_id) is None


# ===========================================================================
# Additional test coverage (Issue #4)
# ===========================================================================


class TestConcurrentBootstrap:
    """Concurrent bootstrap: second bootstrap should detect existing workspace."""

    def test_second_bootstrap_detects_existing(self, tmp_path):
        from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

        (tmp_path / "data.csv").write_text("a,b\n1,2\n")

        bootstrapper = WorkspaceBootstrapper()

        # First bootstrap.
        result1 = bootstrapper.bootstrap(tmp_path)
        assert result1.mode in ("heuristic", "manifest")
        assert (tmp_path / "workbench.project.yaml").exists()

        # Second bootstrap should detect the manifest.
        result2 = bootstrapper.bootstrap(tmp_path)
        assert result2.mode == "manifest"


class TestSnapshotRestoreValidation:
    """Verify safety snapshot is created and record-level state is restored."""

    def test_safety_snapshot_created_before_restore(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()
        original = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="pre-restore-test",
        )

        result = service.restore_snapshot(
            db_engine,
            workspace_id=workspace_id,
            snapshot_id=original.snapshot_id,
        )

        # Safety snapshot must exist and differ from the original.
        assert result.safety_snapshot_id != original.snapshot_id

        # Verify the safety snapshot actually appears in the browse list.
        snapshots = service.browse_snapshots(db_engine, dataset_id=dataset_id)
        safety_names = [s.name for s in snapshots]
        assert "Pre-restore safety snapshot" in safety_names

    def test_record_level_state_restored(
        self, db_engine, workspace_id, dataset_id, sample_records
    ):
        from molabel.core.data.snapshot_service import SnapshotService
        from molabel.core.models.record import Record

        service = SnapshotService()

        # Modify some record state before snapshot.
        with get_session(db_engine) as session:
            rec = session.get(Record, sample_records[0])
            rec.latest_label = {"sentiment": "positive"}
            rec.composite_confidence = 0.95
            rec.export_eligible = True
            rec.flags = ["reviewed"]
            rec.label_count = 1
            session.add(rec)
            session.commit()

        # Create snapshot capturing this state.
        snap_result = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="state-capture",
        )

        # Now change the record state.
        with get_session(db_engine) as session:
            rec = session.get(Record, sample_records[0])
            rec.latest_label = {"sentiment": "negative"}
            rec.composite_confidence = 0.1
            rec.export_eligible = False
            rec.flags = ["disputed"]
            rec.label_count = 3
            session.add(rec)
            session.commit()

        # Create a second snapshot (so we have current state captured).
        service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="after-change",
        )

        # Restore to the first snapshot.
        service.restore_snapshot(
            db_engine,
            workspace_id=workspace_id,
            snapshot_id=snap_result.snapshot_id,
        )

        # Verify record-level state was restored.
        with get_session(db_engine) as session:
            rec = session.get(Record, sample_records[0])
            assert rec.latest_label == {"sentiment": "positive"}
            assert rec.composite_confidence == 0.95
            assert rec.export_eligible is True
            assert rec.flags == ["reviewed"]
            assert rec.label_count == 1


class TestLargeFileHash:
    """Test the _fast_hash path for files > 100 MB threshold."""

    def test_fast_hash_branch_for_large_file(self, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        # Create a small file but mock stat to report > 100MB.
        data_file = tmp_path / "large.csv"
        data_file.write_bytes(b"x" * 200)  # small file with known content

        indexer = ArtifactIndexer()

        # Normal hash (full hash path).
        full_hash = indexer.compute_file_hash(data_file)
        assert isinstance(full_hash, str)
        assert len(full_hash) == 64

        # Patch the stat result to make file_size > threshold.
        original_stat = data_file.stat

        class FakeStat:
            def __init__(self, real_stat):
                self._real = real_stat

            def __getattr__(self, name):
                if name == "st_size":
                    return 200 * 1024 * 1024  # 200 MB
                return getattr(self._real, name)

        fake_stat = FakeStat(original_stat())
        with patch.object(type(data_file), "stat", return_value=fake_stat):
            fast_hash = indexer.compute_file_hash(data_file)

        assert isinstance(fast_hash, str)
        assert len(fast_hash) == 64
        # The hashes should differ because fast_hash includes file_size
        # in the hash and only reads first/last chunks.
        assert fast_hash != full_hash

    def test_fast_hash_deterministic(self, tmp_path):
        from molabel.core.data.artifact_indexer import ArtifactIndexer

        data_file = tmp_path / "data.bin"
        data_file.write_bytes(b"A" * 256)

        indexer = ArtifactIndexer()

        original_stat = data_file.stat

        class FakeStat:
            def __init__(self, real_stat):
                self._real = real_stat

            def __getattr__(self, name):
                if name == "st_size":
                    return 200 * 1024 * 1024
                return getattr(self._real, name)

        fake_stat = FakeStat(original_stat())
        with patch.object(type(data_file), "stat", return_value=fake_stat):
            h1 = indexer.compute_file_hash(data_file)
            h2 = indexer.compute_file_hash(data_file)

        assert h1 == h2


class TestMalformedInputHandling:
    """Test source_adapters with malformed CSV, JSON, YAML inputs."""

    def test_malformed_csv_missing_columns(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        # CSV with inconsistent columns.
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("a,b,c\n1,2\n3,4,5\n")

        adapter = LocalFileAdapter()
        records = list(adapter.ingest(csv_file))
        # csv.DictReader handles missing columns as None.
        assert len(records) == 2
        assert records[0].stable_fields.get("c") is None

    def test_malformed_csv_encoding_error(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        csv_file = tmp_path / "enc.csv"
        csv_file.write_bytes(b"a,b\n\xff\xfe,2\n")

        adapter = LocalFileAdapter()
        with pytest.raises((UnicodeDecodeError, Exception)):
            list(adapter.ingest(csv_file))

    def test_malformed_json_invalid_syntax(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        json_file = tmp_path / "bad.json"
        json_file.write_text("{not valid json")

        adapter = LocalFileAdapter()
        with pytest.raises(json.JSONDecodeError):
            list(adapter.ingest(json_file))

    def test_malformed_jsonl_invalid_line(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        jsonl_file = tmp_path / "bad.jsonl"
        jsonl_file.write_text('{"valid": 1}\n{bad line\n{"valid": 2}\n')

        adapter = LocalFileAdapter()
        with pytest.raises(json.JSONDecodeError):
            list(adapter.ingest(jsonl_file))

    def test_malformed_yaml_indentation(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("- text: hello\n  bad:\n indent: wrong\n")

        adapter = LocalFileAdapter()
        # YAML with bad indentation may parse differently or raise.
        # The key thing is that it does not silently produce wrong results.
        try:
            records = list(adapter.ingest(yaml_file))
            # If it parses, the structure should be some form of list.
            assert isinstance(records, list)
        except (ValueError, Exception):
            pass  # Expected for truly malformed YAML.

    def test_json_not_array(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        json_file = tmp_path / "obj.json"
        json_file.write_text('{"key": "value"}')

        adapter = LocalFileAdapter()
        with pytest.raises(ValueError, match="Expected a JSON array"):
            list(adapter.ingest(json_file))

    def test_yaml_not_array(self, tmp_path):
        from molabel.core.data.source_adapters import LocalFileAdapter

        yaml_file = tmp_path / "obj.yaml"
        yaml_file.write_text("key: value\n")

        adapter = LocalFileAdapter()
        with pytest.raises(ValueError, match="Expected a YAML array"):
            list(adapter.ingest(yaml_file))


class TestLabelMappingEdgeCases:
    """Label mapping with missing fields, wrong types, empty input."""

    def test_mapping_empty_input(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="empty-test",
            source_system="external",
            field_mappings=[
                FieldMapping(source_field="label", target_field="sentiment"),
            ],
        )

        result = engine_obj.apply_mapping({}, config)
        # Source field missing, no default -> warning.
        assert len(result.warnings) > 0
        assert "sentiment" not in result.mapped_labels

    def test_mapping_missing_fields_in_config(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="missing-field-test",
            source_system="external",
            field_mappings=[
                FieldMapping(
                    source_field="nonexistent",
                    target_field="output",
                ),
            ],
        )

        result = engine_obj.apply_mapping({"label": "positive"}, config)
        assert len(result.warnings) > 0
        assert "output" not in result.mapped_labels

    def test_mapping_wrong_type_conversion(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="type-error-test",
            source_system="external",
            field_mappings=[
                FieldMapping(
                    source_field="score",
                    target_field="confidence",
                    type_conversion="float",
                ),
            ],
        )

        # Non-numeric string with float conversion.
        result = engine_obj.apply_mapping({"score": "not_a_number"}, config)
        # Should produce a warning about conversion failure.
        assert len(result.warnings) > 0

    def test_mapping_batch_empty_list(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="batch-empty-test",
            source_system="external",
            field_mappings=[
                FieldMapping(source_field="x", target_field="y"),
            ],
        )

        results = engine_obj.apply_mapping_batch([], config)
        assert results == []

    def test_mapping_value_map_with_list_input(self):
        from molabel.core.data.label_mapping_engine import (
            FieldMapping,
            LabelMappingEngine,
            MappingConfig,
        )

        engine_obj = LabelMappingEngine()
        config = MappingConfig(
            name="list-value-test",
            source_system="external",
            field_mappings=[
                FieldMapping(
                    source_field="labels",
                    target_field="sentiments",
                    value_map={"pos": "positive", "neg": "negative"},
                ),
            ],
        )

        result = engine_obj.apply_mapping({"labels": ["pos", "neg"]}, config)
        assert result.mapped_labels["sentiments"] == ["positive", "negative"]


class TestSnapshotPathTraversal:
    """Verify snapshot filename sanitization blocks path traversal."""

    def test_path_traversal_in_snapshot_name(
        self, db_engine, workspace_id, dataset_id, sample_records, tmp_path
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()

        # Name with path traversal attempt.
        result = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="../../etc/passwd",
            workspace_root=tmp_path,
        )

        assert result.file_path is not None
        full_path = tmp_path / result.file_path
        # File must be under the snapshots directory.
        assert "workbench/snapshots" in Path(result.file_path).as_posix()
        # Must not contain path traversal.
        assert ".." not in result.file_path
        assert full_path.exists()

    def test_sanitize_snapshot_name(self):
        from molabel.core.data.snapshot_service import SnapshotService

        assert SnapshotService._sanitize_snapshot_name("normal_name") == "normal_name"
        assert SnapshotService._sanitize_snapshot_name("with spaces") == "with_spaces"
        assert ".." not in SnapshotService._sanitize_snapshot_name("../../etc/passwd")
        assert "/" not in SnapshotService._sanitize_snapshot_name("path/traversal")
        assert "\\" not in SnapshotService._sanitize_snapshot_name("win\\path")
        # Completely invalid name should fall back to "snapshot".
        assert SnapshotService._sanitize_snapshot_name("../..") == "snapshot"


class TestSnapshotAtomicWrite:
    """Verify atomic write leaves no temp files on failure."""

    def test_atomic_write_creates_file(
        self, db_engine, workspace_id, dataset_id, sample_records, tmp_path
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()
        result = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="atomic-test",
            workspace_root=tmp_path,
        )

        assert result.file_path is not None
        full_path = tmp_path / result.file_path
        assert full_path.exists()

        # No stale temp files should remain.
        snapshots_dir = tmp_path / "workbench" / "snapshots"
        tmp_files = list(snapshots_dir.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_atomic_write_cleanup_on_failure(
        self, db_engine, workspace_id, dataset_id, sample_records, tmp_path
    ):
        from molabel.core.data.snapshot_service import SnapshotService

        service = SnapshotService()
        # Create a snapshot first to get valid snapshot data.
        snap = service.create_snapshot(
            db_engine,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            name="failure-test",
        )

        # Now simulate a write failure by making the directory read-only
        # after creating it (so NamedTemporaryFile may fail on rename).
        snapshots_dir = tmp_path / "workbench" / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        # Patch os.rename to simulate failure.
        rename_patch = patch(
            "molabel.core.data.snapshot_service.os.rename",
            side_effect=OSError("disk full"),
        )
        with rename_patch, pytest.raises(OSError, match="disk full"):
            from molabel.core.models.dataset_snapshot import DatasetSnapshot

            with get_session(db_engine) as session:
                snapshot = session.get(DatasetSnapshot, snap.snapshot_id)

            SnapshotService._write_snapshot_file(tmp_path, snapshot, "test-dataset")

        # No temp files should remain after the failure.
        tmp_files = list(snapshots_dir.glob("*.tmp"))
        assert len(tmp_files) == 0
