"""Parallel execution helpers and group markers for pytest-xdist.

Tests are assigned to groups based on their state isolation properties:

- ``INDEPENDENT``: each test creates its own workspace + in-memory DB,
  so they can all run in parallel with zero shared state.
- ``SHARED_WORKSPACE``: tests share a read-only pre-populated workspace,
  safe to run in parallel as long as they don't mutate shared state.
- ``SEQUENTIAL``: tests must run in order because they exercise concurrent
  claim semantics, SSE streams, or session lifecycle operations.

Apply these markers to test functions or classes::

    @INDEPENDENT
    @pytest.mark.asyncio
    async def test_my_pipeline(...):
        ...

    @SEQUENTIAL
    @pytest.mark.asyncio
    async def test_concurrent_claims(...):
        ...
"""

from __future__ import annotations

import pytest

# ── Parallel group markers ───────────────────────────────────────────────────

# Group 1: Fully independent (each test gets its own in-memory DB)
# Covers: Tier 1, Tier 2, Tier 7, Tier 8, most of Tier 9
INDEPENDENT = pytest.mark.xdist_group("independent")

# Group 2: Shared workspace fixtures (read-only access to pre-populated data)
# Covers: Tier 3, Tier 5, Tier 6
SHARED_WORKSPACE = pytest.mark.xdist_group("shared_workspace")

# Group 3: Must run sequentially (SSE streams, concurrent claims, sessions)
# Covers: Tier 4, Tier 9 SSE + concurrency tests
SEQUENTIAL = pytest.mark.xdist_group("sequential")
