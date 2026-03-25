"""Plugin discovery via Python entry points (PL-001)."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from molabel.core.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "molabel.plugins"


def discover_plugins(registry: PluginRegistry) -> PluginRegistry:
    """Discover and load all plugins registered under
    the ``molabel.plugins`` entry-point group.

    Each entry point is expected to resolve to a callable
    with the signature::

        def register(registry: PluginRegistry) -> None: ...

    Errors during loading or registration are captured per-plugin
    via :pymethod:`PluginRegistry.record_error` so that one broken
    plugin does not prevent others from loading (PL-004).

    Args:
        registry: The :class:`PluginRegistry` to populate.

    Returns:
        The same *registry* instance, now populated with whatever
        plugins were successfully loaded.
    """
    eps = entry_points(group=ENTRY_POINT_GROUP)

    loaded = 0
    failed = 0

    for ep in eps:
        plugin_id = ep.name
        logger.info("Discovering plugin entry point: %s (%s)", plugin_id, ep.value)
        try:
            register_fn = ep.load()
        except Exception as exc:
            logger.exception("Failed to import plugin %s from %s", plugin_id, ep.value)
            registry.record_error(plugin_id, exc)
            failed += 1
            continue

        try:
            register_fn(registry)
            loaded += 1
            logger.info("Plugin %s registered successfully", plugin_id)
        except Exception as exc:
            logger.exception("Plugin %s raised an error during registration", plugin_id)
            registry.record_error(plugin_id, exc)
            failed += 1

    logger.info("Plugin discovery complete: %d loaded, %d failed", loaded, failed)
    return registry
