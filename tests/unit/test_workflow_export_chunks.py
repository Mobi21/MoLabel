"""The workflow export step writes one line per record, in the step's order."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import StaticPool

from molabel.app.api.v1.workflows import _WorkflowExporter
from molabel.core.migration_runner import upgrade_database


def _seeded_engine(record_ids: list[str]) -> tuple[Engine, str]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    upgrade_database(engine)
    workspace_id = str(uuid.uuid4())
    dataset_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, workspace_name, workspace_slug, "
                "core_version, root_path, manifest_path, created_at, updated_at) "
                "VALUES (:id, 'w', 'w', '0.1.0', '/w', '/w/workbench.project.yaml', "
                ":now, :now)"
            ),
            {"id": workspace_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO datasets (id, dataset_name, dataset_slug, source_type, "
                "canonical_id_strategy, indexing_mode, created_at, updated_at, "
                "workspace_id) VALUES (:id, 'd', 'd', 'jsonl', 'external_id', "
                "'full', :now, :now, :wid)"
            ),
            {"id": dataset_id, "now": now, "wid": workspace_id},
        )
        conn.execute(
            text(
                "INSERT INTO records (id, external_id, sequence_index, stable_fields, "
                "payload, latest_label, label_count, export_eligible, created_at, "
                "updated_at, workspace_id, dataset_id) VALUES (:id, :external_id, "
                ":index, '{}', :payload, :label, 1, 0, :now, :now, :wid, :did)"
            ),
            [
                {
                    "id": record_id,
                    "external_id": f"ext-{index}",
                    "index": index,
                    "payload": json.dumps({"text": f"row {index}"}),
                    "label": json.dumps({"sentiment": "positive"}),
                    "now": now,
                    "wid": workspace_id,
                    "did": dataset_id,
                }
                for index, record_id in enumerate(record_ids)
            ],
        )
    return engine, workspace_id


def test_export_keeps_the_step_order_and_skips_unknown_ids(tmp_path: Path) -> None:
    """1,203 records span three id chunks; the file follows the requested order."""
    record_ids = [str(uuid.uuid4()) for _ in range(1203)]
    engine, _ = _seeded_engine(record_ids)
    requested = list(reversed(record_ids))
    requested.insert(7, str(uuid.uuid4()))

    with engine.connect() as conn:
        result = _WorkflowExporter(conn, workspace_root=tmp_path).export(
            record_ids=requested,
            format="jsonl",
            destination="workbench/exports/test",
            config={},
            bundle_id="bundle-1",
        )

    assert result["record_count"] == 1203
    lines = Path(result["file_path"]).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["record_id"] for line in lines] == record_ids[::-1]
    assert json.loads(lines[0]) == {
        "record_id": record_ids[-1],
        "external_id": "ext-1202",
        "text": "row 1202",
        "labels": {"sentiment": "positive"},
    }
