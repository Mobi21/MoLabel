"""MoLabel API v1 router.

Aggregates all v1 sub-routers under the ``/api/v1`` prefix.
"""

from __future__ import annotations

from fastapi import APIRouter

from molabel.app.api.v1.adjudication import router as adjudication_router
from molabel.app.api.v1.agent_runs import router as agent_runs_router
from molabel.app.api.v1.assistant import router as assistant_router
from molabel.app.api.v1.audit import router as audit_router
from molabel.app.api.v1.cli import router as cli_router
from molabel.app.api.v1.corrections import router as corrections_router
from molabel.app.api.v1.costs import router as costs_router
from molabel.app.api.v1.datasets import router as datasets_router
from molabel.app.api.v1.events import router as events_router
from molabel.app.api.v1.exports import router as exports_router
from molabel.app.api.v1.label_mappings import router as label_mappings_router
from molabel.app.api.v1.model_profiles import router as model_profiles_router
from molabel.app.api.v1.plugins import router as plugins_router
from molabel.app.api.v1.prompts import router as prompts_router
from molabel.app.api.v1.providers import router as providers_router
from molabel.app.api.v1.quality import router as quality_router
from molabel.app.api.v1.queue import router as queue_router
from molabel.app.api.v1.releases import router as releases_router
from molabel.app.api.v1.reviewer_profiles import router as reviewer_profiles_router
from molabel.app.api.v1.reviews import router as reviews_router
from molabel.app.api.v1.runtime_profiles import router as runtime_profiles_router
from molabel.app.api.v1.sessions import router as sessions_router
from molabel.app.api.v1.task_schemas import router as task_schemas_router
from molabel.app.api.v1.workflows import router as workflows_router
from molabel.app.api.v1.workspaces import router as workspaces_router

router = APIRouter(prefix="/api/v1")

# Core resources
router.include_router(workspaces_router)
router.include_router(datasets_router)
router.include_router(workflows_router)
router.include_router(task_schemas_router)
router.include_router(label_mappings_router)

# Providers & models
router.include_router(providers_router)
router.include_router(model_profiles_router)
router.include_router(runtime_profiles_router)

# Agent runs & prompts
router.include_router(agent_runs_router)
router.include_router(prompts_router)
router.include_router(corrections_router)

# Review & adjudication
router.include_router(queue_router)
router.include_router(reviews_router)
router.include_router(adjudication_router)

# Quality, exports, releases
router.include_router(quality_router)
router.include_router(exports_router)
router.include_router(releases_router)

# Session & identity
router.include_router(reviewer_profiles_router)
router.include_router(sessions_router)

# Operations & admin
router.include_router(audit_router)
router.include_router(plugins_router)
router.include_router(costs_router)
router.include_router(cli_router)

# AI assistant
router.include_router(assistant_router)

# SSE event streams
router.include_router(events_router)
