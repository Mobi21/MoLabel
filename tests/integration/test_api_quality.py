"""Integration tests for quality, costs, audit, plugins, and releases endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from molabel.app.main import create_app
from molabel.app.services.session import create_session_token

_SECRET = "quality-test-secret"


# ---------------------------------------------------------------------------
# Fixtures (self-contained, no dependency on shared conftest)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _db():
    """In-memory SQLite engine with workspace + reviewer tables."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE workspaces ("
                "id TEXT PRIMARY KEY, workspace_name TEXT, workspace_slug TEXT UNIQUE, "
                "core_version TEXT, root_path TEXT, manifest_path TEXT, "
                "created_at TEXT, updated_at TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE reviewer_profiles ("
                "id TEXT PRIMARY KEY, display_name TEXT, avatar_color TEXT, "
                "is_operator INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1, "
                "preferences TEXT, created_at TEXT, last_active_at TEXT, "
                "workspace_id TEXT REFERENCES workspaces(id))"
            )
        )
        conn.commit()
    return eng


@pytest.fixture()
def _seed(_db):
    """Insert workspace and reviewer, return (workspace_id, reviewer_id)."""
    ws_id = str(uuid.uuid4())
    r_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with _db.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces VALUES "
                "(:id,'Test','test','0.1.0','/tmp','/tmp/m.yaml',:now,:now)"
            ),
            {"id": ws_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO reviewer_profiles "
                "(id,display_name,avatar_color,is_operator,is_active,"
                "workspace_id,created_at,last_active_at) "
                "VALUES (:id,'Tester','#4A90D9',1,1,:ws,:now,:now)"
            ),
            {"id": r_id, "ws": ws_id, "now": now},
        )
        conn.commit()
    return ws_id, r_id


@pytest.fixture()
def _app(_db):
    application = create_app()
    application.state.engine = _db
    application.state.app_secret = _SECRET
    return application


@pytest_asyncio.fixture()
async def auth_client(_app, _seed):
    ws_id, r_id = _seed
    token = create_session_token(uuid.UUID(r_id), _SECRET)
    transport = ASGITransport(app=_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"molabel_session": token},
    ) as c:
        c.headers["X-Test-Workspace"] = ws_id  # convenience header for tests
        yield c


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _ws(client: AsyncClient) -> str:
    return client.headers["X-Test-Workspace"]


# ===================================================================
# Quality endpoints
# ===================================================================


class TestQualityDashboard:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/quality/dashboard",
            params={"workspace_id": _ws(auth_client)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "workspace_id" in body
        assert "readiness_gates" in body
        assert "recent_quality_trend" in body

    @pytest.mark.asyncio
    async def test_requires_workspace_id(self, auth_client):
        resp = await auth_client.get("/api/v1/quality/dashboard")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_requires_auth(self, _app):
        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(
                "/api/v1/quality/dashboard",
                params={"workspace_id": "any"},
            )
            assert resp.status_code == 401


class TestAgreementMetrics:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/quality/agreement",
            params={"workspace_id": _ws(auth_client)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "overall" in body
        assert "per_field" in body
        assert "per_reviewer" in body
        assert "confusion_matrices" in body

    @pytest.mark.asyncio
    async def test_requires_workspace_id(self, auth_client):
        resp = await auth_client.get("/api/v1/quality/agreement")
        assert resp.status_code == 422


class TestDriftReport:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/quality/drift",
            params={"workspace_id": _ws(auth_client)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "indicators" in body
        assert isinstance(body["indicators"], list)

    @pytest.mark.asyncio
    async def test_requires_workspace_id(self, auth_client):
        resp = await auth_client.get("/api/v1/quality/drift")
        assert resp.status_code == 422


# ===================================================================
# Cost endpoints
# ===================================================================


class TestCostSummary:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/costs",
            params={"workspace_id": _ws(auth_client)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["workspace_id"] == _ws(auth_client)
        assert "total_cost_usd" in body
        assert "by_model" in body
        assert "by_role" in body
        assert "daily_trend" in body

    @pytest.mark.asyncio
    async def test_requires_workspace_id(self, auth_client):
        resp = await auth_client.get("/api/v1/costs")
        assert resp.status_code == 422


class TestCostEstimate:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/costs/estimate",
            params={"model_profile_id": "test-model", "record_count": 100},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "estimated_cost_usd" in body
        assert "confidence" in body
        assert "warnings" in body


# ===================================================================
# Audit endpoints
# ===================================================================


class TestAuditList:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/audit",
            params={"workspace_id": _ws(auth_client)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "has_more" in body
        assert isinstance(body["items"], list)

    @pytest.mark.asyncio
    async def test_requires_workspace_id(self, auth_client):
        resp = await auth_client.get("/api/v1/audit")
        assert resp.status_code == 422


class TestAuditDetail:
    @pytest.mark.asyncio
    async def test_returns_404_for_missing(self, auth_client):
        resp = await auth_client.get(f"/api/v1/audit/{uuid.uuid4()}")
        assert resp.status_code == 404


# ===================================================================
# Plugin endpoints
# ===================================================================


class TestPluginList:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/plugins",
            params={"workspace_id": _ws(auth_client)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    @pytest.mark.asyncio
    async def test_requires_workspace_id(self, auth_client):
        resp = await auth_client.get("/api/v1/plugins")
        assert resp.status_code == 422


class TestPluginDetail:
    @pytest.mark.asyncio
    async def test_returns_404_for_missing(self, auth_client):
        resp = await auth_client.get(f"/api/v1/plugins/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestPluginEnable:
    @pytest.mark.asyncio
    async def test_returns_404_for_missing(self, auth_client):
        resp = await auth_client.post(f"/api/v1/plugins/{uuid.uuid4()}/enable")
        assert resp.status_code == 404


class TestPluginDisable:
    @pytest.mark.asyncio
    async def test_returns_404_for_missing(self, auth_client):
        resp = await auth_client.post(f"/api/v1/plugins/{uuid.uuid4()}/disable")
        assert resp.status_code == 404


# ===================================================================
# Release endpoints
# ===================================================================


class TestReleaseList:
    @pytest.mark.asyncio
    async def test_returns_200(self, auth_client):
        resp = await auth_client.get(
            "/api/v1/releases",
            params={"workspace_id": _ws(auth_client)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "has_more" in body

    @pytest.mark.asyncio
    async def test_requires_workspace_id(self, auth_client):
        resp = await auth_client.get("/api/v1/releases")
        assert resp.status_code == 422


class TestReleaseCreate:
    @pytest.mark.asyncio
    async def test_returns_201(self, auth_client):
        workspace_id = _ws(auth_client)
        resp = await auth_client.post(
            "/api/v1/releases",
            json={
                "workspace_id": workspace_id,
                "name": "v1.0",
                "version": "1.0.0",
                "export_ids": [],
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "draft"
        assert body["name"] == "v1.0"
        assert body["version"] == "1.0.0"
        assert body["proof_manifest"]["schema"] == "molabel.release.proof_manifest"
        audit_resp = await auth_client.get(
            "/api/v1/audit",
            params={"workspace_id": workspace_id, "event_type": "release_created"},
        )
        assert audit_resp.status_code == 200
        assert audit_resp.json()["items"][0]["object_id"] == body["release_id"]

    @pytest.mark.asyncio
    async def test_computes_benchmark_certification_gate(
        self, auth_client, _db, tmp_path
    ):
        workspace_id = _ws(auth_client)
        with _db.connect() as conn:
            conn.execute(
                text("UPDATE workspaces SET root_path = :root WHERE id = :id"),
                {"root": str(tmp_path), "id": workspace_id},
            )
            conn.commit()
        run_dir = tmp_path / "workbench" / "benchmarks" / "runs" / "cert-run"
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "benchmark_id": "psychology-survey-coding",
                    "run_id": "cert-run",
                    "mode": "operator",
                    "variant": "molabel_operated",
                    "stage": "operator_reviewed",
                    "record_count": 16,
                    "overall_score": 1.0,
                    "metrics": [{"metric_id": "operator_checklist", "value": 1.0}],
                    "diagnostics": {"blocking_failures": []},
                }
            ),
            encoding="utf-8",
        )
        resp = await auth_client.post(
            "/api/v1/releases",
            json={
                "workspace_id": workspace_id,
                "name": "Certified release",
                "version": "certified",
                "export_ids": [],
                "benchmark_run_ids": ["cert-run"],
                "certification_threshold": 1.0,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["validation_report"]["status"] == "passed"
        gate = body["validation_report"]["gates"][0]
        assert gate["gate_id"] == "benchmark:cert-run"
        assert gate["actual_value"] == 1.0
        assert body["proof_manifest"]["benchmark_run_ids"] == ["cert-run"]

    @pytest.mark.asyncio
    async def test_blocks_approval_when_certification_missing(self, auth_client):
        workspace_id = _ws(auth_client)
        create_resp = await auth_client.post(
            "/api/v1/releases",
            json={
                "workspace_id": workspace_id,
                "name": "Uncertified release",
                "version": "uncertified",
                "export_ids": [],
                "benchmark_run_ids": ["missing-run"],
            },
        )
        assert create_resp.status_code == 201
        body = create_resp.json()
        assert body["validation_report"]["status"] == "failed"
        approve_resp = await auth_client.post(
            f"/api/v1/releases/{body['release_id']}/approve",
            json={"approved": True},
        )
        assert approve_resp.status_code == 409


class TestReleaseDetail:
    @pytest.mark.asyncio
    async def test_returns_404_for_missing(self, auth_client):
        resp = await auth_client.get(f"/api/v1/releases/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reconstructs_proof_manifest_from_file(self, auth_client, _db):
        workspace_id = _ws(auth_client)
        create_resp = await auth_client.post(
            "/api/v1/releases",
            json={
                "workspace_id": workspace_id,
                "name": "Reopenable release",
                "version": "reopenable",
                "export_ids": [],
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.json()
        with _db.connect() as conn:
            conn.execute(
                text("UPDATE releases SET release_metadata = :metadata WHERE id = :id"),
                {"metadata": "{}", "id": created["release_id"]},
            )
            conn.commit()

        detail_resp = await auth_client.get(f"/api/v1/releases/{created['release_id']}")
        assert detail_resp.status_code == 200
        body = detail_resp.json()
        assert body["proof_manifest"]["release_id"] == created["release_id"]
        assert body["validation_report"]["status"] == "passed"


class TestReleaseApprove:
    @pytest.mark.asyncio
    async def test_returns_404_for_missing(self, auth_client):
        resp = await auth_client.post(
            f"/api/v1/releases/{uuid.uuid4()}/approve",
            json={"approved": True},
        )
        assert resp.status_code == 404
