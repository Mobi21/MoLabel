"""Tests for agent output normalization and validation (AG-004)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from molabel.core.agents.output_validator import (
    AgentOutputValidator,
    NormalizationStatus,
    RetryContext,
    ValidationErrorCategory,
)
from molabel.core.types import LabelFieldDefinition, TaskSchema

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_task_schema(
    label_fields: list[LabelFieldDefinition] | None = None,
    required_fields: list[str] | None = None,
) -> TaskSchema:
    """Create a minimal TaskSchema for testing."""
    default_fields = [
        LabelFieldDefinition(
            name="sentiment",
            field_type="categorical",
            options=["positive", "negative", "neutral"],
            required=True,
        ),
        LabelFieldDefinition(
            name="confidence_score",
            field_type="numeric",
            scale_min=0.0,
            scale_max=1.0,
            required=True,
        ),
    ]
    return TaskSchema(
        id=uuid.uuid4(),
        task_schema_slug="test-schema",
        version=1,
        task_type="ordinal_text_review",
        title="Test Schema",
        label_fields=label_fields if label_fields is not None else default_fields,
        required_fields=required_fields or [],
    )


@pytest.fixture()
def validator() -> AgentOutputValidator:
    return AgentOutputValidator(max_retries=3)


@pytest.fixture()
def schema() -> TaskSchema:
    return _make_task_schema()


# ---------------------------------------------------------------------------
# Basic validation tests
# ---------------------------------------------------------------------------


class TestBasicValidation:
    def test_valid_labels_pass(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "positive", "confidence_score": 0.85}
        result = validator.validate(labels, schema)

        assert result.is_valid is True
        assert result.errors == []
        assert result.normalization_status == NormalizationStatus.normalized
        assert result.normalized_labels["sentiment"] == "positive"
        assert result.normalized_labels["confidence_score"] == 0.85

    def test_missing_required_field(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "positive"}
        result = validator.validate(labels, schema)

        assert result.is_valid is False
        missing_errors = [
            e
            for e in result.errors
            if e.category == ValidationErrorCategory.missing_field
        ]
        assert len(missing_errors) == 1
        assert missing_errors[0].field == "confidence_score"

    def test_unknown_field(self, validator: AgentOutputValidator, schema: TaskSchema):
        labels = {
            "sentiment": "positive",
            "confidence_score": 0.5,
            "totally_made_up": "value",
        }
        result = validator.validate(labels, schema)

        assert result.is_valid is False
        unknown_errors = [
            e
            for e in result.errors
            if e.category == ValidationErrorCategory.unknown_field
        ]
        assert len(unknown_errors) == 1
        assert unknown_errors[0].field == "totally_made_up"

    def test_invalid_type_for_numeric(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "positive", "confidence_score": "not-a-number"}
        result = validator.validate(labels, schema)

        assert result.is_valid is False
        # The normalization will try to coerce "not-a-number" to float and fail
        type_errors = [
            e
            for e in result.errors
            if e.category == ValidationErrorCategory.invalid_type
        ]
        assert len(type_errors) >= 1

    def test_out_of_range_numeric(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "positive", "confidence_score": 1.5}
        result = validator.validate(labels, schema)

        assert result.is_valid is False
        range_errors = [
            e
            for e in result.errors
            if e.category == ValidationErrorCategory.out_of_range
        ]
        assert len(range_errors) == 1
        assert range_errors[0].field == "confidence_score"

    def test_out_of_range_below_minimum(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "positive", "confidence_score": -0.1}
        result = validator.validate(labels, schema)

        assert result.is_valid is False
        range_errors = [
            e
            for e in result.errors
            if e.category == ValidationErrorCategory.out_of_range
        ]
        assert len(range_errors) == 1
        assert "below minimum" in range_errors[0].message

    def test_invalid_categorical_value(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "ecstatic", "confidence_score": 0.5}
        result = validator.validate(labels, schema)

        assert result.is_valid is False
        range_errors = [
            e
            for e in result.errors
            if e.category == ValidationErrorCategory.out_of_range
        ]
        assert len(range_errors) == 1
        assert "ecstatic" in range_errors[0].message


# ---------------------------------------------------------------------------
# Normalization tests
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_case_insensitive_categorical_normalization(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "POSITIVE", "confidence_score": 0.5}
        result = validator.validate(labels, schema)

        assert result.is_valid is True
        assert result.normalized_labels["sentiment"] == "positive"

    def test_string_to_numeric_coercion(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "positive", "confidence_score": "0.75"}
        result = validator.validate(labels, schema)

        assert result.is_valid is True
        assert result.normalized_labels["confidence_score"] == 0.75

    def test_case_insensitive_field_name_matching(
        self, validator: AgentOutputValidator
    ):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="sentiment",
                    field_type="categorical",
                    options=["positive", "negative"],
                    required=True,
                ),
            ],
        )
        labels = {"Sentiment": "positive"}
        result = validator.validate(labels, schema)

        assert result.is_valid is True
        assert result.normalized_labels["sentiment"] == "positive"

    def test_bool_coercion_from_string(self, validator: AgentOutputValidator):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="is_toxic",
                    field_type="bool",
                    required=True,
                ),
            ],
        )
        labels = {"is_toxic": "true"}
        result = validator.validate(labels, schema)

        assert result.is_valid is True
        assert result.normalized_labels["is_toxic"] is True

    def test_bool_coercion_from_int(self, validator: AgentOutputValidator):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="is_toxic",
                    field_type="bool",
                    required=True,
                ),
            ],
        )
        labels = {"is_toxic": 1}
        result = validator.validate(labels, schema)

        assert result.is_valid is True
        assert result.normalized_labels["is_toxic"] is True

    def test_multi_select_coercion_from_csv_string(
        self, validator: AgentOutputValidator
    ):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="tags",
                    field_type="multi_select",
                    options=["politics", "sports", "tech"],
                    required=True,
                ),
            ],
        )
        labels = {"tags": "politics, tech"}
        result = validator.validate(labels, schema)

        assert result.is_valid is True
        assert result.normalized_labels["tags"] == ["politics", "tech"]

    def test_multi_select_invalid_option(self, validator: AgentOutputValidator):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="tags",
                    field_type="multi_select",
                    options=["politics", "sports", "tech"],
                    required=True,
                ),
            ],
        )
        labels = {"tags": ["politics", "astrology"]}
        result = validator.validate(labels, schema)

        assert result.is_valid is False
        range_errors = [
            e
            for e in result.errors
            if e.category == ValidationErrorCategory.out_of_range
        ]
        assert len(range_errors) == 1

    def test_text_field_coercion(self, validator: AgentOutputValidator):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="summary",
                    field_type="text",
                    required=True,
                ),
            ],
        )
        labels = {"summary": 12345}
        result = validator.validate(labels, schema)

        assert result.is_valid is True
        assert result.normalized_labels["summary"] == "12345"


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------


class TestRetryLogic:
    def test_retry_succeeds_on_second_attempt(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        bad_labels = {"sentiment": "ecstatic", "confidence_score": 0.5}
        good_labels = {"sentiment": "positive", "confidence_score": 0.5}

        def retry_callback(ctx: RetryContext) -> dict[str, Any]:
            assert ctx.attempt == 2
            assert len(ctx.previous_errors) > 0
            return good_labels

        result = validator.validate_with_retry(
            bad_labels, schema, retry_callback=retry_callback
        )

        assert result.is_valid is True
        assert result.attempt == 2

    def test_retry_exhausts_all_attempts(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        bad_labels = {"sentiment": "ecstatic", "confidence_score": 0.5}
        call_count = 0

        def always_fail_callback(ctx: RetryContext) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {"sentiment": "still_wrong", "confidence_score": 0.5}

        result = validator.validate_with_retry(
            bad_labels, schema, retry_callback=always_fail_callback
        )

        assert result.is_valid is False
        # max_retries=3 means initial + 2 retries
        assert call_count == 2
        assert result.attempt == 3

    def test_retry_not_triggered_on_valid_input(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "positive", "confidence_score": 0.5}
        callback = MagicMock()

        result = validator.validate_with_retry(labels, schema, retry_callback=callback)

        assert result.is_valid is True
        callback.assert_not_called()

    def test_retry_without_callback_returns_first_result(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        bad_labels = {"sentiment": "ecstatic", "confidence_score": 0.5}

        result = validator.validate_with_retry(bad_labels, schema, retry_callback=None)

        assert result.is_valid is False
        assert result.attempt == 1

    def test_retry_callback_exception_stops_retries(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        bad_labels = {"sentiment": "ecstatic", "confidence_score": 0.5}

        def failing_callback(ctx: RetryContext) -> dict[str, Any]:
            raise RuntimeError("LLM unavailable")

        result = validator.validate_with_retry(
            bad_labels, schema, retry_callback=failing_callback
        )

        assert result.is_valid is False
        assert result.attempt == 1  # Only the initial attempt result

    def test_retry_callback_returns_non_dict_stops_retries(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        bad_labels = {"sentiment": "ecstatic", "confidence_score": 0.5}

        def bad_return_callback(ctx: RetryContext) -> Any:
            return "not a dict"

        result = validator.validate_with_retry(
            bad_labels, schema, retry_callback=bad_return_callback
        )

        assert result.is_valid is False
        assert result.attempt == 1

    def test_retry_context_contains_previous_errors(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        bad_labels = {"sentiment": "ecstatic", "confidence_score": 0.5}
        captured_contexts: list[RetryContext] = []

        def capture_callback(ctx: RetryContext) -> dict[str, Any]:
            captured_contexts.append(ctx)
            return {"sentiment": "positive", "confidence_score": 0.5}

        validator.validate_with_retry(
            bad_labels, schema, retry_callback=capture_callback
        )

        assert len(captured_contexts) == 1
        ctx = captured_contexts[0]
        assert ctx.attempt == 2
        assert len(ctx.previous_errors) > 0
        assert ctx.original_labels == bad_labels
        assert ctx.task_schema.id == schema.id


# ---------------------------------------------------------------------------
# apply_to_agent_output tests
# ---------------------------------------------------------------------------


class TestApplyToAgentOutput:
    def test_apply_valid_result(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "positive", "confidence_score": 0.9}
        result = validator.validate(labels, schema)

        # Use a mock agent output object
        agent_output = MagicMock()
        validator.apply_to_agent_output(agent_output, result)

        assert agent_output.validation_passed is True
        assert agent_output.validation_errors is None
        assert agent_output.normalization_status == "normalized"
        assert agent_output.labels == result.normalized_labels
        assert agent_output.retry_attempt == 0

    def test_apply_invalid_result(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "ecstatic", "confidence_score": 0.5}
        result = validator.validate(labels, schema)

        agent_output = MagicMock()
        validator.apply_to_agent_output(agent_output, result)

        assert agent_output.validation_passed is False
        assert agent_output.validation_errors is not None
        assert len(agent_output.validation_errors) > 0
        # Each error should be a dict
        assert isinstance(agent_output.validation_errors[0], dict)

    def test_apply_retry_result_has_correct_attempt(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        bad_labels = {"sentiment": "ecstatic", "confidence_score": 0.5}
        good_labels = {"sentiment": "positive", "confidence_score": 0.5}

        def retry_callback(ctx: RetryContext) -> dict[str, Any]:
            return good_labels

        result = validator.validate_with_retry(
            bad_labels, schema, retry_callback=retry_callback
        )

        agent_output = MagicMock()
        validator.apply_to_agent_output(agent_output, result)

        assert agent_output.validation_passed is True
        assert agent_output.retry_attempt == 1  # attempt 2 => retry_attempt 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_labels(self, validator: AgentOutputValidator, schema: TaskSchema):
        result = validator.validate({}, schema)

        assert result.is_valid is False
        missing_errors = [
            e
            for e in result.errors
            if e.category == ValidationErrorCategory.missing_field
        ]
        assert len(missing_errors) == 2  # Both required fields missing

    def test_empty_schema(self, validator: AgentOutputValidator):
        schema = _make_task_schema(label_fields=[], required_fields=[])
        result = validator.validate({"anything": "goes"}, schema)

        # Unknown field should fail
        assert result.is_valid is False
        assert result.errors[0].category == ValidationErrorCategory.unknown_field

    def test_no_label_fields_no_labels(self, validator: AgentOutputValidator):
        schema = _make_task_schema(label_fields=[], required_fields=[])
        result = validator.validate({}, schema)

        assert result.is_valid is True

    def test_optional_field_can_be_absent(self, validator: AgentOutputValidator):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="required_field",
                    field_type="text",
                    required=True,
                ),
                LabelFieldDefinition(
                    name="optional_field",
                    field_type="text",
                    required=False,
                ),
            ],
        )
        result = validator.validate({"required_field": "present"}, schema)

        assert result.is_valid is True

    def test_none_value_for_required_field(
        self, validator: AgentOutputValidator, schema: TaskSchema
    ):
        labels = {"sentiment": "positive", "confidence_score": None}
        result = validator.validate(labels, schema)

        assert result.is_valid is False
        missing_errors = [
            e
            for e in result.errors
            if e.category == ValidationErrorCategory.missing_field
        ]
        assert any(e.field == "confidence_score" for e in missing_errors)

    def test_max_retries_clamped_to_at_least_one(self):
        v = AgentOutputValidator(max_retries=0)
        assert v.max_retries == 1

    def test_json_field_type_passthrough(self, validator: AgentOutputValidator):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="metadata",
                    field_type="json",
                    required=True,
                ),
            ],
        )
        complex_value = {"nested": {"deeply": [1, 2, 3]}}
        result = validator.validate({"metadata": complex_value}, schema)

        assert result.is_valid is True
        assert result.normalized_labels["metadata"] == complex_value

    def test_explicit_required_fields_override(self, validator: AgentOutputValidator):
        """When required_fields is explicitly set, it takes precedence."""
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(name="a", field_type="text", required=True),
                LabelFieldDefinition(name="b", field_type="text", required=True),
                LabelFieldDefinition(name="c", field_type="text", required=False),
            ],
            required_fields=["a"],
        )
        # Only "a" is required via explicit list
        result = validator.validate({"a": "present"}, schema)

        assert result.is_valid is True

    def test_ordinal_with_scale_range(self, validator: AgentOutputValidator):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="rating",
                    field_type="numeric",
                    scale_min=1.0,
                    scale_max=5.0,
                    required=True,
                ),
            ],
        )
        result = validator.validate({"rating": 3}, schema)
        assert result.is_valid is True

        result_low = validator.validate({"rating": 0}, schema)
        assert result_low.is_valid is False

        result_high = validator.validate({"rating": 6}, schema)
        assert result_high.is_valid is False


# ---------------------------------------------------------------------------
# Error categorization completeness
# ---------------------------------------------------------------------------


class TestErrorCategorization:
    def test_all_four_categories_can_appear(self, validator: AgentOutputValidator):
        schema = _make_task_schema(
            label_fields=[
                LabelFieldDefinition(
                    name="required_cat",
                    field_type="categorical",
                    options=["a", "b"],
                    required=True,
                ),
                LabelFieldDefinition(
                    name="required_num",
                    field_type="numeric",
                    scale_min=0,
                    scale_max=10,
                    required=True,
                ),
                LabelFieldDefinition(
                    name="required_bool",
                    field_type="bool",
                    required=True,
                ),
            ],
        )

        labels = {
            # missing: required_cat
            "required_num": 15,  # out_of_range
            "required_bool": "not-a-bool",  # invalid_type (coercion fails)
            "extra_field": "value",  # unknown_field
        }
        result = validator.validate(labels, schema)

        assert result.is_valid is False
        categories = {e.category for e in result.errors}
        assert ValidationErrorCategory.missing_field in categories
        assert ValidationErrorCategory.out_of_range in categories
        assert ValidationErrorCategory.unknown_field in categories
        # invalid_type is present due to bool coercion failure
        assert ValidationErrorCategory.invalid_type in categories
