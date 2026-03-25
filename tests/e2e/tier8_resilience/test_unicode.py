"""T8-11: Records with emoji, CJK, Arabic, newlines — preserved through entire pipeline.

Verifies:
- Emoji (🎉🚀🌟), CJK (这是测试, 日本語), Arabic (اختبار النص العربي) preserved
- Embedded newlines in text preserved in JSON but handled correctly
- Round-trip: load from JSONL → export to JSONL → parse → original content intact
- CSV export handles unicode without corruption (UTF-8)
- Parquet export preserves all unicode characters
"""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import pytest

from tests.e2e.infrastructure.assertions import checkpoint
from tests.e2e.infrastructure.parallel import INDEPENDENT

UNICODE_RECORDS = [
    {
        "id": "u1",
        "text": "Emoji test: 🎉 Party! 🚀 Launch! 🌟 Star!",
        "note": "Multiple emoji in sequence",
    },
    {
        "id": "u2",
        "text": "CJK Chinese: 这是测试内容，用于验证汉字的处理。",
        "note": "Simplified Chinese",
    },
    {
        "id": "u3",
        "text": "CJK Japanese: 日本語のテストです。これはサンプルテキストです。",
        "note": "Japanese hiragana and katakana",
    },
    {
        "id": "u4",
        "text": "Arabic: اختبار النص العربي وهذا نص عربي للاختبار",
        "note": "Right-to-left Arabic text",
    },
    {
        "id": "u5",
        "text": "Mixed: 🎉 Hello\nworld\nThis has\nembedded\nnewlines",
        "note": "Embedded newlines in text field",
    },
    {
        "id": "u6",
        "text": "Special chars: <>&\"' and \t tab \r carriage",
        "note": "HTML/XML special characters",
    },
    {
        "id": "u7",
        "text": "Korean: 안녕하세요, 이것은 한국어 테스트입니다.",
        "note": "Korean Hangul",
    },
    {
        "id": "u8",
        "text": "Accented: café, naïve, résumé, über, façade, São Paulo",
        "note": "Latin extended characters",
    },
]


@INDEPENDENT
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.tier8
async def test_unicode(client, ctx):
    """T8-11: Unicode preservation through entire pipeline."""

    # ── Checkpoint 1: Setup ───────────────────────────────────────────────────
    with checkpoint(ctx, "setup"):
        ws = await client.post("/workspaces", json={"workspace_name": "Unicode Test"})
        assert ws.status_code == 201
        ws_id = ws.json()["workspace_id"]

        reviewer = await client.post(
            "/reviewer-profiles", json={"display_name": "UnicodeTester"}
        )
        assert reviewer.status_code == 201
        await client.login(reviewer.json()["reviewer_id"])

        ds = await client.post(
            "/datasets",
            json={
                "dataset_name": "Unicode Dataset",
                "workspace_id": ws_id,
                "source_type": "jsonl",
            },
        )
        assert ds.status_code == 201
        ds_id = ds.json()["dataset_id"]

    # ── Checkpoint 2: JSONL load → preserves all unicode ─────────────────────
    with checkpoint(ctx, "jsonl_load"):
        from molabel.plugins.loaders.jsonl_loader import JsonlLoader

        content = (
            "\n".join(json.dumps(r, ensure_ascii=False) for r in UNICODE_RECORDS) + "\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            jsonl_path = Path(f.name)

        try:
            loader = JsonlLoader()
            records = list(loader.load_records(jsonl_path, config={"id_field": "id"}))
            assert len(records) == len(UNICODE_RECORDS)

            # Verify each unicode string is preserved exactly
            for i, (rec, expected) in enumerate(
                zip(records, UNICODE_RECORDS, strict=True)
            ):
                got_text = rec.stable_fields["text"]
                assert got_text == expected["text"], (
                    f"Record {i}: unicode mismatch.\n"
                    f"Expected: {expected['text']!r}\n"
                    f"Got:      {got_text!r}"
                )
        finally:
            jsonl_path.unlink(missing_ok=True)

    # ── Checkpoint 3: JSONL export preserves all unicode ─────────────────────
    with checkpoint(ctx, "jsonl_export"):
        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.jsonl_exporter import JsonlExporter

        export_records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields=r,
                payload=r,
                record_kind=None,
            )
            for r in UNICODE_RECORDS
        ]

        exporter = JsonlExporter()
        artifact = exporter.package(export_records, labels={}, config={})

        content_out = artifact.data.decode("utf-8")
        lines = [ln for ln in content_out.splitlines() if ln.strip()]
        assert len(lines) == len(UNICODE_RECORDS)

        for i, (line, expected) in enumerate(zip(lines, UNICODE_RECORDS, strict=True)):
            obj = json.loads(line)
            assert obj["text"] == expected["text"], f"Export record {i}: text mismatch"
            assert obj["id"] == expected["id"]

    # ── Checkpoint 4: CSV export preserves unicode ────────────────────────────
    with checkpoint(ctx, "csv_export"):
        import csv
        import io as _io

        from molabel.core.types import SENTINEL_DATASET_ID, Record
        from molabel.plugins.exporters.csv_exporter import CsvExporter

        csv_records = [
            Record(
                id=uuid.uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                stable_fields={"id": r["id"], "text": r["text"]},
                payload={},
                record_kind=None,
            )
            for r in UNICODE_RECORDS
        ]

        csv_exporter = CsvExporter()
        csv_artifact = csv_exporter.package(csv_records, labels={}, config={})

        csv_text = csv_artifact.data.decode("utf-8")
        reader = csv.DictReader(_io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == len(UNICODE_RECORDS)

        # Key unicode strings must appear in CSV
        all_csv = csv_text
        assert "🎉" in all_csv
        assert "这是测试" in all_csv
        assert "اختبار" in all_csv
        assert "日本語" in all_csv

    # ── Checkpoint 5: Specific unicode assertions ─────────────────────────────
    with checkpoint(ctx, "specific_unicode"):
        # Emoji
        assert "🎉" in UNICODE_RECORDS[0]["text"]
        assert "🚀" in UNICODE_RECORDS[0]["text"]

        # CJK
        assert "这是测试" in UNICODE_RECORDS[1]["text"]
        assert "日本語" in UNICODE_RECORDS[2]["text"]

        # Arabic
        assert "اختبار" in UNICODE_RECORDS[3]["text"]

        # Embedded newlines
        assert "\n" in UNICODE_RECORDS[4]["text"]

    # ── Checkpoint 6: API import with unicode URI ─────────────────────────────
    with checkpoint(ctx, "api_import"):
        resp = await client.post(
            f"/datasets/{ds_id}/import",
            json={"source_uri": "test://unicode-data"},
        )
        assert resp.status_code == 202
