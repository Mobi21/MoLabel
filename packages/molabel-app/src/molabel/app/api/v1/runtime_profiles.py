"""Runtime profile endpoints — /api/v1/runtime-profiles.

CRUD operations for runtime profiles with routing configuration.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from molabel.app.middleware.session import CurrentReviewer
from molabel.core.services.runtime_profile_service import (
    RetryConfig,
    RuntimeProfileCreate,
    RuntimeProfileResponse,
    RuntimeProfileService,
    RuntimeProfileUpdate,
)

router = APIRouter(prefix="/runtime-profiles", tags=["runtime-profiles"])

# Service instance (will be replaced by DI in a later step).
_service = RuntimeProfileService()

# Default workspace for placeholder endpoints.
_DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=RuntimeProfileResponse, status_code=201)
async def create_runtime_profile(
    data: RuntimeProfileCreate,
    _reviewer: CurrentReviewer,
) -> RuntimeProfileResponse:
    """Create a new runtime profile."""
    return _service.create(data, workspace_id=_DEFAULT_WORKSPACE)


@router.get("", response_model=list[RuntimeProfileResponse])
async def list_runtime_profiles() -> list[RuntimeProfileResponse]:
    """List runtime profiles for the current workspace."""
    return _service.list_profiles(_DEFAULT_WORKSPACE)


@router.get("/{profile_id}", response_model=RuntimeProfileResponse)
async def get_runtime_profile(
    profile_id: UUID,
) -> RuntimeProfileResponse:
    """Get a runtime profile by ID."""
    result = _service.get(profile_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Runtime profile not found")
    return result


@router.patch("/{profile_id}", response_model=RuntimeProfileResponse)
async def update_runtime_profile(
    profile_id: UUID,
    data: RuntimeProfileUpdate,
    _reviewer: CurrentReviewer,
) -> RuntimeProfileResponse:
    """Update an existing runtime profile."""
    result = _service.update(profile_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Runtime profile not found")
    return result


@router.delete("/{profile_id}", status_code=204)
async def delete_runtime_profile(
    profile_id: UUID,
    _reviewer: CurrentReviewer,
) -> None:
    """Delete a runtime profile."""
    if not _service.delete(profile_id):
        raise HTTPException(status_code=404, detail="Runtime profile not found")


@router.get("/{profile_id}/retry-config", response_model=RetryConfig)
async def get_retry_config(
    profile_id: UUID,
) -> RetryConfig:
    """Get the effective retry configuration for a runtime profile."""
    record = _service.get(profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Runtime profile not found")
    return _service.get_effective_retry_config(profile_id)
