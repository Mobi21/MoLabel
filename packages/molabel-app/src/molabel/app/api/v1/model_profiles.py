"""Model profile endpoints — /api/v1/model-profiles.

CRUD operations for model profiles with connectivity testing.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from molabel.app.middleware.session import CurrentReviewer
from molabel.app.utils import get_engine
from molabel.core.services.model_profile_service import (
    ConnectivityTestResult,
    ModelProfileCreate,
    ModelProfileResponse,
    ModelProfileService,
    ModelProfileUpdate,
)

router = APIRouter(prefix="/model-profiles", tags=["model-profiles"])

# In-memory fallback for endpoints that don't need DB yet.
_service = ModelProfileService()

# Default workspace for placeholder endpoints.
_DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")


def _get_service(request: Request) -> ModelProfileService:
    """Return a service instance backed by the request's DB engine."""
    engine = get_engine(request)
    return ModelProfileService(engine=engine)


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
    request: Request,
    data: ModelProfileCreate,
    _reviewer: CurrentReviewer,
) -> ModelProfileResponse:
    """Create a new model profile."""
    service = _get_service(request)
    return service.create(data, workspace_id=_DEFAULT_WORKSPACE)


@router.get("", response_model=list[ModelProfileResponse])
async def list_model_profiles(
    request: Request,
    provider_type: str | None = None,
) -> list[ModelProfileResponse]:
    """List model profiles, optionally filtered by provider type."""
    service = _get_service(request)
    return service.list_profiles(
        _DEFAULT_WORKSPACE,
        provider_type=provider_type,
    )


@router.get("/{profile_id}", response_model=ModelProfileResponse)
async def get_model_profile(
    request: Request,
    profile_id: UUID,
) -> ModelProfileResponse:
    """Get a model profile by ID."""
    service = _get_service(request)
    result = service.get(profile_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Model profile not found")
    return result


@router.patch("/{profile_id}", response_model=ModelProfileResponse)
async def update_model_profile(
    request: Request,
    profile_id: UUID,
    data: ModelProfileUpdate,
    _reviewer: CurrentReviewer,
) -> ModelProfileResponse:
    """Update an existing model profile."""
    service = _get_service(request)
    result = service.update(profile_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Model profile not found")
    return result


@router.delete("/{profile_id}", status_code=204)
async def delete_model_profile(
    request: Request,
    profile_id: UUID,
    _reviewer: CurrentReviewer,
) -> None:
    """Delete a model profile."""
    service = _get_service(request)
    if not service.delete(profile_id):
        raise HTTPException(status_code=404, detail="Model profile not found")


@router.post(
    "/{profile_id}/test",
    response_model=ConnectivityTestResult,
)
async def test_model_profile(
    request: Request,
    profile_id: UUID,
    _reviewer: CurrentReviewer,
) -> ConnectivityTestResult:
    """Test connectivity to the provider configured in a model profile."""
    service = _get_service(request)
    return service.test_connectivity(profile_id)
