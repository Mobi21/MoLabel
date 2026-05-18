"""Provider adapters for external model hosting backends.

Each adapter implements the ``ModelProviderPlugin`` protocol from
``molabel.core.plugins.protocols`` and can be registered with the
``PluginRegistry``.
"""

from molabel.core.providers.anthropic_adapter import AnthropicAdapter
from molabel.core.providers.base import ProviderError
from molabel.core.providers.cost_tracking import CostTracker
from molabel.core.providers.custom_adapter import CustomAdapter
from molabel.core.providers.detection import ProviderDetector
from molabel.core.providers.hf_auth import HuggingFaceAuth
from molabel.core.providers.model_defaults import (
    MINIMAX_M27_HIGHSPEED,
    MINIMAX_MODEL_IDENTIFIERS,
    ModelProfileDefaults,
    is_minimax_model,
)
from molabel.core.providers.ollama_adapter import OllamaAdapter
from molabel.core.providers.openai_adapter import OpenAIAdapter
from molabel.core.providers.openrouter_adapter import OpenRouterAdapter
from molabel.core.providers.structured_output import StructuredOutputEnforcer

__all__ = [
    "AnthropicAdapter",
    "CostTracker",
    "CustomAdapter",
    "HuggingFaceAuth",
    "MINIMAX_M27_HIGHSPEED",
    "MINIMAX_MODEL_IDENTIFIERS",
    "ModelProfileDefaults",
    "OllamaAdapter",
    "OpenAIAdapter",
    "OpenRouterAdapter",
    "ProviderDetector",
    "ProviderError",
    "StructuredOutputEnforcer",
    "is_minimax_model",
]
