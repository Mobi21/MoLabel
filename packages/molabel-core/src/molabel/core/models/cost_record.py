"""CostRecord domain model (DM-031)."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index
from sqlmodel import JSON, Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from molabel.core.models.agent_output import AgentOutput
    from molabel.core.models.agent_run import AgentRun
    from molabel.core.models.model_profile import ModelProfile
    from molabel.core.models.workspace import Workspace


class CostRecord(SQLModel, table=True):
    """Tracks token usage and cost for an individual LLM request."""

    __tablename__ = "cost_records"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    agent_run_id: uuid.UUID = Field(foreign_key="agent_runs.id")
    agent_output_id: uuid.UUID | None = Field(
        default=None, foreign_key="agent_outputs.id"
    )
    model_profile_id: uuid.UUID = Field(foreign_key="model_profiles.id")
    tokens_input: int
    tokens_output: int
    cost_input: float | None = None
    cost_output: float | None = None
    cost_total: float | None = None
    latency_ms: int | None = None
    provider_response_metadata: dict | None = Field(
        default=None, sa_column=Column(JSON)
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # -- foreign keys --
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")

    # -- relationships --
    workspace: "Workspace" = Relationship(back_populates="cost_records")
    agent_run: "AgentRun" = Relationship()
    agent_output: Optional["AgentOutput"] = Relationship()
    model_profile: "ModelProfile" = Relationship(back_populates="cost_records")

    __table_args__ = (
        Index("idx_cost_records_run", "agent_run_id"),
        Index("idx_cost_records_model", "model_profile_id", "created_at"),
    )
