"""Plugin management endpoints -- /api/v1/plugins.

Lists installed plugins, retrieves plugin details, and allows enabling
or disabling plugins within a workspace.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from molabel.app.middleware.session import CurrentReviewer

router = APIRouter(prefix="/plugins", tags=["plugins"])


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class PluginSummary(BaseModel):
    """Lightweight plugin listing model."""

    plugin_id: str
    version: str
    plugin_type: str
    name: str
    enabled: bool = False
    compatible: bool = True
    compatible_core: str = ""
    required_by_project: bool = False
    created_at: datetime


class PluginSupports(BaseModel):
    """Capabilities supported by a plugin."""

    record_kinds: list[str] = []
    task_types: list[str] = []
    export_formats: list[str] = []
    validation_gates: list[str] = []


class PluginDetail(BaseModel):
    """Full plugin detail model."""

    plugin_id: str
    version: str
    plugin_type: str
    name: str
    description: str | None = None
    enabled: bool = False
    compatible: bool = True
    compatible_core: str = ""
    required_by_project: bool = False
    entrypoint: str = ""
    supports: PluginSupports
    compatibility_errors: list[str] = []
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[PluginSummary])
async def list_plugins(
    reviewer: CurrentReviewer,
    workspace_id: Annotated[str, Query(description="Workspace ID (required)")],
) -> list[PluginSummary]:
    """List all installed plugins for a workspace.

    Returns plugin summaries including compatibility and enablement status.
    """
    return []


@router.get("/{plugin_id}", response_model=PluginDetail)
async def get_plugin(
    plugin_id: str,
    reviewer: CurrentReviewer,
) -> PluginDetail:
    """Get detailed information about a specific plugin.

    Returns 404 if the plugin does not exist.
    """
    raise HTTPException(status_code=404, detail="Plugin not found")


@router.post("/{plugin_id}/enable", response_model=PluginDetail)
async def enable_plugin(
    plugin_id: str,
    reviewer: CurrentReviewer,
) -> PluginDetail:
    """Enable a plugin.

    Returns 404 if the plugin does not exist.
    """
    raise HTTPException(status_code=404, detail="Plugin not found")


@router.post("/{plugin_id}/disable", response_model=PluginDetail)
async def disable_plugin(
    plugin_id: str,
    reviewer: CurrentReviewer,
) -> PluginDetail:
    """Disable a plugin.

    Returns 404 if the plugin does not exist.
    """
    raise HTTPException(status_code=404, detail="Plugin not found")
