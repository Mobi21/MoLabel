"""VCR-style cassette manager for deterministic LLM tests.

Records real LLM API responses on the first run and replays them on
subsequent runs.  Cassettes are stored as JSON files per scenario ID
under tests/e2e/fixtures/cassettes/.

Usage::

    mgr = CassetteManager("T1-01")
    mgr.load()
    mgr.mock_provider(adapter)   # injects replay mock into adapter
    # ... run test ...
    mgr.save()                   # no-op in replay mode
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

CASSETTE_DIR = Path(__file__).parent.parent / "fixtures" / "cassettes"


class CassetteManager:
    """Record/replay LLM API calls for deterministic tests.

    In *replay* mode (default) the cassette file must exist; each call to
    mock_provider() wires up an AsyncMock that returns pre-recorded
    CompletionResult objects in order.

    In *record* mode (E2E_RECORD_CASSETTES=1) the real adapter is called and
    each response is stored; call save() at the end to persist the cassette.
    """

    def __init__(self, scenario_id: str, record: bool = False) -> None:
        self.path = CASSETTE_DIR / f"{scenario_id}.json"
        self.record = record
        self._responses: list[dict] = []
        self._call_index = 0

    def load(self) -> None:
        """Load a previously recorded cassette from disk."""
        if self.path.exists() and not self.record:
            self._responses = json.loads(self.path.read_text())

    def save(self) -> None:
        """Persist newly recorded responses to disk (record mode only)."""
        if self.record:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._responses, indent=2))

    def next_response(self) -> dict:
        """Pop the next pre-recorded response in sequence."""
        resp = self._responses[self._call_index]
        self._call_index += 1
        return resp

    def add_response(self, response: dict) -> None:
        """Append a live response during recording."""
        self._responses.append(response)

    def mock_provider(self, adapter: object, result_type: type | None = None) -> object:
        """Replace adapter.complete() with cassette playback.

        Args:
            adapter: The provider adapter instance to mock.
            result_type: Pydantic model class for deserialisation (defaults to
                         CompletionResult from molabel.core.types).

        Returns:
            The patched adapter (same object, mutated in place).
        """
        from molabel.core.types import CompletionResult

        result_cls = result_type or CompletionResult
        original = adapter.complete  # type: ignore[union-attr]

        async def replay(*args: object, **kwargs: object) -> object:
            if self.record:
                result = await original(*args, **kwargs)
                self.add_response(result.model_dump())
                return result
            return result_cls.model_validate(self.next_response())

        adapter.complete = AsyncMock(side_effect=replay)  # type: ignore[union-attr]
        return adapter
