"""Derived subset model (DT-020).

Saved subset definitions, lineage-aware derived slices, and subset
promotion across curation/export/release flows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from molabel.core.database import get_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class SubsetDefinition(BaseModel):
    """A saved subset definition with selection criteria."""

    id: uuid.UUID | None = None
    name: str
    description: str = ""
    dataset_id: uuid.UUID
    workspace_id: uuid.UUID
    selection_criteria: dict[str, Any]
    """Selection criteria for the subset. Keys include:
    - ``filter``: filter expression (field, op, value)
    - ``sample_size``: number of records to sample
    - ``sample_strategy``: random, stratified, etc.
    - ``source_subset_id``: parent subset for lineage
    - ``include_record_ids``: explicit list of record IDs
    - ``exclude_record_ids``: explicit list to exclude
    """
    parent_subset_id: uuid.UUID | None = None
    """Lineage: the subset this was derived from."""
    record_count: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    tags: list[str] = []


class SubsetMaterializeResult(BaseModel):
    """Result of materializing a subset into record IDs."""

    subset_id: uuid.UUID
    record_ids: list[uuid.UUID]
    record_count: int
    warnings: list[str] = []


class SubsetPromotionResult(BaseModel):
    """Result of promoting a subset to a dataset."""

    new_dataset_id: uuid.UUID
    new_dataset_name: str
    record_count: int
    source_subset_id: uuid.UUID


# ---------------------------------------------------------------------------
# DerivedSubsetService
# ---------------------------------------------------------------------------


class DerivedSubsetService:
    """Manages derived subsets: definition, materialization, lineage, and promotion.

    Subsets are lightweight definitions (saved queries/filters) that can be
    materialized into concrete record ID lists, promoted to full datasets,
    or used as inputs for export and release flows.
    """

    def create_subset(
        self,
        engine: Any,
        *,
        definition: SubsetDefinition,
    ) -> uuid.UUID:
        """Save a subset definition and return its ID.

        The subset is stored in the ``saved_views`` table with
        ``view_type="subset"`` to reuse the existing infrastructure.
        """
        from molabel.core.models.saved_view import SavedView

        subset_id = uuid.uuid4()

        with get_session(engine) as session:
            view = SavedView(
                id=subset_id,
                workspace_id=definition.workspace_id,
                target_dataset_id=definition.dataset_id,
                view_name=definition.name,
                view_type="subset",
                description=definition.description,
                filters={
                    "selection_criteria": definition.selection_criteria,
                    "parent_subset_id": (
                        str(definition.parent_subset_id)
                        if definition.parent_subset_id
                        else None
                    ),
                    "tags": definition.tags,
                },
            )
            session.add(view)
            session.commit()

        return subset_id

    def get_subset(
        self,
        engine: Any,
        *,
        subset_id: uuid.UUID,
    ) -> SubsetDefinition | None:
        """Load a subset definition by ID."""
        from molabel.core.models.saved_view import SavedView

        with get_session(engine) as session:
            view = session.get(SavedView, subset_id)
            if not view or view.view_type != "subset":
                return None

            filters = view.filters or {}
            ds_id = (
                str(view.target_dataset_id)
                if view.target_dataset_id
                else filters.get("dataset_id", "")
            )
            return SubsetDefinition(
                id=view.id,
                name=view.view_name,
                description=view.description or "",
                dataset_id=uuid.UUID(ds_id) if ds_id else uuid.uuid4(),
                workspace_id=view.workspace_id,
                selection_criteria=filters.get("selection_criteria", {}),
                parent_subset_id=(
                    uuid.UUID(filters["parent_subset_id"])
                    if filters.get("parent_subset_id")
                    else None
                ),
                tags=filters.get("tags", []),
                created_at=view.created_at,
            )

    def list_subsets(
        self,
        engine: Any,
        *,
        workspace_id: uuid.UUID,
        dataset_id: uuid.UUID | None = None,
    ) -> list[SubsetDefinition]:
        """List subset definitions, optionally filtered by dataset."""
        from molabel.core.models.saved_view import SavedView

        with get_session(engine) as session:
            from sqlmodel import select

            stmt = select(SavedView).where(
                SavedView.workspace_id == workspace_id,
                SavedView.view_type == "subset",
            )
            views = list(session.exec(stmt).all())

        subsets: list[SubsetDefinition] = []
        for view in views:
            filters = view.filters or {}
            ds_id = (
                str(view.target_dataset_id)
                if view.target_dataset_id
                else filters.get("dataset_id", "")
            )
            if dataset_id and ds_id and str(dataset_id) != ds_id:
                continue

            subsets.append(
                SubsetDefinition(
                    id=view.id,
                    name=view.view_name,
                    description=view.description or "",
                    dataset_id=uuid.UUID(ds_id) if ds_id else uuid.uuid4(),
                    workspace_id=view.workspace_id,
                    selection_criteria=filters.get("selection_criteria", {}),
                    parent_subset_id=(
                        uuid.UUID(filters["parent_subset_id"])
                        if filters.get("parent_subset_id")
                        else None
                    ),
                    tags=filters.get("tags", []),
                    created_at=view.created_at,
                )
            )

        return subsets

    def materialize_subset(
        self,
        engine: Any,
        *,
        subset_id: uuid.UUID,
    ) -> SubsetMaterializeResult:
        """Materialize a subset definition into concrete record IDs.

        Evaluates the subset's selection criteria against the database
        and returns the matching record IDs.
        """
        definition = self.get_subset(engine, subset_id=subset_id)
        if not definition:
            raise ValueError(f"Subset {subset_id} not found")

        criteria = definition.selection_criteria
        record_ids = self._evaluate_criteria(engine, definition.dataset_id, criteria)

        warnings: list[str] = []
        if not record_ids:
            warnings.append("No records matched the subset criteria")

        return SubsetMaterializeResult(
            subset_id=subset_id,
            record_ids=record_ids,
            record_count=len(record_ids),
            warnings=warnings,
        )

    def promote_to_dataset(
        self,
        engine: Any,
        *,
        subset_id: uuid.UUID,
        new_dataset_name: str,
    ) -> SubsetPromotionResult:
        """Promote a subset to a full dataset.

        Creates a new dataset with the records from the subset, maintaining
        lineage back to the source subset and dataset.
        """
        from molabel.core.models.dataset import Dataset

        materialized = self.materialize_subset(engine, subset_id=subset_id)
        definition = self.get_subset(engine, subset_id=subset_id)
        if not definition:
            raise ValueError(f"Subset {subset_id} not found")

        import re

        slug = re.sub(r"[^\w\s-]", "", new_dataset_name.lower())
        slug = re.sub(r"[\s_]+", "-", slug).strip("-")[:64]

        with get_session(engine) as session:
            new_dataset = Dataset(
                workspace_id=definition.workspace_id,
                dataset_name=new_dataset_name,
                dataset_slug=slug,
                source_type="derived",
                source_config={
                    "source_subset_id": str(subset_id),
                    "source_dataset_id": str(definition.dataset_id),
                    "record_count": materialized.record_count,
                },
                canonical_id_strategy="source_record_id",
                indexing_mode="projection",
                record_count=materialized.record_count,
            )
            session.add(new_dataset)
            session.commit()
            session.refresh(new_dataset)
            new_dataset_id = new_dataset.id

        return SubsetPromotionResult(
            new_dataset_id=new_dataset_id,
            new_dataset_name=new_dataset_name,
            record_count=materialized.record_count,
            source_subset_id=subset_id,
        )

    def get_lineage(
        self,
        engine: Any,
        *,
        subset_id: uuid.UUID,
    ) -> list[SubsetDefinition]:
        """Trace the lineage of a subset back to its root.

        Returns a list of subset definitions from root to the given subset.
        """
        lineage: list[SubsetDefinition] = []
        current_id: uuid.UUID | None = subset_id

        visited: set[uuid.UUID] = set()
        while current_id and current_id not in visited:
            visited.add(current_id)
            definition = self.get_subset(engine, subset_id=current_id)
            if not definition:
                break
            lineage.append(definition)
            current_id = definition.parent_subset_id

        lineage.reverse()
        return lineage

    def delete_subset(
        self,
        engine: Any,
        *,
        subset_id: uuid.UUID,
    ) -> bool:
        """Delete a subset definition. Returns True if deleted."""
        from molabel.core.models.saved_view import SavedView

        with get_session(engine) as session:
            view = session.get(SavedView, subset_id)
            if not view or view.view_type != "subset":
                return False
            session.delete(view)
            session.commit()
            return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _evaluate_criteria(
        self,
        engine: Any,
        dataset_id: uuid.UUID,
        criteria: dict[str, Any],
    ) -> list[uuid.UUID]:
        """Evaluate selection criteria against the database."""
        from molabel.core.models.record import Record

        with get_session(engine) as session:
            from sqlmodel import select

            stmt = select(Record.id).where(Record.dataset_id == dataset_id)

            # Apply explicit include list if present.
            include_ids = criteria.get("include_record_ids")
            if include_ids:
                uuids = [uuid.UUID(rid) for rid in include_ids]
                return uuids

            records = list(session.exec(stmt).all())

        # Apply exclude list.
        exclude_ids = criteria.get("exclude_record_ids")
        if exclude_ids:
            exclude_set = {uuid.UUID(rid) for rid in exclude_ids}
            records = [r for r in records if r not in exclude_set]

        # Apply sample size.
        sample_size = criteria.get("sample_size")
        if sample_size and sample_size < len(records):
            import random

            strategy = criteria.get("sample_strategy", "random")
            if strategy == "random":
                records = random.sample(records, sample_size)
            else:
                records = records[:sample_size]

        return records
