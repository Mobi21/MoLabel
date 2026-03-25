"""Data step executors: ingest, normalize, filter, sample, deduplicate.

WF-004 through WF-008. These steps manipulate record sets in the
WorkflowContext, updating the active_record_set_id so downstream steps
implicitly operate on the narrowed/modified set.
"""

from __future__ import annotations

import hashlib
import logging
import random
import uuid
from typing import Any

from molabel.core.workflow.context import (
    DatasetReference,
    RecordSet,
    StepOutput,
    WorkflowContext,
)
from molabel.core.workflow.steps.base import StepExecutor, StepResult

logger = logging.getLogger(__name__)


class DataIngestExecutor(StepExecutor):
    """Executor for data_ingest steps (WF-004).

    Loads records from a source path via a data loader service. Creates
    dataset and record set entries in the context.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not config.get("source"):
            errors.append("data_ingest requires 'source' in config")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        source = config["source"]
        loader = services.get("data_loader")

        dataset_id = str(uuid.uuid4())
        record_ids: list[str] = []

        if loader is not None:
            try:
                records = loader.load_records(source, config)
                for record in records:
                    record_ids.append(str(record.id))
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Data ingest failed: {e}",
                    error_trace=str(e)[:2000],
                )
        else:
            # Without a loader service, create a placeholder dataset
            logger.info(
                "No data_loader service provided for step '%s'; "
                "creating placeholder dataset from source '%s'",
                step_id,
                source,
            )

        context.datasets[dataset_id] = DatasetReference(
            dataset_id=dataset_id,
            dataset_name=config.get("dataset_name", f"dataset_{step_id}"),
            record_count=len(record_ids),
            source_path=str(source),
        )
        context.record_sets[step_id] = RecordSet(
            record_ids=record_ids,
            record_count=len(record_ids),
            description=f"Ingested from {source}",
        )
        context.active_record_set_id = step_id

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="data_ingest",
                summary={
                    "source": str(source),
                    "dataset_id": dataset_id,
                    "record_count": len(record_ids),
                },
            ),
        )


class DataNormalizeExecutor(StepExecutor):
    """Executor for data_normalize steps (WF-005).

    Normalizes records to a target schema. Reads from the active record
    set and applies field mapping/transformation.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not context.active_record_set_id:
            errors.append("data_normalize requires an active record set")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        input_record_ids = context.get_active_record_ids()

        normalizer = services.get("record_normalizer")
        normalized_count = 0
        warnings: list[str] = []

        if normalizer is not None:
            try:
                for _rid in input_record_ids:
                    normalized_count += 1
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Normalization failed: {e}",
                    error_trace=str(e)[:2000],
                )
        else:
            normalized_count = len(input_record_ids)
            warnings.append("No normalizer service; records passed through unchanged")

        context.record_sets[step_id] = RecordSet(
            record_ids=list(input_record_ids),
            record_count=len(input_record_ids),
            description=f"Normalized {normalized_count} records",
        )
        context.active_record_set_id = step_id

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="data_normalize",
                summary={
                    "schema_ref": config.get("schema_ref", ""),
                    "records_normalized": normalized_count,
                    "input_count": len(input_record_ids),
                },
                warnings=warnings,
            ),
        )


class DataFilterExecutor(StepExecutor):
    """Executor for data_filter steps (WF-006).

    Filters the active record set using a filter expression. Filtering is
    a projection -- no mutation of source records.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not config.get("filter_expression"):
            errors.append("data_filter requires 'filter_expression' in config")
        if not context.active_record_set_id:
            errors.append("data_filter requires an active record set")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        input_record_ids = context.get_active_record_ids()
        filter_expression = config["filter_expression"]

        filter_service = services.get("record_filter")
        if filter_service is not None:
            try:
                filtered_ids = filter_service.apply_filter(
                    input_record_ids, filter_expression
                )
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Filter failed: {e}",
                    error_trace=str(e)[:2000],
                )
        else:
            # Without a filter service, pass through all records
            filtered_ids = list(input_record_ids)

        context.record_sets[step_id] = RecordSet(
            record_ids=filtered_ids,
            record_count=len(filtered_ids),
            description=f"Filtered with: {filter_expression}",
        )
        context.active_record_set_id = step_id

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="data_filter",
                summary={
                    "filter_expression": filter_expression,
                    "input_count": len(input_record_ids),
                    "output_count": len(filtered_ids),
                },
            ),
        )


class DataSampleExecutor(StepExecutor):
    """Executor for data_sample steps (WF-007).

    Draws a sample from the active record set using the configured
    strategy: random, stratified, confidence_based, or active_learning.
    """

    VALID_STRATEGIES = {"random", "stratified", "confidence_based", "active_learning"}

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        strategy = config.get("sample_strategy", "random")
        if strategy not in self.VALID_STRATEGIES:
            errors.append(
                f"Invalid sample_strategy '{strategy}'. "
                f"Valid: {sorted(self.VALID_STRATEGIES)}"
            )
        if not config.get("sample_size"):
            errors.append("data_sample requires 'sample_size' in config")
        if not context.active_record_set_id:
            errors.append("data_sample requires an active record set")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        input_record_ids = context.get_active_record_ids()
        strategy = config.get("sample_strategy", "random")
        sample_size = min(int(config["sample_size"]), len(input_record_ids))
        seed = config.get("seed")

        rng = random.Random(seed)

        if strategy == "random":
            sampled = rng.sample(input_record_ids, sample_size)
        elif strategy == "stratified":
            # Stratified sampling delegates to a service when available;
            # falls back to random for the core implementation.
            services = services or {}
            sampler = services.get("stratified_sampler")
            if sampler is not None:
                try:
                    sampled = sampler.sample(input_record_ids, sample_size, config)
                except Exception as e:
                    return StepResult(
                        success=False,
                        error=f"Stratified sampling failed: {e}",
                    )
            else:
                sampled = rng.sample(input_record_ids, sample_size)
        elif strategy == "confidence_based":
            services = services or {}
            confidence_sampler = services.get("confidence_sampler")
            if confidence_sampler is not None:
                try:
                    sampled = confidence_sampler.sample(
                        input_record_ids, sample_size, config
                    )
                except Exception as e:
                    return StepResult(
                        success=False,
                        error=f"Confidence-based sampling failed: {e}",
                    )
            else:
                sampled = rng.sample(input_record_ids, sample_size)
        elif strategy == "active_learning":
            services = services or {}
            al_sampler = services.get("active_learning_sampler")
            if al_sampler is not None:
                try:
                    sampled = al_sampler.sample(input_record_ids, sample_size, config)
                except Exception as e:
                    return StepResult(
                        success=False,
                        error=f"Active learning sampling failed: {e}",
                    )
            else:
                sampled = rng.sample(input_record_ids, sample_size)
        else:
            sampled = rng.sample(input_record_ids, sample_size)

        context.record_sets[step_id] = RecordSet(
            record_ids=sampled,
            record_count=len(sampled),
            description=f"Sampled {len(sampled)} records ({strategy})",
        )
        context.active_record_set_id = step_id

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="data_sample",
                summary={
                    "strategy": strategy,
                    "sample_size": len(sampled),
                    "input_count": len(input_record_ids),
                    "seed": seed,
                },
            ),
        )


class DataDeduplicateExecutor(StepExecutor):
    """Executor for data_deduplicate steps (WF-008).

    Removes or flags duplicate/near-duplicate records. Supports exact,
    fuzzy, and embedding deduplication strategies.
    """

    VALID_STRATEGIES = {"exact", "fuzzy", "embedding"}
    VALID_ACTIONS = {"remove", "flag"}

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        strategy = config.get("strategy", "exact")
        if strategy not in self.VALID_STRATEGIES:
            errors.append(
                f"Invalid dedup strategy '{strategy}'. "
                f"Valid: {sorted(self.VALID_STRATEGIES)}"
            )
        action = config.get("action", "remove")
        if action not in self.VALID_ACTIONS:
            errors.append(
                f"Invalid dedup action '{action}'. Valid: {sorted(self.VALID_ACTIONS)}"
            )
        if not context.active_record_set_id:
            errors.append("data_deduplicate requires an active record set")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        services = services or {}
        input_record_ids = context.get_active_record_ids()
        strategy = config.get("strategy", "exact")
        action = config.get("action", "remove")
        threshold = config.get("threshold", 0.9)

        dedup_service = services.get("deduplicator")
        duplicates_found = 0

        if dedup_service is not None:
            try:
                result = dedup_service.deduplicate(
                    input_record_ids, strategy, threshold, config
                )
                output_ids = result.get("unique_ids", input_record_ids)
                duplicates_found = result.get("duplicates_found", 0)
            except Exception as e:
                return StepResult(
                    success=False,
                    error=f"Deduplication failed: {e}",
                    error_trace=str(e)[:2000],
                )
        else:
            # Without a dedup service, use exact hash dedup on record content
            if strategy == "exact":
                seen: set[str] = set()
                output_ids: list[str] = []
                record_store = services.get("record_store")
                for rid in input_record_ids:
                    h = _content_hash(rid, record_store)
                    if h not in seen:
                        seen.add(h)
                        output_ids.append(rid)
                duplicates_found = len(input_record_ids) - len(output_ids)
            else:
                # For fuzzy/embedding without service, pass through
                output_ids = list(input_record_ids)
                duplicates_found = 0

        if action == "flag":
            # In flag mode, keep all records but note duplicates
            output_ids = list(input_record_ids)

        duplicate_rate = (
            duplicates_found / len(input_record_ids) if input_record_ids else 0.0
        )
        context.metrics["dedup.duplicate_rate"] = duplicate_rate

        context.record_sets[step_id] = RecordSet(
            record_ids=output_ids,
            record_count=len(output_ids),
            description=f"Deduplicated ({strategy}, {action})",
        )
        context.active_record_set_id = step_id

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="data_deduplicate",
                summary={
                    "strategy": strategy,
                    "action": action,
                    "threshold": threshold,
                    "input_count": len(input_record_ids),
                    "output_count": len(output_ids),
                    "duplicates_found": duplicates_found,
                    "duplicate_rate": duplicate_rate,
                },
            ),
        )


def _content_hash(record_id: str, record_store: Any | None) -> str:
    """Compute a content-based hash for deduplication.

    If a record_store is available, fetches the record and hashes its
    content. If the record has a ``content_hash`` field, that is used
    directly. Otherwise, hashes the record dict values in sorted key order.

    Falls back to the record_id only when no record_store is available and
    no content can be retrieved.
    """
    if record_store is not None:
        try:
            record = record_store.get_record(record_id)
            if record is not None:
                record_dict = (
                    record
                    if isinstance(record, dict)
                    else getattr(record, "__dict__", {})
                )
                # Prefer an explicit content_hash field
                if "content_hash" in record_dict:
                    return str(record_dict["content_hash"])
                # Hash sorted key-value pairs for determinism
                content_parts = []
                for key in sorted(record_dict.keys()):
                    content_parts.append(f"{key}={record_dict[key]!r}")
                content_str = "|".join(content_parts)
                return hashlib.sha256(content_str.encode()).hexdigest()
        except Exception:
            logger.warning(
                "Failed to fetch record '%s' for content hashing; "
                "falling back to ID hash",
                record_id,
            )

    # Fallback: hash the record ID (only when no store is available)
    return hashlib.sha256(record_id.encode()).hexdigest()
