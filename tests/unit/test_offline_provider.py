from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from molabel.app.api.v1.workflows import _LlmAgentRunner
from molabel.core.plugins.protocols import ModelProviderPlugin
from molabel.core.providers.base import ProviderError
from molabel.core.providers.offline_adapter import OFFLINE_MODEL_ID, OfflineAdapter
from molabel.core.providers.structured_output import StructuredOutputEnforcer
from molabel.core.types import Message


def _schema(fields: list[dict]) -> dict:
    return _LlmAgentRunner(conn=None, workspace_id="ws")._build_output_schema(fields)


def _categorical(options: list[str], name: str = "intent") -> dict:
    return {"name": name, "field_type": "categorical", "options": options}


def _label(text: str, fields: list[dict], *, system: str = "Label it.") -> dict:
    result = StructuredOutputEnforcer().enforce(
        OfflineAdapter(),
        [Message(role="system", content=system), Message(role="user", content=text)],
        OFFLINE_MODEL_ID,
        _schema(fields),
    )
    assert result.is_valid, result.validation_errors
    assert result.attempts == 1
    return result.parsed


def test_picks_the_option_the_text_mentions_ignoring_case() -> None:
    fields = [_categorical(["refund", "bug", "other"])]

    assert _label("The app crashes on login. Looks like a BUG.", fields) == {
        "intent": "bug"
    }


def test_matches_options_on_word_boundaries_only() -> None:
    fields = [_categorical(["other", "bug"])]

    assert _label("Any debugging tips?", fields) == {"intent": "other"}


def test_matches_multi_word_options_written_with_separators() -> None:
    fields = [_categorical(["other", "billing_issue", "card-arrival"])]

    assert _label("A billing issue with my card", fields) == {"intent": "billing_issue"}
    assert _label("Waiting on card arrival", fields) == {"intent": "card-arrival"}


def test_takes_the_first_matching_option_in_schema_order() -> None:
    fields = [_categorical(["refund", "bug", "other"])]

    assert _label("A bug made me ask for a refund", fields) == {"intent": "refund"}


def test_falls_back_to_the_first_option_when_nothing_matches() -> None:
    fields = [
        _categorical(["other", "refund"]),
        {"name": "severity", "field_type": "ordinal", "options": ["low", "high"]},
    ]

    assert _label("Hello there", fields) == {"intent": "other", "severity": "low"}


def test_reads_only_the_record_not_the_instructions() -> None:
    fields = [_categorical(["other", "refund"])]

    labels = _label(
        "Hello there",
        fields,
        system="Valid values: other, refund. Choose refund for money back.",
    )

    assert labels == {"intent": "other"}


def test_multi_select_takes_every_mentioned_option_and_none_when_unmatched() -> None:
    fields = [
        {
            "name": "topics",
            "field_type": "multi_select",
            "options": ["shipping", "refund", "bug"],
        }
    ]

    assert _label("Refund the shipping fee", fields) == {
        "topics": ["shipping", "refund"]
    }
    assert _label("Hello there", fields) == {"topics": []}


def test_boolean_is_true_only_when_the_text_names_the_field() -> None:
    fields = [{"name": "urgent", "field_type": "bool"}]

    assert _label("This is urgent, please help", fields) == {"urgent": True}
    assert _label("No rush at all", fields) == {"urgent": False}


def test_every_field_type_gets_a_value_that_passes_validation() -> None:
    fields = [
        _categorical(["refund", "bug"]),
        {"name": "severity", "field_type": "ordinal", "options": ["1", "2", "3"]},
        {"name": "topics", "field_type": "multi_select", "options": ["a", "b"]},
        {"name": "urgent", "field_type": "bool"},
        {"name": "score", "field_type": "numeric"},
        {"name": "notes", "field_type": "text"},
        {"name": "extra", "field_type": "json"},
        {"name": "evidence_atoms", "field_type": "json"},
        {"name": "rationale_token_mask", "field_type": "json"},
    ]

    assert _label("Nothing relevant here", fields) == {
        "intent": "refund",
        "severity": "1",
        "topics": [],
        "urgent": False,
        "score": 0,
        "notes": "",
        "extra": {},
        "evidence_atoms": [],
        "rationale_token_mask": [],
    }


_LABEL_IN_SUBPROCESS = """
import json, sys
from molabel.core.providers.offline_adapter import OfflineAdapter
from molabel.core.types import Message

schema = json.loads(sys.argv[1])
messages = [Message(role="user", content=sys.argv[2])]
result = OfflineAdapter().complete(messages, "offline-heuristic", output_schema=schema)
print(result.content)
"""


def test_same_input_gives_the_same_output_across_processes() -> None:
    schema = _schema(
        [
            _categorical(["refund", "bug", "other"]),
            {"name": "topics", "field_type": "multi_select", "options": ["x", "bug"]},
            {"name": "urgent", "field_type": "bool"},
        ]
    )
    text = "Urgent: a bug and a refund"

    outputs = {
        subprocess.run(
            [sys.executable, "-c", _LABEL_IN_SUBPROCESS, json.dumps(schema), text],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "2", "3")
    }

    assert outputs == {
        '{"intent": "refund", "topics": ["bug"], "urgent": true}\n',
    }


def test_refuses_a_call_without_an_output_schema() -> None:
    with pytest.raises(ProviderError):
        OfflineAdapter().complete([Message(role="user", content="hi")], "m")


def test_is_a_zero_cost_provider_plugin() -> None:
    adapter = OfflineAdapter()

    assert isinstance(adapter, ModelProviderPlugin)
    assert adapter.provider_type == "offline"
    assert adapter.check_health().is_healthy
    assert adapter.estimate_cost(1000, 1000, OFFLINE_MODEL_ID).total_cost == 0.0
    assert [m.model_id for m in adapter.list_models()] == [OFFLINE_MODEL_ID]
