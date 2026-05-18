"""T7-10a: HuggingFace export — push-hf API endpoint and auth failure handling.

Verifies:
- POST /exports creates an export with format="huggingface_hub" (202)
- POST /exports/{id}/push-hf returns HFPushStatus with status="pending" (202)
- Auth failure: when no token is available, ValueError is raised by plugin
- HuggingFaceExporter.validate_export checks repo_id in metadata
"""

from __future__ import annotations

import uuid

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_export_huggingface(client, ctx):
    """T7-10a: HuggingFace export — push-hf creates repo entry, handles auth failure."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces",
            json={"path": "/tmp/ws-hf-export-test", "workspace_name": "HF Export Test"},
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "HF Export Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: Create HF export via API ───────────────────────────────
    with checkpoint(ctx, "create_hf_export"):
        resp = await client.post(
            "/api/v1/exports",
            json={
                "workspace_id": ws_id,
                "dataset_id": ds_id,
                "name": "HuggingFace Push",
                "format": "huggingface_hub",
                "include": {
                    "record_data": True,
                    "human_labels": True,
                },
            },
        )
        assert resp.status_code == 202
        export_body = resp.json()
        assert export_body["format"] == "huggingface_hub"
        export_id = export_body["export_id"]
        assert export_id

    # ── Checkpoint 3: push-hf endpoint returns 202 ───────────────────────────
    with checkpoint(ctx, "push_hf_endpoint"):
        push_resp = await client.post(
            f"/api/v1/exports/{export_id}/push-hf",
            json={
                "repo_id": "test-org/test-dataset",
                "split": "train",
                "private": True,
                "commit_message": "Test push from MoLabel",
            },
        )
        assert push_resp.status_code == 202
        push_body = push_resp.json()
        assert push_body["export_id"] == export_id
        assert push_body["repo_id"] == "test-org/test-dataset"
        assert push_body["status"] in ("pending", "queued")

    # ── Checkpoint 4: Auth failure from plugin (no token) ────────────────────
    with checkpoint(ctx, "auth_failure"):
        import os

        from molabel.core.types import SENTINEL_DATASET_ID, Record

        # Ensure no HF token in environment
        hf_token_backup = os.environ.pop("HF_TOKEN", None)
        hf_home_backup = os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)

        try:
            from molabel.plugins.exporters.huggingface_exporter import (
                HuggingFaceExporter,
            )

            records = [
                Record(
                    id=uuid.uuid4(),
                    dataset_id=SENTINEL_DATASET_ID,
                    stable_fields={"text": "hello"},
                    payload={},
                    record_kind=None,
                )
            ]

            exporter = HuggingFaceExporter()
            # Should raise ValueError due to missing token
            with pytest.raises(ValueError, match="(?i)token|auth|HuggingFace"):
                exporter.package(
                    records,
                    labels={},
                    config={"repo_id": "no-token/dataset"},
                )
        finally:
            if hf_token_backup is not None:
                os.environ["HF_TOKEN"] = hf_token_backup
            if hf_home_backup is not None:
                os.environ["HUGGING_FACE_HUB_TOKEN"] = hf_home_backup

    # ── Checkpoint 5: Validate export checks repo_id ─────────────────────────
    with checkpoint(ctx, "validate_artifact"):
        from molabel.core.types import ExportArtifact
        from molabel.plugins.exporters.huggingface_exporter import HuggingFaceExporter

        exporter2 = HuggingFaceExporter()

        # Valid artifact with repo_id
        good_artifact = ExportArtifact(
            format="huggingface_hub",
            record_count=5,
            checksum="abc123",
            metadata={"repo_id": "user/dataset", "split": "train"},
        )
        result_good = exporter2.validate_export(good_artifact)
        assert result_good.is_valid

        # Artifact missing repo_id
        bad_artifact = ExportArtifact(
            format="huggingface_hub",
            record_count=5,
            checksum="abc123",
            metadata={},
        )
        result_bad = exporter2.validate_export(bad_artifact)
        assert not result_bad.is_valid
        assert any("repo_id" in e.message for e in result_bad.errors)
