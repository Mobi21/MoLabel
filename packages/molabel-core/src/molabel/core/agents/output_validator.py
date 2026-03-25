"""Agent output normalization and validation against task schemas (AG-004).

Validates agent-produced labels against the task schema's field definitions,
categorises errors, normalises raw output format, and supports retry logic
with validation-error context fed back for subsequent attempts.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from molabel.core.types import LabelFieldDefinition, TaskSchema

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class ValidationErrorCategory(StrEnum):
    """Categories for agent-output validation errors."""

    missing_field = "missing_field"
    invalid_type = "invalid_type"
    out_of_range = "out_of_range"
    unknown_field = "unknown_field"


class CategorizedValidationError(BaseModel):
    """A single validation error with category metadata."""

    field: str
    category: ValidationErrorCategory
    message: str
    expected: str | None = None
    received: str | None = None


class NormalizationStatus(StrEnum):
    """Normalization outcome for an agent output."""

    raw = "raw"
    normalized = "normalized"
    normalization_failed = "normalization_failed"


class OutputValidationResult(BaseModel):
    """Full result of validating and normalizing an agent output."""

    is_valid: bool
    errors: list[CategorizedValidationError] = []
    normalized_labels: dict[str, Any] = {}
    normalization_status: NormalizationStatus = NormalizationStatus.raw
    attempt: int = 1


class RetryContext(BaseModel):
    """Context passed to a retry callback so it can re-prompt the agent."""

    attempt: int
    previous_errors: list[CategorizedValidationError]
    original_labels: dict[str, Any]
    task_schema: TaskSchema


# ---------------------------------------------------------------------------
# Normalizer helpers
# ---------------------------------------------------------------------------

_BOOL_TRUE = frozenset({"true", "1", "yes", "y", "on"})
_BOOL_FALSE = frozenset({"false", "0", "no", "n", "off"})


def _coerce_to_type(
    value: Any,
    field_def: LabelFieldDefinition,
) -> tuple[Any, str | None]:
    """Attempt to coerce *value* to match the field definition's type.

    Returns ``(coerced_value, error_message_or_none)``.
    """
    ft = field_def.field_type

    if ft == "bool":
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str) and value.strip().lower() in _BOOL_TRUE:
            return True, None
        if isinstance(value, str) and value.strip().lower() in _BOOL_FALSE:
            return False, None
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value), None
        return value, f"Cannot coerce {type(value).__name__} to bool"

    if ft == "numeric":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value, None
        if isinstance(value, str):
            try:
                return float(value), None
            except ValueError:
                return value, f"Cannot coerce string '{value}' to numeric"
        return value, f"Cannot coerce {type(value).__name__} to numeric"

    if ft in ("categorical", "ordinal"):
        str_value = str(value).strip() if not isinstance(value, str) else value.strip()
        if field_def.options:
            # Try case-insensitive match
            lower_map = {opt.lower(): opt for opt in field_def.options}
            if str_value.lower() in lower_map:
                return lower_map[str_value.lower()], None
        return str_value, None

    if ft == "text":
        return str(value), None

    if ft == "multi_select":
        if isinstance(value, list):
            return value, None
        if isinstance(value, str):
            # Try comma-separated parsing
            return [item.strip() for item in value.split(",") if item.strip()], None
        return value, f"Cannot coerce {type(value).__name__} to list for multi_select"

    if ft == "json":
        return value, None

    # Unknown field type -- pass through
    return value, None


def _normalize_labels(
    raw_labels: dict[str, Any],
    field_defs: list[LabelFieldDefinition],
) -> tuple[dict[str, Any], list[CategorizedValidationError]]:
    """Normalize raw labels to match schema structure.

    Returns ``(normalized_labels, normalization_errors)``.
    """
    normalized: dict[str, Any] = {}
    errors: list[CategorizedValidationError] = []
    field_map = {fd.name: fd for fd in field_defs}

    # Build a case-insensitive lookup of the raw keys
    raw_lower: dict[str, tuple[str, Any]] = {}
    for key, val in raw_labels.items():
        raw_lower[key.lower()] = (key, val)

    for field_name, field_def in field_map.items():
        # Direct match first, then case-insensitive
        if field_name in raw_labels:
            raw_value = raw_labels[field_name]
        elif field_name.lower() in raw_lower:
            _, raw_value = raw_lower[field_name.lower()]
        else:
            # Field missing -- will be caught by required-field validation
            continue

        coerced, err = _coerce_to_type(raw_value, field_def)
        if err:
            errors.append(
                CategorizedValidationError(
                    field=field_name,
                    category=ValidationErrorCategory.invalid_type,
                    message=f"Normalization coercion failed: {err}",
                    expected=field_def.field_type,
                    received=type(raw_value).__name__,
                )
            )
            normalized[field_name] = raw_value
        else:
            normalized[field_name] = coerced

    # Preserve unknown fields (they'll be flagged in validation)
    known_lower = {fd.name.lower() for fd in field_defs}
    for key, val in raw_labels.items():
        if key.lower() not in known_lower:
            normalized[key] = val

    return normalized, errors


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_against_schema(
    labels: dict[str, Any],
    task_schema: TaskSchema,
) -> list[CategorizedValidationError]:
    """Validate normalized labels against the task schema field definitions."""
    errors: list[CategorizedValidationError] = []
    field_map = {fd.name: fd for fd in task_schema.label_fields}
    known_fields = set(field_map.keys())

    # Check required fields
    required = (
        set(task_schema.required_fields) if task_schema.required_fields else set()
    )
    if not required:
        # Fallback: treat all required label_field_definitions as required
        required = {fd.name for fd in task_schema.label_fields if fd.required}

    for req_field in required:
        if req_field not in labels or labels[req_field] is None:
            errors.append(
                CategorizedValidationError(
                    field=req_field,
                    category=ValidationErrorCategory.missing_field,
                    message=f"Required field '{req_field}' is missing",
                    expected="present",
                    received="absent",
                )
            )

    # Validate each present field
    for field_name, value in labels.items():
        if field_name not in known_fields:
            errors.append(
                CategorizedValidationError(
                    field=field_name,
                    category=ValidationErrorCategory.unknown_field,
                    message=f"Unknown field '{field_name}' not in task schema",
                )
            )
            continue

        field_def = field_map[field_name]

        # Type checks
        if field_def.field_type == "bool" and not isinstance(value, bool):
            errors.append(
                CategorizedValidationError(
                    field=field_name,
                    category=ValidationErrorCategory.invalid_type,
                    message=f"Expected bool, got {type(value).__name__}",
                    expected="bool",
                    received=type(value).__name__,
                )
            )
            continue

        if field_def.field_type == "numeric":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(
                    CategorizedValidationError(
                        field=field_name,
                        category=ValidationErrorCategory.invalid_type,
                        message=f"Expected numeric, got {type(value).__name__}",
                        expected="numeric",
                        received=type(value).__name__,
                    )
                )
                continue
            # Range check
            if field_def.scale_min is not None and value < field_def.scale_min:
                errors.append(
                    CategorizedValidationError(
                        field=field_name,
                        category=ValidationErrorCategory.out_of_range,
                        message=(
                            f"Value {value} is below minimum {field_def.scale_min}"
                        ),
                        expected=f">= {field_def.scale_min}",
                        received=str(value),
                    )
                )
            if field_def.scale_max is not None and value > field_def.scale_max:
                errors.append(
                    CategorizedValidationError(
                        field=field_name,
                        category=ValidationErrorCategory.out_of_range,
                        message=(
                            f"Value {value} is above maximum {field_def.scale_max}"
                        ),
                        expected=f"<= {field_def.scale_max}",
                        received=str(value),
                    )
                )

        if field_def.field_type in ("categorical", "ordinal"):
            if not isinstance(value, str):
                errors.append(
                    CategorizedValidationError(
                        field=field_name,
                        category=ValidationErrorCategory.invalid_type,
                        message=(
                            f"Expected string for {field_def.field_type},"
                            f" got {type(value).__name__}"
                        ),
                        expected="str",
                        received=type(value).__name__,
                    )
                )
                continue
            if field_def.options and value not in field_def.options:
                errors.append(
                    CategorizedValidationError(
                        field=field_name,
                        category=ValidationErrorCategory.out_of_range,
                        message=(
                            f"Value '{value}' not in allowed options: "
                            f"{field_def.options}"
                        ),
                        expected=f"one of {field_def.options}",
                        received=value,
                    )
                )
            # Ordinal range check when options is absent but scale_min/max present
            if field_def.field_type == "ordinal" and not field_def.options:
                try:
                    num = float(value)
                    if field_def.scale_min is not None and num < field_def.scale_min:
                        errors.append(
                            CategorizedValidationError(
                                field=field_name,
                                category=ValidationErrorCategory.out_of_range,
                                message=(
                                    f"Ordinal value {num} below"
                                    f" minimum {field_def.scale_min}"
                                ),
                                expected=f">= {field_def.scale_min}",
                                received=value,
                            )
                        )
                    if field_def.scale_max is not None and num > field_def.scale_max:
                        errors.append(
                            CategorizedValidationError(
                                field=field_name,
                                category=ValidationErrorCategory.out_of_range,
                                message=(
                                    f"Ordinal value {num} above"
                                    f" maximum {field_def.scale_max}"
                                ),
                                expected=f"<= {field_def.scale_max}",
                                received=value,
                            )
                        )
                except (ValueError, TypeError):
                    pass

        if field_def.field_type == "text" and not isinstance(value, str):
            errors.append(
                CategorizedValidationError(
                    field=field_name,
                    category=ValidationErrorCategory.invalid_type,
                    message=(
                        f"Expected string for text field, got {type(value).__name__}"
                    ),
                    expected="str",
                    received=type(value).__name__,
                )
            )

        if field_def.field_type == "multi_select":
            if not isinstance(value, list):
                errors.append(
                    CategorizedValidationError(
                        field=field_name,
                        category=ValidationErrorCategory.invalid_type,
                        message=(
                            f"Expected list for multi_select,"
                            f" got {type(value).__name__}"
                        ),
                        expected="list",
                        received=type(value).__name__,
                    )
                )
            elif field_def.options:
                invalid_items = [
                    item for item in value if item not in field_def.options
                ]
                if invalid_items:
                    errors.append(
                        CategorizedValidationError(
                            field=field_name,
                            category=ValidationErrorCategory.out_of_range,
                            message=(
                                f"Invalid multi_select values: {invalid_items}. "
                                f"Allowed: {field_def.options}"
                            ),
                            expected=f"subset of {field_def.options}",
                            received=str(invalid_items),
                        )
                    )

    return errors


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class AgentOutputValidator:
    """Validates and normalizes agent outputs against a task schema.

    The validator performs three steps:
    1. Normalize raw labels to match the expected schema structure.
    2. Validate the normalized labels against field definitions.
    3. Optionally retry via a caller-supplied callback that can re-prompt the agent.

    The service is stateless -- all context is passed per call.
    """

    def __init__(self, *, max_retries: int = 3) -> None:
        """Initialize the validator.

        Parameters
        ----------
        max_retries:
            Maximum number of validation attempts (including the initial one).
            Must be at least 1.
        """
        self._max_retries = max(1, int(max_retries))

    @property
    def max_retries(self) -> int:
        """The maximum number of validation attempts configured."""
        return self._max_retries

    def validate(
        self,
        labels: dict[str, Any],
        task_schema: TaskSchema,
    ) -> OutputValidationResult:
        """Validate and normalize a single set of labels.

        Returns a result with ``is_valid``, categorized errors, and the
        normalized labels.  Does not perform retries.
        """
        return self._do_validate(labels, task_schema, attempt=1)

    def validate_with_retry(
        self,
        labels: dict[str, Any],
        task_schema: TaskSchema,
        retry_callback: Any | None = None,
    ) -> OutputValidationResult:
        """Validate with automatic retry logic.

        Parameters
        ----------
        labels:
            The raw labels dict produced by the agent.
        task_schema:
            The task schema to validate against.
        retry_callback:
            An optional callable ``(RetryContext) -> dict[str, Any]`` that
            returns new labels for a retry attempt.  If ``None``, retries
            are skipped and the first result is returned immediately.

        Returns the best validation result (first passing, or the last attempt).
        """
        result = self._do_validate(labels, task_schema, attempt=1)
        if result.is_valid or retry_callback is None:
            return result

        current_labels = deepcopy(labels)
        best_result = result

        for attempt in range(2, self._max_retries + 1):
            ctx = RetryContext(
                attempt=attempt,
                previous_errors=list(best_result.errors),
                original_labels=current_labels,
                task_schema=task_schema,
            )
            try:
                new_labels = retry_callback(ctx)
            except Exception:
                logger.warning(
                    "Retry callback failed on attempt %d", attempt, exc_info=True
                )
                break

            if not isinstance(new_labels, dict):
                logger.warning(
                    "Retry callback returned non-dict on attempt %d, skipping",
                    attempt,
                )
                break

            current_labels = new_labels
            result = self._do_validate(current_labels, task_schema, attempt=attempt)
            best_result = result

            if result.is_valid:
                logger.info("Validation passed on retry attempt %d", attempt)
                break

        return best_result

    def apply_to_agent_output(
        self,
        agent_output: Any,
        validation_result: OutputValidationResult,
    ) -> None:
        """Update an AgentOutput model's validation fields in place.

        Works with both the SQLModel ``models.agent_output.AgentOutput``
        and the Pydantic ``types.AgentOutput`` value object, since both
        share the same field names.

        Parameters
        ----------
        agent_output:
            The AgentOutput instance to update.
        validation_result:
            The result from ``validate`` or ``validate_with_retry``.
        """
        agent_output.validation_passed = validation_result.is_valid
        agent_output.validation_errors = (
            [err.model_dump() for err in validation_result.errors]
            if validation_result.errors
            else None
        )
        agent_output.normalization_status = validation_result.normalization_status.value
        if validation_result.is_valid and validation_result.normalized_labels:
            agent_output.labels = validation_result.normalized_labels
        agent_output.retry_attempt = validation_result.attempt - 1

    # -- private helpers --

    def _do_validate(
        self,
        labels: dict[str, Any],
        task_schema: TaskSchema,
        *,
        attempt: int,
    ) -> OutputValidationResult:
        """Single-pass normalize + validate."""
        field_defs = task_schema.label_fields

        # 1. Normalize
        normalized, norm_errors = _normalize_labels(labels, field_defs)
        normalization_status = (
            NormalizationStatus.normalization_failed
            if norm_errors
            else NormalizationStatus.normalized
        )

        # 2. Validate
        validation_errors = _validate_against_schema(normalized, task_schema)

        all_errors = norm_errors + validation_errors
        is_valid = len(all_errors) == 0

        return OutputValidationResult(
            is_valid=is_valid,
            errors=all_errors,
            normalized_labels=normalized,
            normalization_status=normalization_status,
            attempt=attempt,
        )
