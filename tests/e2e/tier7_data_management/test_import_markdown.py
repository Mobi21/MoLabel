"""T7-05: Markdown import via plugin loader.

Verifies:
- Content (body) preserved in stable_fields["content"]
- Front matter metadata extracted into stable_fields["front_matter"]
- Title extracted from front matter or first # heading
- Each .md file becomes one record with record_kind="markdown"
- Files without front matter get empty dict for front_matter
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier7
async def test_import_markdown(client, ctx):
    """T7-05: Markdown import — content preserved, front matter extracted."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post(
            "/api/v1/workspaces",
            json={
                "path": "/tmp/ws-markdown-import-test",
                "workspace_name": "Markdown Import Test",
            },
        )
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        ds = await client.post(
            "/api/v1/datasets",
            json={
                "dataset_name": "Markdown Dataset",
                "workspace_id": ws_id,
                "source_type": "markdown",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: File with front matter ──────────────────────────────────
    with checkpoint(ctx, "front_matter"):
        from molabel.plugins.loaders.markdown_loader import MarkdownLoader

        md_content = """\
---
id: doc-001
title: "Introduction to AI"
author: Alice
tags:
  - ai
  - ml
date: 2024-01-15
---

# Introduction to AI

This is the body of the article. It discusses artificial intelligence
and machine learning fundamentals.

## Section Two

More content here.
"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(md_content)
            md_path = Path(f.name)

        try:
            loader = MarkdownLoader()
            assert loader.can_load(md_path)

            records = list(loader.load_records(md_path, config={"id_field": "id"}))
            assert len(records) == 1

            rec = records[0]
            assert rec.record_kind == "markdown"

            # Content (body without front matter) preserved
            assert "Introduction to AI" in rec.stable_fields["content"]
            assert "Section Two" in rec.stable_fields["content"]

            # Front matter extracted
            fm = rec.stable_fields["front_matter"]
            assert isinstance(fm, dict)
            assert fm["author"] == "Alice"
            assert fm["id"] == "doc-001"
            assert "ai" in fm["tags"]

            # Title extracted from front matter
            assert rec.stable_fields.get("title") == "Introduction to AI"

            # external_id from id_field in front matter
            assert rec.external_id == "doc-001"

            # payload contains full document
            assert "content" in rec.payload
        finally:
            md_path.unlink(missing_ok=True)

    # ── Checkpoint 3: File without front matter ───────────────────────────────
    with checkpoint(ctx, "no_front_matter"):
        from molabel.plugins.loaders.markdown_loader import MarkdownLoader

        plain_md = """\
# Plain Article

This article has no front matter. Just a heading and body.

Some more text here.
"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(plain_md)
            plain_path = Path(f.name)

        try:
            loader2 = MarkdownLoader()
            records2 = list(loader2.load_records(plain_path, config={}))
            assert len(records2) == 1

            rec2 = records2[0]
            # Front matter is empty dict when absent
            assert rec2.stable_fields["front_matter"] == {}
            # Title extracted from first # heading
            assert rec2.stable_fields.get("title") == "Plain Article"
            # Content contains body
            assert "no front matter" in rec2.stable_fields["content"]
            # No external_id (no id_field in front matter)
            assert rec2.external_id is None
        finally:
            plain_path.unlink(missing_ok=True)

    # ── Checkpoint 4: Schema and count ───────────────────────────────────────
    with checkpoint(ctx, "schema_count"):
        from molabel.plugins.loaders.markdown_loader import MarkdownLoader

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("# Test\n\nHello\n")
            schema_path = Path(f.name)

        try:
            loader3 = MarkdownLoader()
            schema = loader3.get_schema(schema_path)
            props = schema["properties"]
            assert "content" in props
            assert "front_matter" in props
            assert "title" in props

            count = loader3.estimate_record_count(schema_path)
            assert count == 1
        finally:
            schema_path.unlink(missing_ok=True)

    # ── Checkpoint 5: API import ──────────────────────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/api/v1/datasets/{ds_id}/import",
            json={"source_uri": "test://markdown"},
        )
        assert resp.status_code == 202
        assert resp.json()["dataset_id"] == ds_id
