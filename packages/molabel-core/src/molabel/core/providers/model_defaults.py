"""Canonical model profile defaults used across providers and workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfileDefaults:
    """Public defaults for a known provider/model profile."""

    provider_type: str
    provider_name: str
    model_identifier: str
    display_name: str
    base_url: str
    primary_auth_ref: str
    fallback_auth_ref: str | None = None
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None
    context_window: int | None = None
    supports_structured_output: bool = True


MINIMAX_M27_HIGHSPEED = ModelProfileDefaults(
    provider_type="anthropic",
    provider_name="MiniMax",
    model_identifier="MiniMax-M2.7-highspeed",
    display_name="MiniMax 2.7 highspeed",
    base_url="https://api.minimax.io/anthropic",
    primary_auth_ref="ANTHROPIC_API_KEY",
    fallback_auth_ref="MINIMAX_API_KEY",
    cost_per_input_token=1.0e-6,
    cost_per_output_token=3.0e-6,
    context_window=200000,
    supports_structured_output=True,
)

MINIMAX_MODEL_IDENTIFIERS = frozenset({MINIMAX_M27_HIGHSPEED.model_identifier})


def is_minimax_model(model_identifier: str) -> bool:
    """Return True when a model id refers to a canonical MiniMax profile."""

    normalized = model_identifier.strip().lower()
    return normalized in {
        model_id.lower() for model_id in MINIMAX_MODEL_IDENTIFIERS
    } or normalized.startswith("minimax-")
