from __future__ import annotations

from molabel.app.api.v1.workflows import (
    _build_record_prompt_content,
    _LlmAgentRunner,
)


def test_build_output_schema_preserves_grounded_json_arrays() -> None:
    runner = _LlmAgentRunner(conn=None, workspace_id="ws-test")

    schema = runner._build_output_schema(
        [
            {
                "name": "verdict",
                "field_type": "categorical",
                "required": True,
                "options": ["supports", "refutes", "nei"],
            },
            {
                "name": "evidence_atoms",
                "field_type": "json",
                "required": True,
            },
            {
                "name": "rationale_token_mask",
                "field_type": "json",
                "required": True,
            },
        ]
    )

    assert schema["properties"]["evidence_atoms"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert schema["properties"]["rationale_token_mask"] == {
        "type": "array",
        "items": {"type": "integer", "enum": [0, 1]},
    }


def test_build_output_schema_includes_option_rubric_descriptions() -> None:
    runner = _LlmAgentRunner(conn=None, workspace_id="ws-test")

    schema = runner._build_output_schema(
        [
            {
                "name": "intent_label",
                "field_type": "categorical",
                "required": True,
                "options": ["card_arrival", "card_delivery_estimate"],
                "description": "Canonical intent label.",
                "option_descriptions": {
                    "card_arrival": "Asked whether the card arrived or where it is.",
                    "card_delivery_estimate": "Asked for a delivery timeframe.",
                },
            }
        ]
    )

    description = schema["properties"]["intent_label"]["description"]
    assert "Option rubric" in description
    assert "`card_arrival`: Asked whether the card arrived" in description
    assert "`card_delivery_estimate`: Asked for a delivery timeframe" in description


def test_build_record_prompt_content_preserves_structured_payload() -> None:
    prompt = _build_record_prompt_content(
        record_identifier="record-1350",
        payload={
            "claim": "Example claim",
            "evidence": [
                {
                    "content": [
                        "Per Axel Rydberg_sentence_0",
                        "Per Axel Rydberg_cell_0_1_1",
                    ]
                }
            ],
            "label": "SUPPORTS",
        },
    )

    assert "Record ID: record-1350" in prompt
    assert "Raw record JSON" in prompt
    assert "Per Axel Rydberg_sentence_0" in prompt
    assert "Per Axel Rydberg_cell_0_1_1" in prompt
    assert '"label"' not in prompt
