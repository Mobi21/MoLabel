"""Gold sets through the API: files in the workspace, promotion, append, dedupe."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
import yaml
from sqlalchemy import text

from tests.integration.review_flow import (
    FIRST_REVIEWER,
    OFFLINE_SENTIMENT,
    _as,
    _external_ids,
    _review_all,
    _review_both,
    _start_review,
    review_app,
    review_client,
)
from tests.integration.test_api_workflows import _seed_reviewer, _seed_task_schema

GOLD = "sentiment-gold"


@pytest.fixture()
def app(tmp_path):
    return review_app(tmp_path)


@pytest_asyncio.fixture()
async def client(app):
    async with review_client(app) as c:
        yield c


def _sha256(path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _lines(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def _header(tmp_path, slug=GOLD) -> dict:
    return yaml.safe_load((tmp_path / "gold" / slug / "gold.yaml").read_text("utf-8"))


def _items_path(tmp_path, slug=GOLD):
    return tmp_path / "gold" / slug / "gold.jsonl"


async def _create(client, token, slug=GOLD, schema="sentiment-demo-v1"):
    created = await client.post(
        "/api/v1/gold-sets",
        json={"gold_set_id": slug, "name": "Sentiment gold", "task_schema_id": schema},
        headers=_as(token),
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _promote(client, token, body, slug=GOLD, action="promote"):
    resp = await client.post(
        f"/api/v1/gold-sets/{slug}/{action}", json=body, headers=_as(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _adjudicate_r3(client, app, queue_id, token, labels):
    record_id = _external_ids(app)["r3"]
    path = f"/api/v1/adjudication/queues/{queue_id}/disagreements/{record_id}"
    shown = (await client.get(path, headers=_as(token))).json()
    resolved = await client.post(
        f"{path}/resolve",
        json={
            "resolved_labels": labels,
            "review_event_ids": [
                s["review_event_id"] for s in shown["reviewer_labels"]
            ],
        },
        headers=_as(token),
    )
    assert resolved.status_code == 200, resolved.text
    return resolved.json()


async def _reviewed_and_adjudicated(client, app, tmp_path):
    workspace_id, tokens, queue = await _start_review(client, app, tmp_path)
    await _review_both(client, queue["queue_id"], tokens)
    resolution = await _adjudicate_r3(
        client, app, queue["queue_id"], tokens[0], {"sentiment": "negative"}
    )
    return workspace_id, tokens, queue["queue_id"], resolution


def _reviewer_ids(app) -> list[str]:
    with app.state.engine.connect() as conn:
        return [
            str(r[0])
            for r in conn.execute(
                text("SELECT id FROM reviewer_profiles ORDER BY created_at")
            )
        ]


@pytest.mark.asyncio
async def test_create_writes_an_empty_first_version_and_lists_it(client, app, tmp_path):
    _, tokens, _ = await _start_review(client, app, tmp_path)

    created = await _create(client, tokens[0])

    header = _header(tmp_path)
    assert header["gold_set_id"] == GOLD
    assert header["task_schema"] == "sentiment-demo-v1"
    assert (header["version"], header["item_count"]) == (1, 0)
    assert header["previous_hash"] is None
    assert _items_path(tmp_path).read_bytes() == b""
    assert header["content_hash"] == _sha256(_items_path(tmp_path))
    manifest = yaml.safe_load((tmp_path / "workbench.project.yaml").read_text("utf-8"))
    assert manifest["gold_sets"] == [
        {"gold_set_id": GOLD, "definition_path": "gold/sentiment-gold/gold.yaml"}
    ]
    assert created["path"] == "gold/sentiment-gold/gold.yaml"

    listed = await client.get("/api/v1/gold-sets", headers=_as(tokens[0]))
    assert [s["gold_set_id"] for s in listed.json()["items"]] == [GOLD]


@pytest.mark.asyncio
async def test_create_refuses_a_set_that_exists_or_a_schema_that_does_not(
    client, app, tmp_path
):
    _, tokens, _ = await _start_review(client, app, tmp_path)
    await _create(client, tokens[0])

    again = await client.post(
        "/api/v1/gold-sets",
        json={"gold_set_id": GOLD, "task_schema_id": "sentiment-demo-v1"},
        headers=_as(tokens[0]),
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "GOLD_SET_EXISTS"

    unknown = await client.post(
        "/api/v1/gold-sets",
        json={"gold_set_id": "other", "task_schema_id": "no-such-schema"},
        headers=_as(tokens[0]),
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "TASK_SCHEMA_NOT_FOUND"

    traversal = await client.post(
        "/api/v1/gold-sets",
        json={"gold_set_id": "../outside", "task_schema_id": "sentiment-demo-v1"},
        headers=_as(tokens[0]),
    )
    assert traversal.status_code == 422
    assert not (tmp_path / "outside").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("orphan", ["gold.jsonl", "gold.yaml", "notes.md"])
async def test_create_refuses_a_folder_holding_files_the_manifest_does_not_list(
    client, app, tmp_path, orphan
):
    _, tokens, _ = await _start_review(client, app, tmp_path)
    folder = tmp_path / "gold" / GOLD
    folder.mkdir(parents=True)
    kept = b'{"input": {"text": "hand made"}, "expected": {}}\n'
    (folder / orphan).write_bytes(kept)

    resp = await client.post(
        "/api/v1/gold-sets",
        json={"gold_set_id": GOLD, "task_schema_id": "sentiment-demo-v1"},
        headers=_as(tokens[0]),
    )

    assert resp.status_code == 409, resp.text
    error = resp.json()["error"]
    assert error["code"] == "GOLD_SET_FILES_EXIST"
    assert error["details"]["files"] == [f"gold/{GOLD}/{orphan}"]
    assert (folder / orphan).read_bytes() == kept
    assert [p.name for p in folder.iterdir()] == [orphan]
    listed = await client.get("/api/v1/gold-sets", headers=_as(tokens[0]))
    assert listed.json()["items"] == []


@pytest.mark.asyncio
async def test_create_writes_into_an_empty_folder(client, app, tmp_path):
    _, tokens, _ = await _start_review(client, app, tmp_path)
    (tmp_path / "gold" / GOLD).mkdir(parents=True)

    await _create(client, tokens[0])

    assert _header(tmp_path)["version"] == 1


@pytest.mark.asyncio
async def test_promotion_writes_adjudicated_and_agreed_records_with_provenance(
    client, app, tmp_path
):
    _, tokens, queue_id, resolution = await _reviewed_and_adjudicated(
        client, app, tmp_path
    )
    await _create(client, tokens[0])
    before = _sha256(_items_path(tmp_path))

    report = await _promote(client, tokens[0], {"queue_id": queue_id})

    assert report["written"] is True
    assert report["counts"] == {
        "added": 6,
        "duplicates": 0,
        "conflicts": 0,
        "skipped": 0,
    }
    items = {
        item["input_ref"]["external_id"]: item for item in _lines(_items_path(tmp_path))
    }
    assert sorted(items) == ["r1", "r2", "r3", "r4", "r5", "r6"]
    expected = {**OFFLINE_SENTIMENT, "r3": "negative"}
    assert {k: v["expected"] for k, v in items.items()} == {
        k: {"sentiment": v} for k, v in expected.items()
    }

    first, second = _reviewer_ids(app)
    r3 = items["r3"]["provenance"]
    assert r3["source"] == "adjudication"
    assert (
        r3["adjudication"]["adjudication_id"]
        == resolution["resolution"]["adjudication_id"]
    )
    assert r3["adjudication"]["adjudicator_id"] == first
    assert sorted(r3["reviewer_ids"]) == sorted([first, second])
    assert len(r3["reviews"]) == 2
    assert r3["queue_id"] == queue_id
    assert r3["promoted_by"] == first

    r1 = items["r1"]["provenance"]
    assert r1["source"] == "reviewer_agreement"
    assert r1["adjudication"] is None
    assert r1["ai_revealed"] is True
    assert r1["accepted_ai_proposal"] is True
    assert items["r1"]["input"] == {"text": "A positive review."}
    assert items["r1"]["input_ref"]["dataset"]

    header = _header(tmp_path)
    assert (header["version"], header["item_count"]) == (2, 6)
    assert header["previous_hash"] == before
    assert header["content_hash"] == _sha256(_items_path(tmp_path))
    assert [s["queue_id"] for s in header["sources"]] == [queue_id]
    assert header["sources"][0]["workflow_execution_id"]


@pytest.mark.asyncio
async def test_promoting_the_same_records_again_changes_no_file(client, app, tmp_path):
    _, tokens, queue_id, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])
    await _promote(client, tokens[0], {"queue_id": queue_id})
    items = _items_path(tmp_path).read_bytes()
    header = (tmp_path / "gold" / GOLD / "gold.yaml").read_bytes()

    again = await _promote(client, tokens[1], {"queue_id": queue_id})

    assert again["written"] is False
    assert again["counts"]["added"] == 0
    assert again["counts"]["duplicates"] == 6
    assert again["gold_set"]["version"] == 2
    assert _items_path(tmp_path).read_bytes() == items
    assert (tmp_path / "gold" / GOLD / "gold.yaml").read_bytes() == header


async def _correct(client, app, queue_id, token, external_id, labels):
    tasks = await client.get(f"/api/v1/queues/{queue_id}/my-tasks", headers=_as(token))
    record_id = _external_ids(app)[external_id]
    (task,) = [t for t in tasks.json()["items"] if t["record_id"] == record_id]
    corrected = await client.post(
        f"/api/v1/review-tasks/{task['task_id']}/correct",
        json={"labels": labels, "decision": "edit"},
        headers=_as(token),
    )
    assert corrected.status_code == 200, corrected.text


@pytest.mark.asyncio
async def test_new_labels_for_a_promoted_input_are_a_conflict_that_keeps_gold(
    client, app, tmp_path
):
    _, tokens, queue_id, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])
    await _promote(client, tokens[0], {"queue_id": queue_id})
    items = _items_path(tmp_path).read_bytes()
    for token in tokens:
        await _correct(client, app, queue_id, token, "r1", {"sentiment": "neutral"})

    report = await _promote(client, tokens[0], {"queue_id": queue_id})

    assert report["written"] is False
    assert report["counts"]["conflicts"] == 1
    (conflict,) = report["conflicts"]
    assert conflict["fields"] == ["sentiment"]
    assert conflict["gold"]["expected"] == {"sentiment": "positive"}
    assert conflict["other"]["expected"] == {"sentiment": "neutral"}
    assert conflict["gold"]["input_ref"]["external_id"] == "r1"
    assert _items_path(tmp_path).read_bytes() == items


@pytest.mark.asyncio
async def test_a_record_with_open_copies_or_an_unresolved_disagreement_waits(
    client, app, tmp_path
):
    _, tokens, queue = await _start_review(client, app, tmp_path)
    queue_id = queue["queue_id"]
    await _review_all(client, queue_id, tokens[0], FIRST_REVIEWER)
    await _create(client, tokens[0])

    early = await _promote(client, tokens[0], {"queue_id": queue_id})
    assert {s["reason"] for s in early["skipped"]} == {"open_copies"}
    assert early["counts"]["added"] == 0

    await _review_all(client, queue_id, tokens[1], OFFLINE_SENTIMENT)
    later = await _promote(client, tokens[0], {"queue_id": queue_id})
    assert later["counts"]["added"] == 5
    assert [(s["external_id"], s["reason"]) for s in later["skipped"]] == [
        ("r3", "unresolved_disagreement")
    ]


@pytest.mark.asyncio
async def test_one_reviewers_labels_need_the_opt_in_and_say_so(client, app, tmp_path):
    _, tokens, queue = await _start_review(
        client, app, tmp_path, reviewers=1, overlap=1
    )
    queue_id = queue["queue_id"]
    await _review_all(client, queue_id, tokens[0], OFFLINE_SENTIMENT)
    await _create(client, tokens[0])

    default = await _promote(client, tokens[0], {"queue_id": queue_id})
    assert default["counts"]["added"] == 0
    assert {s["reason"] for s in default["skipped"]} == {"single_reviewer"}

    opted = await _promote(
        client, tokens[0], {"queue_id": queue_id, "allow_single_reviewer": True}
    )
    assert opted["counts"]["added"] == 6
    sources = {i["provenance"]["source"] for i in _lines(_items_path(tmp_path))}
    assert sources == {"single_reviewer"}


@pytest.mark.asyncio
async def test_promoting_named_records_promotes_only_those(client, app, tmp_path):
    _, tokens, queue_id, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])
    r3 = _external_ids(app)["r3"]

    report = await _promote(
        client, tokens[0], {"queue_id": queue_id, "record_ids": [r3]}
    )

    assert [i["input_ref"]["external_id"] for i in report["added"]] == ["r3"]
    unknown = await client.post(
        f"/api/v1/gold-sets/{GOLD}/promote",
        json={"queue_id": queue_id, "record_ids": [str(uuid.uuid4())]},
        headers=_as(tokens[0]),
    )
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_append_adds_only_what_the_model_got_wrong_and_dedupes(
    client, app, tmp_path
):
    _, tokens, queue_id, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])

    appended = await _promote(
        client, tokens[0], {"queue_id": queue_id}, action="append"
    )

    assert appended["counts"] == {
        "added": 1,
        "duplicates": 0,
        "conflicts": 0,
        "skipped": 5,
    }
    (item,) = _lines(_items_path(tmp_path))
    assert item["input_ref"]["external_id"] == "r3"
    failure = item["provenance"]["model_failure"]
    assert failure["proposed"]["sentiment"] == "neutral"
    assert failure["failed_fields"] == ["sentiment"]
    assert {s["reason"] for s in appended["skipped"]} == {"model_agreed"}

    again = await _promote(client, tokens[0], {"queue_id": queue_id}, action="append")
    assert (again["counts"]["added"], again["counts"]["duplicates"]) == (0, 1)
    assert again["written"] is False


@pytest.mark.asyncio
async def test_promotion_from_a_workflow_execution_reads_its_queues(
    client, app, tmp_path
):
    _, tokens, queue_id, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])
    execution_id = _header_source_execution(app, queue_id)

    report = await _promote(client, tokens[0], {"workflow_execution_id": execution_id})

    assert report["counts"]["added"] == 6
    assert _header(tmp_path)["sources"][0]["workflow_execution_id"] == execution_id


def _header_source_execution(app, queue_id) -> str:
    with app.state.engine.connect() as conn:
        return str(
            conn.execute(
                text(
                    "SELECT workflow_execution_id FROM workflow_step_executions "
                    "WHERE json_extract(result, '$.summary.queue_id') = :q"
                ),
                {"q": queue_id},
            ).scalar()
        )


@pytest.mark.asyncio
async def test_a_queue_of_another_task_schema_is_refused(client, app, tmp_path):
    workspace_id, tokens, queue_id, _ = await _reviewed_and_adjudicated(
        client, app, tmp_path
    )
    now = datetime.now(UTC).isoformat()
    with app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO task_schemas (id, task_schema_slug, version, task_type, "
                "title, instructions, label_fields, required_fields, "
                "optional_fields, blind_review_policy, supported_agent_roles, "
                "is_active, is_frozen, created_at, updated_at, workspace_id) "
                "VALUES (:id, 'topics', 1, 'classification', 'Topics', '', '[]', "
                "'[]', '[]', 'show_agent_outputs', '[]', 1, 0, :now, :now, :w)"
            ),
            {"id": str(uuid.uuid4()), "now": now, "w": workspace_id},
        )
    await _create(client, tokens[0], slug="topics-gold", schema="topics")

    resp = await client.post(
        "/api/v1/gold-sets/topics-gold/promote",
        json={"queue_id": queue_id},
        headers=_as(tokens[0]),
    )

    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "GOLD_TASK_SCHEMA_MISMATCH"
    assert error["details"]["queue_task_schema"] == "sentiment-demo-v1"
    assert _items_path(tmp_path, "topics-gold").read_bytes() == b""


@pytest.mark.asyncio
async def test_show_reports_repeats_and_conflicts_and_dedupe_removes_repeats(
    client, app, tmp_path
):
    _, tokens, queue_id, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])
    await _promote(client, tokens[0], {"queue_id": queue_id})
    path = _items_path(tmp_path)
    lines = path.read_text("utf-8").splitlines()
    conflicting = json.loads(lines[1])
    conflicting["expected"] = {"sentiment": "positive"}
    merged = [*lines, lines[0], json.dumps(conflicting)]
    path.write_bytes(("\n".join(merged) + "\n").encode("utf-8"))

    shown = await client.get(f"/api/v1/gold-sets/{GOLD}", headers=_as(tokens[0]))
    detail = shown.json()
    assert detail["content_hash_matches"] is False
    assert [d["item_id"] for d in detail["duplicates"]] == [
        json.loads(lines[0])["item_id"]
    ]
    assert [c["item_id"] for c in detail["conflicts"]] == [conflicting["item_id"]]

    deduped = await client.post(
        f"/api/v1/gold-sets/{GOLD}/dedupe", headers=_as(tokens[0])
    )
    body = deduped.json()
    assert body["written"] is True
    assert len(body["removed"]) == 1
    assert len(body["conflicts"]) == 1
    after = _lines(path)
    assert len(after) == 7
    assert [i["item_id"] for i in after].count(conflicting["item_id"]) == 2
    header = _header(tmp_path)
    assert header["version"] == 3
    assert header["content_hash"] == _sha256(path)

    again = await client.post(
        f"/api/v1/gold-sets/{GOLD}/dedupe", headers=_as(tokens[0])
    )
    assert again.json()["written"] is False
    assert _header(tmp_path)["version"] == 3


@pytest.mark.asyncio
async def test_export_gives_the_file_and_writes_it_inside_the_workspace(
    client, app, tmp_path
):
    _, tokens, queue_id, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])
    await _promote(client, tokens[0], {"queue_id": queue_id})
    data = _items_path(tmp_path).read_bytes()

    inline = await client.get(
        f"/api/v1/gold-sets/{GOLD}/export",
        params={"format": "jsonl"},
        headers=_as(tokens[0]),
    )
    assert inline.json()["content"].encode("utf-8") == data
    assert inline.json()["content_hash"] == _sha256(_items_path(tmp_path))

    written = await client.post(
        f"/api/v1/gold-sets/{GOLD}/export",
        json={"path": "exports/gold-v2.jsonl"},
        headers=_as(tokens[0]),
    )
    assert written.status_code == 200, written.text
    assert written.json()["path"] == "exports/gold-v2.jsonl"
    assert (tmp_path / "exports" / "gold-v2.jsonl").read_bytes() == data

    exists = await client.post(
        f"/api/v1/gold-sets/{GOLD}/export",
        json={"path": "exports/gold-v2.jsonl"},
        headers=_as(tokens[0]),
    )
    assert exists.json()["error"]["code"] == "EXPORT_PATH_EXISTS"
    outside = await client.post(
        f"/api/v1/gold-sets/{GOLD}/export",
        json={"path": "../gold.jsonl"},
        headers=_as(tokens[0]),
    )
    assert outside.status_code == 400
    assert outside.json()["error"]["code"] == "PATH_TRAVERSAL"


def _outsider(app, tmp_path):
    """A session for a reviewer of another workspace, with its own folder."""
    workspace_id = uuid.uuid4()
    root = tmp_path / "other"
    root.mkdir()
    now = datetime.now(UTC).isoformat()
    with app.state.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, workspace_name, workspace_slug, "
                "core_version, root_path, manifest_path, created_at, updated_at) "
                "VALUES (:id, 'Other', 'other', '0.1.0', :root, :manifest, "
                ":now, :now)"
            ),
            {
                "id": str(workspace_id),
                "root": str(root),
                "manifest": str(root / "workbench.project.yaml"),
                "now": now,
            },
        )
    _seed_task_schema(app.state.engine, workspace_id)
    return _seed_reviewer(app.state.engine, workspace_id)


@pytest.mark.asyncio
async def test_another_workspace_sees_and_touches_none_of_it(client, app, tmp_path):
    _, tokens, queue_id, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])
    await _promote(client, tokens[0], {"queue_id": queue_id})
    items = _items_path(tmp_path).read_bytes()
    outsider = _outsider(app, tmp_path)
    execution_id = _header_source_execution(app, queue_id)

    listed = await client.get("/api/v1/gold-sets", headers=_as(outsider))
    assert listed.json()["items"] == []
    for method, path, body in [
        ("GET", f"/api/v1/gold-sets/{GOLD}", None),
        ("POST", f"/api/v1/gold-sets/{GOLD}/promote", {"queue_id": queue_id}),
        ("POST", f"/api/v1/gold-sets/{GOLD}/append", {"queue_id": queue_id}),
        ("POST", f"/api/v1/gold-sets/{GOLD}/dedupe", None),
        ("GET", f"/api/v1/gold-sets/{GOLD}/export", None),
        ("POST", f"/api/v1/gold-sets/{GOLD}/export", {"path": "x.jsonl"}),
    ]:
        resp = await client.request(method, path, json=body, headers=_as(outsider))
        assert resp.status_code == 404, (path, resp.text)
        assert resp.json()["error"]["code"] == "GOLD_SET_NOT_FOUND"

    await _create(client, outsider)
    for body in ({"queue_id": queue_id}, {"workflow_execution_id": execution_id}):
        resp = await client.post(
            f"/api/v1/gold-sets/{GOLD}/promote", json=body, headers=_as(outsider)
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "NOT_FOUND"
    assert _items_path(tmp_path).read_bytes() == items
    assert _items_path(tmp_path / "other").read_bytes() == b""


PROMOTE_AND_DIE_AT_HEADER = """
import os, sys, uuid
from molabel.app.services.gold_sets import promote_to_gold
from molabel.core.database import get_engine

replace = os.replace
def replace_or_die(src, dst):
    if os.path.basename(dst) == "gold.yaml":
        os._exit(17)
    replace(src, dst)
os.replace = replace_or_die
db, workspace_id, slug, reviewer_id, queue_id = sys.argv[1:]
promote_to_gold(get_engine(db), uuid.UUID(workspace_id), slug,
                promoted_by=uuid.UUID(reviewer_id), queue_ids=[queue_id])
"""


@pytest.mark.asyncio
async def test_a_write_killed_between_the_files_is_reported_by_every_read(
    client, app, tmp_path
):
    workspace_id, tokens, queue_id, _ = await _reviewed_and_adjudicated(
        client, app, tmp_path
    )
    await _create(client, tokens[0])
    header_before = (tmp_path / "gold" / GOLD / "gold.yaml").read_bytes()

    killed = subprocess.run(
        [
            sys.executable,
            "-c",
            PROMOTE_AND_DIE_AT_HEADER,
            str(tmp_path / "review-gui.db"),
            str(workspace_id),
            GOLD,
            _reviewer_ids(app)[0],
            queue_id,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert killed.returncode == 17, killed.stderr
    assert len(_lines(_items_path(tmp_path))) == 6
    assert (tmp_path / "gold" / GOLD / "gold.yaml").read_bytes() == header_before
    headers = _as(tokens[0])
    listed = (await client.get("/api/v1/gold-sets", headers=headers)).json()
    shown = (await client.get(f"/api/v1/gold-sets/{GOLD}", headers=headers)).json()
    exported = await client.get(f"/api/v1/gold-sets/{GOLD}/export", headers=headers)
    retried = await _promote(client, tokens[0], {"queue_id": queue_id})
    assert listed["items"][0]["content_hash_matches"] is False
    assert shown["content_hash_matches"] is False
    assert exported.json()["content_hash_matches"] is False
    assert retried["written"] is False
    assert retried["gold_set"]["content_hash_matches"] is False


@pytest.mark.asyncio
async def test_a_promotion_that_adds_nothing_leaves_a_hand_edited_file_alone(
    client, app, tmp_path
):
    _, tokens, queue_id, _ = await _reviewed_and_adjudicated(client, app, tmp_path)
    await _create(client, tokens[0])
    await _promote(client, tokens[0], {"queue_id": queue_id})
    path = _items_path(tmp_path)
    lines = path.read_text("utf-8").splitlines()
    edited = json.loads(lines[1])
    edited["expected"] = {"sentiment": "positive"}
    path.write_bytes(
        ("\n".join([lines[0], json.dumps(edited), *lines[2:]]) + "\n").encode()
    )
    hand_edited = path.read_bytes()

    report = await _promote(client, tokens[0], {"queue_id": queue_id})

    assert report["written"] is False
    assert report["counts"]["conflicts"] == 1
    assert path.read_bytes() == hand_edited
    assert _header(tmp_path)["version"] == 2
