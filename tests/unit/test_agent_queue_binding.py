"""Tests for agent output binding to review queues (AG-005)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

import pytest

from molabel.core.agents.queue_binding import (
    AgentQueueBinder,
    deserialize_agent_output_ids,
    serialize_agent_output_ids,
)
from molabel.core.types import BlindReviewPolicy

# ---------------------------------------------------------------------------
# Lightweight stub objects (avoid SQLAlchemy mapper config)
# ---------------------------------------------------------------------------


@dataclass
class StubAgentOutput:
    """Minimal agent output stand-in for tests."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    record_id: uuid.UUID = field(default_factory=uuid.uuid4)
    is_visible_for_review: bool = False
    validation_passed: bool = True


@dataclass
class StubReviewTask:
    """Minimal review task stand-in for tests."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    record_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_output_ids: str | None = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def binder() -> AgentQueueBinder:
    return AgentQueueBinder()


def _make_output(record_id: uuid.UUID | None = None) -> StubAgentOutput:
    return StubAgentOutput(record_id=record_id or uuid.uuid4())


def _make_task(record_id: uuid.UUID | None = None) -> StubReviewTask:
    return StubReviewTask(record_id=record_id or uuid.uuid4())


# ---------------------------------------------------------------------------
# Serialization / deserialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_serialize_empty_list(self):
        result = serialize_agent_output_ids([])
        assert result == "[]"

    def test_round_trip(self):
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        serialized = serialize_agent_output_ids(ids)
        deserialized = deserialize_agent_output_ids(serialized)

        assert deserialized == ids

    def test_deserialize_none(self):
        assert deserialize_agent_output_ids(None) == []

    def test_deserialize_empty_string(self):
        assert deserialize_agent_output_ids("") == []

    def test_deserialize_invalid_json(self):
        assert deserialize_agent_output_ids("not-json") == []

    def test_deserialize_invalid_uuid(self):
        # Should return empty list when UUID parsing fails
        assert deserialize_agent_output_ids('["not-a-uuid"]') == []

    def test_serialized_format_is_valid_json(self):
        ids = [uuid.uuid4(), uuid.uuid4()]
        serialized = serialize_agent_output_ids(ids)
        parsed = json.loads(serialized)
        assert isinstance(parsed, list)
        assert len(parsed) == 2
        assert all(isinstance(item, str) for item in parsed)


# ---------------------------------------------------------------------------
# Visibility determination
# ---------------------------------------------------------------------------


class TestVisibility:
    def test_hide_by_default_policy(self, binder: AgentQueueBinder):
        assert (
            binder.determine_visibility(BlindReviewPolicy.hide_agent_outputs_by_default)
            is False
        )

    def test_show_outputs_policy(self, binder: AgentQueueBinder):
        assert binder.determine_visibility(BlindReviewPolicy.show_agent_outputs) is True

    def test_no_agent_policy(self, binder: AgentQueueBinder):
        assert binder.determine_visibility(BlindReviewPolicy.no_agent) is False

    def test_string_policy_value(self, binder: AgentQueueBinder):
        assert binder.determine_visibility("show_agent_outputs") is True
        assert binder.determine_visibility("hide_agent_outputs_by_default") is False
        assert binder.determine_visibility("no_agent") is False

    def test_none_policy_defaults_to_hidden(self, binder: AgentQueueBinder):
        assert binder.determine_visibility(None) is False

    def test_invalid_policy_defaults_to_hidden(self, binder: AgentQueueBinder):
        assert binder.determine_visibility("invalid_policy") is False

    def test_set_visibility_show(self, binder: AgentQueueBinder):
        outputs = [_make_output(), _make_output()]
        visible, hidden = binder.set_visibility_on_outputs(
            outputs, blind_review_policy=BlindReviewPolicy.show_agent_outputs
        )

        assert visible == 2
        assert hidden == 0
        assert all(o.is_visible_for_review is True for o in outputs)

    def test_set_visibility_hide(self, binder: AgentQueueBinder):
        outputs = [_make_output(), _make_output()]
        # Pre-set to visible to prove the method changes them
        for o in outputs:
            o.is_visible_for_review = True

        visible, hidden = binder.set_visibility_on_outputs(
            outputs,
            blind_review_policy=BlindReviewPolicy.hide_agent_outputs_by_default,
        )

        assert visible == 0
        assert hidden == 2
        assert all(o.is_visible_for_review is False for o in outputs)


# ---------------------------------------------------------------------------
# Binding outputs to tasks
# ---------------------------------------------------------------------------


class TestBindOutputsToTasks:
    def test_basic_binding(self, binder: AgentQueueBinder):
        record_id = uuid.uuid4()
        output = _make_output(record_id=record_id)
        task = _make_task(record_id=record_id)

        result = binder.bind_outputs_to_tasks(
            [output],
            [task],
            blind_review_policy=BlindReviewPolicy.show_agent_outputs,
        )

        assert result.review_task_count == 1
        assert result.agent_output_count == 1
        assert result.outputs_made_visible == 1
        assert result.outputs_hidden == 0
        assert result.errors == []

        # Verify the task has the output ID serialized
        stored_ids = deserialize_agent_output_ids(task.agent_output_ids)
        assert stored_ids == [output.id]

    def test_multiple_outputs_per_record(self, binder: AgentQueueBinder):
        record_id = uuid.uuid4()
        output1 = _make_output(record_id=record_id)
        output2 = _make_output(record_id=record_id)
        task = _make_task(record_id=record_id)

        result = binder.bind_outputs_to_tasks(
            [output1, output2],
            [task],
            blind_review_policy=BlindReviewPolicy.show_agent_outputs,
        )

        assert result.review_task_count == 1
        stored_ids = deserialize_agent_output_ids(task.agent_output_ids)
        assert set(stored_ids) == {output1.id, output2.id}

    def test_no_matching_outputs(self, binder: AgentQueueBinder):
        output = _make_output()
        task = _make_task()  # Different record_id

        result = binder.bind_outputs_to_tasks(
            [output],
            [task],
            blind_review_policy=BlindReviewPolicy.show_agent_outputs,
        )

        assert result.review_task_count == 0
        assert task.agent_output_ids is None

    def test_multiple_tasks_different_records(self, binder: AgentQueueBinder):
        record_id_a = uuid.uuid4()
        record_id_b = uuid.uuid4()

        output_a = _make_output(record_id=record_id_a)
        output_b = _make_output(record_id=record_id_b)
        task_a = _make_task(record_id=record_id_a)
        task_b = _make_task(record_id=record_id_b)

        result = binder.bind_outputs_to_tasks(
            [output_a, output_b],
            [task_a, task_b],
            blind_review_policy=BlindReviewPolicy.show_agent_outputs,
        )

        assert result.review_task_count == 2
        assert deserialize_agent_output_ids(task_a.agent_output_ids) == [output_a.id]
        assert deserialize_agent_output_ids(task_b.agent_output_ids) == [output_b.id]

    def test_merge_with_existing_output_ids(self, binder: AgentQueueBinder):
        record_id = uuid.uuid4()
        existing_output_id = uuid.uuid4()
        new_output = _make_output(record_id=record_id)

        task = _make_task(record_id=record_id)
        task.agent_output_ids = serialize_agent_output_ids([existing_output_id])

        binder.bind_outputs_to_tasks(
            [new_output],
            [task],
            blind_review_policy=BlindReviewPolicy.show_agent_outputs,
        )

        stored_ids = deserialize_agent_output_ids(task.agent_output_ids)
        assert len(stored_ids) == 2
        assert existing_output_id in stored_ids
        assert new_output.id in stored_ids

    def test_deduplication_on_merge(self, binder: AgentQueueBinder):
        record_id = uuid.uuid4()
        output = _make_output(record_id=record_id)

        task = _make_task(record_id=record_id)
        # Pre-populate with the same output ID
        task.agent_output_ids = serialize_agent_output_ids([output.id])

        binder.bind_outputs_to_tasks(
            [output],
            [task],
            blind_review_policy=BlindReviewPolicy.show_agent_outputs,
        )

        stored_ids = deserialize_agent_output_ids(task.agent_output_ids)
        assert len(stored_ids) == 1
        assert stored_ids[0] == output.id

    def test_empty_outputs_list(self, binder: AgentQueueBinder):
        task = _make_task()

        result = binder.bind_outputs_to_tasks(
            [],
            [task],
            blind_review_policy=BlindReviewPolicy.show_agent_outputs,
        )

        assert result.review_task_count == 0
        assert result.agent_output_count == 0
        assert task.agent_output_ids is None

    def test_empty_tasks_list(self, binder: AgentQueueBinder):
        output = _make_output()

        result = binder.bind_outputs_to_tasks(
            [output],
            [],
            blind_review_policy=BlindReviewPolicy.show_agent_outputs,
        )

        assert result.review_task_count == 0
        assert result.agent_output_count == 1

    def test_blind_review_hides_outputs(self, binder: AgentQueueBinder):
        record_id = uuid.uuid4()
        output = _make_output(record_id=record_id)
        task = _make_task(record_id=record_id)

        bind_result = binder.bind_outputs_to_tasks(
            [output],
            [task],
            blind_review_policy=BlindReviewPolicy.hide_agent_outputs_by_default,
        )

        assert bind_result.outputs_hidden == 1
        assert bind_result.outputs_made_visible == 0
        assert output.is_visible_for_review is False

        # Task should still have the binding (reviewer just can't see it yet)
        stored_ids = deserialize_agent_output_ids(task.agent_output_ids)
        assert len(stored_ids) == 1

    def test_default_policy_hides(self, binder: AgentQueueBinder):
        record_id = uuid.uuid4()
        output = _make_output(record_id=record_id)
        task = _make_task(record_id=record_id)

        binder.bind_outputs_to_tasks(
            [output],
            [task],
        )

        assert output.is_visible_for_review is False


# ---------------------------------------------------------------------------
# get / add / remove helpers
# ---------------------------------------------------------------------------


class TestTaskHelpers:
    def test_get_agent_output_ids_for_task(self, binder: AgentQueueBinder):
        ids = [uuid.uuid4(), uuid.uuid4()]
        task = _make_task()
        task.agent_output_ids = serialize_agent_output_ids(ids)

        result = binder.get_agent_output_ids_for_task(task)
        assert result == ids

    def test_get_agent_output_ids_for_task_with_none(self, binder: AgentQueueBinder):
        task = _make_task()
        assert binder.get_agent_output_ids_for_task(task) == []

    def test_add_output_to_task(self, binder: AgentQueueBinder):
        task = _make_task()
        output_id = uuid.uuid4()

        binder.add_output_to_task(task, output_id)

        stored = deserialize_agent_output_ids(task.agent_output_ids)
        assert stored == [output_id]

    def test_add_output_to_task_deduplicates(self, binder: AgentQueueBinder):
        task = _make_task()
        output_id = uuid.uuid4()

        binder.add_output_to_task(task, output_id)
        binder.add_output_to_task(task, output_id)

        stored = deserialize_agent_output_ids(task.agent_output_ids)
        assert len(stored) == 1

    def test_add_multiple_outputs_preserves_order(self, binder: AgentQueueBinder):
        task = _make_task()
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        id3 = uuid.uuid4()

        binder.add_output_to_task(task, id1)
        binder.add_output_to_task(task, id2)
        binder.add_output_to_task(task, id3)

        stored = deserialize_agent_output_ids(task.agent_output_ids)
        assert stored == [id1, id2, id3]

    def test_remove_output_from_task(self, binder: AgentQueueBinder):
        task = _make_task()
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        task.agent_output_ids = serialize_agent_output_ids([id1, id2])

        removed = binder.remove_output_from_task(task, id1)

        assert removed is True
        stored = deserialize_agent_output_ids(task.agent_output_ids)
        assert stored == [id2]

    def test_remove_nonexistent_output(self, binder: AgentQueueBinder):
        task = _make_task()
        id1 = uuid.uuid4()
        task.agent_output_ids = serialize_agent_output_ids([id1])

        removed = binder.remove_output_from_task(task, uuid.uuid4())

        assert removed is False
        stored = deserialize_agent_output_ids(task.agent_output_ids)
        assert stored == [id1]

    def test_remove_last_output_sets_none(self, binder: AgentQueueBinder):
        task = _make_task()
        output_id = uuid.uuid4()
        task.agent_output_ids = serialize_agent_output_ids([output_id])

        binder.remove_output_from_task(task, output_id)

        assert task.agent_output_ids is None


# ---------------------------------------------------------------------------
# Integration-style: full flow
# ---------------------------------------------------------------------------


class TestFullFlow:
    def test_end_to_end_bind_retrieve_modify(self, binder: AgentQueueBinder):
        """Simulate the full lifecycle: bind, retrieve, add, remove."""
        record_id = uuid.uuid4()
        output1 = _make_output(record_id=record_id)
        output2 = _make_output(record_id=record_id)
        task = _make_task(record_id=record_id)

        # Step 1: Bind initial outputs
        result = binder.bind_outputs_to_tasks(
            [output1],
            [task],
            blind_review_policy=BlindReviewPolicy.show_agent_outputs,
        )
        assert result.review_task_count == 1
        assert binder.get_agent_output_ids_for_task(task) == [output1.id]

        # Step 2: Add another output
        binder.add_output_to_task(task, output2.id)
        ids = binder.get_agent_output_ids_for_task(task)
        assert len(ids) == 2
        assert output1.id in ids
        assert output2.id in ids

        # Step 3: Remove first output
        removed = binder.remove_output_from_task(task, output1.id)
        assert removed is True
        assert binder.get_agent_output_ids_for_task(task) == [output2.id]

        # Step 4: Remove last output
        binder.remove_output_from_task(task, output2.id)
        assert task.agent_output_ids is None
        assert binder.get_agent_output_ids_for_task(task) == []

    def test_bind_with_multiple_records_and_policies(self, binder: AgentQueueBinder):
        """Multiple records, each with a different binding outcome."""
        record_a = uuid.uuid4()
        record_b = uuid.uuid4()
        record_c = uuid.uuid4()  # no output

        output_a = _make_output(record_id=record_a)
        output_b1 = _make_output(record_id=record_b)
        output_b2 = _make_output(record_id=record_b)

        task_a = _make_task(record_id=record_a)
        task_b = _make_task(record_id=record_b)
        task_c = _make_task(record_id=record_c)

        result = binder.bind_outputs_to_tasks(
            [output_a, output_b1, output_b2],
            [task_a, task_b, task_c],
            blind_review_policy=BlindReviewPolicy.hide_agent_outputs_by_default,
        )

        assert result.review_task_count == 2  # task_a and task_b have matches
        assert result.agent_output_count == 3
        assert result.outputs_hidden == 3
        assert result.outputs_made_visible == 0

        assert len(binder.get_agent_output_ids_for_task(task_a)) == 1
        assert len(binder.get_agent_output_ids_for_task(task_b)) == 2
        assert len(binder.get_agent_output_ids_for_task(task_c)) == 0
