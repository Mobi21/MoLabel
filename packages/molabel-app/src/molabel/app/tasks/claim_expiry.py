"""Background task: claim expiry checker (SE-007).

Runs every POLL_INTERVAL_SECONDS (default 60s), finds claims older than
the configured timeout, and releases them back to the available pool.
Expired claims increment claim_expired_count on the review task.

Started as an asyncio task in the application lifespan.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.engine import Engine

from molabel.app.services.claims import (
    DEFAULT_CLAIM_TIMEOUT_MINUTES,
    expire_claims,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL_SECONDS: float = 60.0


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def claim_expiry_loop(
    engine: Engine,
    *,
    timeout_minutes: int = DEFAULT_CLAIM_TIMEOUT_MINUTES,
    poll_interval: float = POLL_INTERVAL_SECONDS,
) -> None:
    """Periodically expire stale claims.

    This coroutine runs indefinitely until cancelled.  It should be
    started as an asyncio task in the application lifespan and cancelled
    on shutdown.

    Parameters
    ----------
    engine:
        SQLAlchemy engine for database access.
    timeout_minutes:
        Claims older than this are expired (default 30 min).
    poll_interval:
        Seconds between expiry checks (default 60s).
    """
    logger.info(
        "Claim expiry task started (timeout=%d min, poll=%0.0fs)",
        timeout_minutes,
        poll_interval,
    )

    while True:
        try:
            await asyncio.sleep(poll_interval)
            # Run the synchronous DB operation in the default executor
            # to avoid blocking the event loop.
            loop = asyncio.get_running_loop()
            expired = await loop.run_in_executor(
                None, expire_claims, engine, timeout_minutes
            )
            if expired:
                logger.info("Expired %d stale claim(s)", len(expired))
        except asyncio.CancelledError:
            logger.info("Claim expiry task shutting down")
            break
        except Exception:
            logger.exception("Error in claim expiry task")
            # Continue running; transient errors should not kill the task.
            await asyncio.sleep(poll_interval)
