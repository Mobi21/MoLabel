"""Data Management Hub for MoLabel.

This package implements the core data management services:
- Workspace bootstrap and indexing (DT-001, DT-002, DT-016, DT-017, DT-018)
- Data source adapters (DT-003, DT-004, DT-005)
- Pre-label import and label mapping (DT-010, DT-011, DT-012)
- Dataset snapshots (DT-013, DT-014)
- Dataset operations and derived sets (DT-019, DT-020)
"""

from molabel.core.data.artifact_indexer import ArtifactIndexer
from molabel.core.data.dataset_operations import DatasetOperationsService
from molabel.core.data.derived_sets import DerivedSubsetService
from molabel.core.data.label_mapping_engine import LabelMappingEngine
from molabel.core.data.prelabel_import import PreLabelImporter
from molabel.core.data.snapshot_service import SnapshotService
from molabel.core.data.source_adapters import (
    HuggingFaceAdapter,
    LabelingToolAdapter,
    LocalFileAdapter,
)
from molabel.core.data.workspace_bootstrap import WorkspaceBootstrapper

__all__ = [
    "WorkspaceBootstrapper",
    "ArtifactIndexer",
    "LocalFileAdapter",
    "HuggingFaceAdapter",
    "LabelingToolAdapter",
    "PreLabelImporter",
    "LabelMappingEngine",
    "SnapshotService",
    "DatasetOperationsService",
    "DerivedSubsetService",
]
