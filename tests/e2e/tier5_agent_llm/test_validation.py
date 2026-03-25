"""Agent output validation tests (T5-01, T5-02).

T5-01: Structured output validation passes for valid labels.
T5-02: Validation failures trigger retry; retry_attempt increments; some recover.
"""

from __future__ import annotations

import pytest

from molabel.core.agents.output_validator import AgentOutputValidator
from molabel.core.types import LabelFieldDefinition, TaskSchema
from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.client import InstrumentedClient
from tests.e2e.infrastructure.logging_config import TestContext
from tests.e2e.infrastructure.parallel import SHARED_WORKSPACE


def _make_schema(task_slug: str, fields: list[dict]) -> TaskSchema:
    """Build a minimal TaskSchema for validation testing."""
    label_fields = [LabelFieldDefinition(**f) for f in fields]
    return TaskSchema(
        task_schema_id="00000000-0000-0000-0000-000000000001",
        workspace_id="00000000-0000-0000-0000-000000000002",
        task_slug=task_slug,
        task_type="classification",
        label_fields=label_fields,
        version=1,
    )


# ---------------------------------------------------------------------------
# T5-01: Structured output validation passes
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier5
async def test_validation_passes_for_valid_output(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T5-01: Valid structured output passes validation with no errors."""
    with checkpoint(ctx, "categorical_field_validation"):
        schema = _make_schema(
            "sentiment",
            [
                {
                    "name": "sentiment",
                    "field_type": "categorical",
                    "options": ["positive", "negative", "neutral"],
                    "required": True,
                }
            ],
        )

        validator = AgentOutputValidator(max_retries=1)
        result = validator.validate({"sentiment": "positive"}, schema)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert result.normalized_labels["sentiment"] == "positive"
        assert result.attempt == 1

    with checkpoint(ctx, "numeric_field_validation"):
        schema_num = _make_schema(
            "rating",
            [
                {
                    "name": "score",
                    "field_type": "numeric",
                    "scale_min": 0.0,
                    "scale_max": 1.0,
                    "required": True,
                }
            ],
        )

        result_num = validator.validate({"score": 0.75}, schema_num)
        assert result_num.is_valid is True
        assert result_num.normalized_labels["score"] == pytest.approx(0.75)

    with checkpoint(ctx, "multi_select_validation"):
        schema_ms = _make_schema(
            "topics",
            [
                {
                    "name": "topics",
                    "field_type": "multi_select",
                    "options": ["politics", "sports", "tech"],
                    "required": True,
                }
            ],
        )

        result_ms = validator.validate({"topics": ["politics", "tech"]}, schema_ms)
        assert result_ms.is_valid is True

    with checkpoint(ctx, "text_field_validation"):
        schema_txt = _make_schema(
            "rationale",
            [
                {
                    "name": "rationale",
                    "field_type": "text",
                    "required": True,
                }
            ],
        )

        result_txt = validator.validate(
            {"rationale": "This is the rationale."}, schema_txt
        )
        assert result_txt.is_valid is True


# ---------------------------------------------------------------------------
# T5-02: Validation failures with retry
# ---------------------------------------------------------------------------


@SHARED_WORKSPACE
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier5
async def test_validation_failure_with_retry_recovery(
    ctx: TestContext,
    client: InstrumentedClient,
) -> None:
    """T5-02: Validation failures trigger retry; retry_attempt increments; some recover.
    """
    with checkpoint(ctx, "missing_required_field_fails"):
        schema = _make_schema(
            "sentiment",
            [
                {
                    "name": "sentiment",
                    "field_type": "categorical",
                    "options": ["positive", "negative", "neutral"],
                    "required": True,
                }
            ],
        )
        validator = AgentOutputValidator(max_retries=3)

        result = validator.validate({}, schema)
        assert result.is_valid is False
        assert len(result.errors) >= 1
        error = result.errors[0]
        assert error.field == "sentiment"
        assert error.category == "missing_field"

    with checkpoint(ctx, "invalid_option_fails"):
        result_bad = validator.validate({"sentiment": "unknown_value"}, schema)
        assert result_bad.is_valid is False
        assert any(e.category == "out_of_range" for e in result_bad.errors)

    with checkpoint(ctx, "retry_recovers_on_second_attempt"):
        call_count = 0

        def retry_callback(ctx_retry):
            nonlocal call_count
            call_count += 1
            # On first retry, return valid labels
            return {"sentiment": "positive"}

        # Start with invalid labels
        result_retry = validator.validate_with_retry(
            {},  # missing required field
            schema,
            retry_callback=retry_callback,
        )

        assert call_count >= 1, "Retry callback should have been called"
        assert result_retry.is_valid is True
        assert result_retry.attempt == 2
        assert result_retry.normalized_labels["sentiment"] == "positive"

    with checkpoint(ctx, "retry_exhaustion_when_never_valid"):
        exhausted_call_count = 0

        def always_bad_callback(ctx_retry):
            nonlocal exhausted_call_count
            exhausted_call_count += 1
            # Always return an invalid value
            return {"sentiment": "always_wrong"}

        result_exhausted = validator.validate_with_retry(
            {},  # missing
            schema,
            retry_callback=always_bad_callback,
        )

        # max_retries=3 → attempts: 1 (initial) + 2 (retries) = 3
        assert exhausted_call_count == validator.max_retries - 1
        assert result_exhausted.is_valid is False

    with checkpoint(ctx, "numeric_out_of_range_fails"):
        schema_num = _make_schema(
            "score",
            [
                {
                    "name": "score",
                    "field_type": "numeric",
                    "scale_min": 0.0,
                    "scale_max": 1.0,
                    "required": True,
                }
            ],
        )

        result_range = validator.validate({"score": 1.5}, schema_num)
        assert result_range.is_valid is False
        assert any(e.category == "out_of_range" for e in result_range.errors)
