"""Structured output enforcement and validation (PV-010, PV-011, PV-014).

Implements a two-tier strategy:
1. Provider-native structured output (when supported).
2. Prompt-based JSON fallback with post-hoc parsing.

Also handles output validation against task JSON schemas with
auto-retry (up to 3 attempts) and offline degradation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel

from molabel.core.providers.base import ProviderError
from molabel.core.types import CompletionResult, Message

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


class StructuredOutputResult(BaseModel):
    """Result of structured output enforcement."""

    parsed: dict[str, Any] | None = None
    raw_content: str = ""
    is_valid: bool = False
    validation_errors: list[str] = []
    attempts: int = 1
    used_native: bool = False


class StructuredOutputEnforcer:
    """Enforces structured (JSON) output from model completions.

    Strategy:
    1. If the provider supports native structured output, pass the
       ``output_schema`` directly to ``complete()``.
    2. Otherwise, inject a prompt-based JSON instruction and parse
       the raw text output.
    3. Validate the parsed output against the provided JSON schema.
    4. On validation failure, retry with error feedback (up to 3 times).

    Args:
        max_retries: Maximum retry attempts on validation failure.
    """

    def __init__(self, *, max_retries: int = _MAX_RETRIES) -> None:
        self._max_retries = max_retries

    def enforce(
        self,
        provider: Any,
        messages: list[Message],
        model: str,
        output_schema: dict[str, Any],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> StructuredOutputResult:
        """Execute completion with structured output enforcement.

        Args:
            provider: A ``ModelProviderPlugin`` implementation.
            messages: Chat messages to send.
            model: Model identifier.
            output_schema: JSON Schema the output must conform to.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            extra: Provider-specific extra parameters.

        Returns:
            StructuredOutputResult with parsed output if successful.
        """
        use_native = provider.supports_structured_output()
        last_result: CompletionResult | None = None
        all_errors: list[str] = []

        for attempt in range(1, self._max_retries + 1):
            try:
                if use_native:
                    result = provider.complete(
                        messages,
                        model,
                        output_schema=output_schema,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        extra=extra,
                    )
                else:
                    # Prompt-based fallback: inject JSON instruction
                    augmented = self._augment_messages_for_json(
                        messages, output_schema, all_errors
                    )
                    result = provider.complete(
                        augmented,
                        model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        extra=extra,
                    )
                last_result = result

                # Parse the output
                parsed = self._extract_json(result)
                if parsed is None:
                    all_errors.append(
                        f"Attempt {attempt}: Could not parse JSON from response"
                    )
                    continue

                # Validate against schema
                errors = self._validate_against_schema(parsed, output_schema)
                if errors:
                    all_errors.extend(f"Attempt {attempt}: {e}" for e in errors)
                    continue

                return StructuredOutputResult(
                    parsed=parsed,
                    raw_content=result.content,
                    is_valid=True,
                    attempts=attempt,
                    used_native=use_native,
                )

            except ProviderError:
                raise
            except Exception as exc:
                all_errors.append(f"Attempt {attempt}: {exc}")
                continue

        # All retries exhausted
        return StructuredOutputResult(
            parsed=self._extract_json(last_result) if last_result else None,
            raw_content=last_result.content if last_result else "",
            is_valid=False,
            validation_errors=all_errors,
            attempts=self._max_retries,
            used_native=use_native,
        )

    def _augment_messages_for_json(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        previous_errors: list[str],
    ) -> list[Message]:
        """Add JSON formatting instructions to the message list."""
        schema_str = json.dumps(schema, indent=2)
        instruction = (
            "You MUST respond with valid JSON that conforms to the following schema. "
            "Do not include any text outside the JSON object.\n\n"
            f"Schema:\n```json\n{schema_str}\n```"
        )
        if previous_errors:
            error_feedback = "\n".join(previous_errors[-3:])
            instruction += (
                f"\n\nPrevious attempts had errors:\n{error_feedback}\n"
                "Please fix these issues in your response."
            )

        augmented = list(messages)
        # Find or create system message
        has_system = any(m.role == "system" for m in augmented)
        if has_system:
            augmented = [
                Message(
                    role=m.role,
                    content=(
                        f"{m.content}\n\n{instruction}"
                        if m.role == "system"
                        else m.content
                    ),
                    name=m.name,
                )
                for m in augmented
            ]
        else:
            augmented.insert(0, Message(role="system", content=instruction))

        return augmented

    def _extract_json(self, result: CompletionResult) -> dict[str, Any] | None:
        """Extract JSON from a completion result."""
        # First try the parsed field (native structured output)
        if result.parsed is not None:
            return result.parsed

        # Try parsing the raw content
        content = result.content.strip()
        if not content:
            return None

        # Direct JSON parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code blocks
        json_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?\s*```",
            content,
            re.DOTALL,
        )
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding the first { ... } block
        brace_match = re.search(r"\{.*\}", content, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _validate_against_schema(
        self,
        data: dict[str, Any],
        schema: dict[str, Any],
    ) -> list[str]:
        """Validate data against a JSON schema.

        Returns a list of error messages (empty if valid).
        Uses a lightweight validation approach that does not
        depend on jsonschema library.
        """
        errors: list[str] = []

        # Check required properties
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        # Check property types
        for field, prop_schema in properties.items():
            if field not in data:
                continue
            value = data[field]
            expected_type = prop_schema.get("type")
            if expected_type and not self._check_type(value, expected_type):
                errors.append(
                    f"Field '{field}': expected type '{expected_type}', "
                    f"got '{type(value).__name__}'"
                )

            # Check enum constraints
            enum_values = prop_schema.get("enum")
            if enum_values is not None and value not in enum_values:
                errors.append(
                    f"Field '{field}': value '{value}' not in "
                    f"allowed values {enum_values}"
                )

        return errors

    def _check_type(self, value: Any, expected: str) -> bool:
        """Check if a value matches an expected JSON Schema type."""
        type_map: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected_types = type_map.get(expected)
        if expected_types is None:
            return True  # Unknown type, skip check
        return isinstance(value, expected_types)


def check_offline_status() -> bool:
    """Check if the system appears to be offline.

    Returns True if we can detect that network is unavailable.
    Used for PV-014 offline degradation.
    """
    import socket

    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return False
    except OSError:
        return True


class OfflineDegradationError(ProviderError):
    """Raised when a cloud provider call fails due to offline status.

    Used for PV-014: local features should still work, cloud failures
    show clear error messages.
    """

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Cannot reach {provider} provider. Check your internet connection. "
            f"Local features remain available.",
            provider=provider,
            retriable=True,
        )
