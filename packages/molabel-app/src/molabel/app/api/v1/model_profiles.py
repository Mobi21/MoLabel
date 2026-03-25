"""Model profile endpoints — /api/v1/model-profiles.

CRUD operations for model profiles with connectivity testing.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from molabel.app.middleware.session import CurrentReviewer
from molabel.core.services.model_profile_service import (
    ConnectivityTestResult,
    ModelProfileCreate,
    ModelProfileResponse,
    ModelProfileService,
    ModelProfileUpdate,
)

router = APIRouter(prefix="/model-profiles", tags=["model-profiles"])

# Service instance (will be replaced by DI in a later step).
_service = ModelProfileService()

# Default workspace for placeholder endpoints.
_DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ModelProfileListResponse(ModelProfileResponse):
    """Individual profile in a list response (inherits all fields)."""

    pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ModelProfileResponse, status_code=201)
async def create_model_profile(
    data: ModelProfileCreate,
    _reviewer: CurrentReviewer,
) -> ModelProfileResponse:
    """Create a new model profile."""
    return _service.create(data, workspace_id=_DEFAULT_WORKSPACE)


@router.get("", response_model=list[ModelProfileResponse])
async def list_model_profiles(
    provider_type: str | None = None,
) -> list[ModelProfileResponse]:
    """List model profiles, optionally filtered by provider type."""
    return _service.list_profiles(
        _DEFAULT_WORKSPACE,
        provider_type=provider_type,
    )


@router.get("/{profile_id}", response_model=ModelProfileResponse)
async def get_model_profile(
    profile_id: UUID,
) -> ModelProfileResponse:
    """Get a model profile by ID."""
    result = _service.get(profile_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Model profile not found")
    return result


@router.patch("/{profile_id}", response_model=ModelProfileResponse)
async def update_model_profile(
    profile_id: UUID,
    data: ModelProfileUpdate,
    _reviewer: CurrentReviewer,
) -> ModelProfileResponse:
    """Update an existing model profile."""
    result = _service.update(profile_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Model profile not found")
    return result


@router.delete("/{profile_id}", status_code=204)
async def delete_model_profile(
    profile_id: UUID,
    _reviewer: CurrentReviewer,
) -> None:
    """Delete a model profile."""
    if not _service.delete(profile_id):
        raise HTTPException(status_code=404, detail="Model profile not found")


@router.post(
    "/{profile_id}/test",
    response_model=ConnectivityTestResult,
)
async def test_model_profile(
    profile_id: UUID,
    _reviewer: CurrentReviewer,
) -> ConnectivityTestResult:
    """Test connectivity to the provider configured in a model profile."""
    return _service.test_connectivity(profile_id)
