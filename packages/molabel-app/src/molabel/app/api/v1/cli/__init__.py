"""MoLabel CLI-specific additive router."""

from __future__ import annotations

from fastapi import APIRouter

from molabel.app.api.v1.cli.artifacts import router as artifacts_router
from molabel.app.api.v1.cli.operations import router as operations_router
from molabel.app.api.v1.cli.workspaces import router as workspaces_router

router = APIRouter(prefix="/cli", tags=["cli"])

router.include_router(workspaces_router)
router.include_router(artifacts_router)
router.include_router(operations_router)
