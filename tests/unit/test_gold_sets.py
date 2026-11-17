"""Gold-set files, merge and dedupe, promotion rules, and calibration scoring."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from molabel.core.gold.calibration import score_against_gold
from molabel.core.gold.model import (
    GoldFileError,
    GoldInputRef,
    GoldItem,
    GoldProvenance,
    GoldSet,
    GoldSetSource,
    GoldSource,
    dedupe,
    file_hash,
    merge,
    parse_items,
    render_items,
)
from molabel.core.gold.promotion import (
    CountedReview,
    Proposal,
    Resolution,
    ReviewedRecord,
    Skipped,
    SkipReason,
    gold_candidate,
)
from molabel.core.quality.review_agreement import ReviewEventLabels
from molabel.core.types import AdjudicationResolution

SCHEMA = "ticket-triage"
NOW = "2026-11-17T00:00:00+00:00"


def provenance(**overrides) -> GoldProvenance:
    return GoldProvenance.model_validate(
        {
            "source": "reviewer_agreement",
            "queue_id": "q1",
            "ai_revealed": False,
            "accepted_ai_proposal": False,
            "promoted_at": NOW,
            "promoted_by": "lead",
            **overrides,
        }
    )


def item(text: str, intent: str, record: str = "r1") -> GoldItem:
    return GoldItem.build(
        task_schema=SCHEMA,
        input={"text": text},
        expected={"intent": intent},
        input_ref=GoldInputRef(dataset="tickets", external_id=record, record_id=record),
        provenance=provenance(),
    )


class TestItemFile:
    def test_the_same_content_renders_the_same_bytes_whatever_its_key_order(self):
        first = GoldItem.build(
            task_schema=SCHEMA,
            input={"text": "refund me", "channel": "email"},
            expected={"urgent": False, "intent": "refund"},
            input_ref=GoldInputRef(record_id="r1"),
            provenance=provenance(),
        )
        second = GoldItem.build(
            task_schema=SCHEMA,
            input={"channel": "email", "text": "refund me"},
            expected={"intent": "refund", "urgent": False},
            input_ref=GoldInputRef(record_id="r1"),
            provenance=provenance(),
        )

        assert render_items([first]) == render_items([second])
        line = render_items([first]).decode("utf-8")
        assert line.endswith("}\n") and "\r" not in line
        assert list(json.loads(line)) == [
            "item_id",
            "input_ref",
            "input",
            "input_hash",
            "expected",
            "content_hash",
            "provenance",
        ]
        assert str(uuid.UUID(first.item_id)) == first.item_id

    def test_the_item_id_depends_on_the_input_and_schema_alone(self):
        assert item("refund me", "refund").item_id == item("refund me", "bug").item_id
        assert item("refund me", "refund").item_id != item("ship it", "refund").item_id
        other_schema = GoldItem.build(
            task_schema="other-schema",
            input={"text": "refund me"},
            expected={"intent": "refund"},
            input_ref=GoldInputRef(),
            provenance=provenance(),
        )
        assert other_schema.item_id != item("refund me", "refund").item_id

    def test_null_labels_are_dropped_from_expected(self):
        built = GoldItem.build(
            task_schema=SCHEMA,
            input={"text": "x"},
            expected={"intent": "bug", "note": None},
            input_ref=GoldInputRef(),
            provenance=provenance(),
        )
        assert built.expected == {"intent": "bug"}
        assert built.content_hash == item("x", "bug").content_hash

    def test_reading_a_hand_edited_line_recomputes_its_hashes(self):
        original = item("refund me", "refund")
        edited = json.loads(original.line())
        edited["expected"] = {"intent": "other"}
        edited["note"] = "checked by the lead"

        (parsed,) = parse_items(SCHEMA, (json.dumps(edited) + "\n").encode())

        assert parsed.content_hash == item("refund me", "other").content_hash
        assert parsed.item_id == original.item_id
        assert json.loads(parsed.line())["note"] == "checked by the lead"

    def test_a_line_that_does_not_parse_names_its_line(self):
        data = render_items([item("a", "bug")]) + b"\n{not json\n"
        with pytest.raises(GoldFileError) as raised:
            parse_items(SCHEMA, data)
        assert raised.value.line == 3

    def test_the_file_hash_ignores_crlf_line_ends(self):
        data = render_items([item("a", "bug"), item("b", "refund")])
        assert file_hash(data.replace(b"\n", b"\r\n")) == file_hash(data)

    @pytest.mark.parametrize("separator", ["\x85", "\u2028", "\u2029"])
    def test_a_unicode_line_separator_in_content_survives_write_and_read(
        self, separator
    ):
        odd = GoldItem.build(
            task_schema=SCHEMA,
            input={"text": f"first{separator}second"},
            expected={"intent": f"re{separator}fund"},
            input_ref=GoldInputRef(record_id="r1"),
            provenance=provenance(),
        )
        items = (odd, item("b", "bug", record="r2"))

        data = render_items(items)

        assert len(data.decode("utf-8").splitlines()) == 2
        assert parse_items(SCHEMA, data) == items
        written_raw = "".join(
            json.dumps(i.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for i in items
        ).encode("utf-8")
        assert separator.encode("utf-8") in written_raw
        assert parse_items(SCHEMA, written_raw) == items

    def test_a_file_with_crlf_line_ends_reads_as_its_lf_form(self):
        items = (item("a", "bug"), item("b", "refund", record="r2"))
        data = render_items(items)

        assert parse_items(SCHEMA, data.replace(b"\n", b"\r\n")) == items


class TestMerge:
    def test_a_new_input_is_appended_after_the_items_the_set_holds(self):
        held = item("refund me", "refund")
        new = item("ship it", "shipping", record="r2")

        merged = merge([held], [new])

        assert merged.items == (held, new)
        assert merged.added == (new,)
        assert merged.duplicates == () and merged.conflicts == ()

    def test_the_same_input_and_labels_is_a_duplicate_and_changes_nothing(self):
        held = item("refund me", "refund")
        again = item("  refund me\r\n", "refund", record="r9")

        merged = merge([held], [again])

        assert merged.items == (held,)
        assert merged.added == ()
        assert [d.input_ref.record_id for d in merged.duplicates] == ["r9"]

    def test_the_same_input_with_other_labels_is_a_conflict_and_keeps_the_gold(self):
        held = item("refund me", "refund")
        other = item("refund me", "other", record="r2")

        merged = merge([held], [other])

        assert merged.items == (held,)
        (conflict,) = merged.conflicts
        assert conflict.fields == ["intent"]
        assert conflict.gold.expected == {"intent": "refund"}
        assert conflict.other.expected == {"intent": "other"}

    def test_two_candidates_with_one_input_meet_each_other_in_one_batch(self):
        merged = merge([], [item("a", "bug"), item("a", "bug"), item("a", "refund")])
        assert len(merged.added) == 1
        assert len(merged.duplicates) == 1
        assert len(merged.conflicts) == 1


class TestVersions:
    def test_create_writes_version_one_with_no_items(self):
        gold = GoldSet.new(slug="g", name="G", task_schema=SCHEMA, now=NOW)
        assert gold.header.version == 1
        assert gold.header.item_count == 0
        assert gold.header.content_hash == file_hash(b"")
        assert gold.header.previous_hash is None

    def test_a_write_that_changes_the_items_bumps_the_version(self):
        gold = GoldSet.new(slug="g", name="G", task_schema=SCHEMA, now=NOW)
        source = GoldSetSource(queue_id="q1", workflow_execution_id="e1")

        revised = gold.appended([item("a", "bug")], now="later", sources=[source])

        assert revised is not None
        assert revised.header.version == 2
        assert revised.header.item_count == 1
        assert revised.header.previous_hash == file_hash(b"")
        assert revised.header.content_hash == file_hash(
            render_items([item("a", "bug")])
        )
        assert revised.header.sources == [source]
        assert revised.header.updated_at == "later"

    def test_a_write_that_leaves_the_file_as_it_is_changes_nothing(self):
        gold = GoldSet.new(slug="g", name="G", task_schema=SCHEMA, now=NOW)
        once = gold.appended([item("a", "bug")], now=NOW)
        assert once is not None
        assert once.revised(list(once.items), now="later") is None
        assert once.appended([], now="later") is None

    def test_a_source_is_listed_once(self):
        gold = GoldSet.new(slug="g", name="G", task_schema=SCHEMA, now=NOW)
        source = GoldSetSource(queue_id="q1")
        v2 = gold.appended([item("a", "bug")], now=NOW, sources=[source])
        v3 = v2.appended([item("b", "bug")], now=NOW, sources=[source])
        assert [s.queue_id for s in v3.header.sources] == ["q1"]

    def test_an_append_keeps_every_earlier_byte_and_adds_lines_at_the_end(self):
        first = item("a", "bug")
        compacted = json.dumps(json.loads(first.line()), separators=(",", ":"))
        held = GoldSet(
            header=GoldSet.new(slug="g", name="G", task_schema=SCHEMA, now=NOW).header,
            items=(first,),
            data=compacted.encode(),
        )

        v2 = held.appended([item("b", "refund", record="r2")], now=NOW)

        assert v2.data == (
            compacted.encode() + b"\n" + render_items([item("b", "refund", "r2")])
        )
        assert v2.header.content_hash == file_hash(v2.data)
        assert v2.header.previous_hash == file_hash(compacted.encode())
        assert v2.header.item_count == 2


class TestDedupe:
    def test_exact_repeats_are_removed_and_the_first_is_kept(self):
        first = item("a", "bug", record="r1")
        repeat = item("a", "bug", record="r2")
        other = item("b", "refund", record="r3")

        deduped = dedupe([first, other, repeat])

        assert deduped.items == (first, other)
        assert [r.input_ref.record_id for r in deduped.removed] == ["r2"]
        assert deduped.conflicts == ()

    def test_conflicts_are_reported_and_both_items_stay(self):
        gold = item("a", "bug", record="r1")
        other = item("a", "refund", record="r2")

        deduped = dedupe([gold, other])

        assert deduped.items == (gold, other)
        assert deduped.removed == ()
        assert [(c.gold.expected, c.other.expected) for c in deduped.conflicts] == [
            ({"intent": "bug"}, {"intent": "refund"})
        ]


def review(
    reviewer: str,
    labels: dict | None,
    *,
    decision: str | None = "edit",
    ai_revealed: bool = False,
) -> CountedReview:
    return CountedReview(
        review_event_id=f"e-{reviewer}",
        reviewer_id=reviewer,
        decision=decision,
        ai_revealed=ai_revealed,
        labels=labels,
    )


def reviewed(
    *reviews: CountedReview,
    disagreement: bool = False,
    resolution: Resolution | None = None,
    open_copies: int = 0,
    proposals: tuple[Proposal, ...] = (),
) -> ReviewedRecord:
    return ReviewedRecord(
        input_ref=GoldInputRef(dataset="tickets", external_id="t4", record_id="r4"),
        input={"text": "Where is my money?"},
        queue_id="q1",
        workflow_execution_id="e1",
        open_copies=open_copies,
        reviews=reviews,
        disagreement=disagreement,
        resolution=resolution,
        proposals=proposals,
    )


def promote(record: ReviewedRecord, **options) -> GoldItem | Skipped:
    return gold_candidate(
        record, task_schema=SCHEMA, promoted_by="lead", promoted_at=NOW, **options
    )


def skip_reason(result: GoldItem | Skipped) -> SkipReason:
    assert isinstance(result, Skipped), result
    return result.reason


REFUND = {"intent": "refund", "urgent": False}
OTHER = {"intent": "other", "urgent": False}
RESOLVED = Resolution(
    adjudication_id="adj1",
    adjudicator_id="lead",
    resolution=AdjudicationResolution.resolve,
    labels=REFUND,
    review_event_id="e-adj",
    ai_revealed=True,
)


class TestPromotion:
    def test_an_adjudication_with_labels_gives_its_labels_and_provenance(self):
        result = promote(
            reviewed(
                review("a", REFUND, decision="accept", ai_revealed=True),
                review("b", OTHER),
                disagreement=True,
                resolution=RESOLVED,
            )
        )

        assert isinstance(result, GoldItem)
        assert result.expected == REFUND
        p = result.provenance
        assert p.source == GoldSource.adjudication
        assert p.adjudication.adjudication_id == "adj1"
        assert [r.review_event_id for r in p.reviews] == ["e-a", "e-b"]
        assert p.reviewer_ids == ["a", "b", "lead"]
        assert p.ai_revealed is True
        assert p.accepted_ai_proposal is True
        assert (p.queue_id, p.workflow_execution_id) == ("q1", "e1")
        assert (p.promoted_by, p.promoted_at) == ("lead", NOW)
        assert result.input_ref.external_id == "t4"

    @pytest.mark.parametrize(
        "resolution",
        [
            AdjudicationResolution.preserve_disagreement,
            AdjudicationResolution.downgrade,
            AdjudicationResolution.exclude,
        ],
    )
    def test_an_adjudication_that_kept_no_labels_is_skipped(self, resolution):
        kept = Resolution(**{**RESOLVED.__dict__, "resolution": resolution})
        record = reviewed(
            review("a", REFUND), review("b", OTHER), disagreement=True, resolution=kept
        )
        assert skip_reason(promote(record)) == SkipReason.resolved_without_labels

    def test_an_unresolved_disagreement_is_skipped(self):
        record = reviewed(review("a", REFUND), review("b", OTHER), disagreement=True)
        assert skip_reason(promote(record)) == SkipReason.unresolved_disagreement

    def test_reviewers_who_agree_give_their_labels(self):
        result = promote(reviewed(review("a", REFUND), review("b", dict(REFUND))))
        assert isinstance(result, GoldItem)
        assert result.provenance.source == GoldSource.reviewer_agreement
        assert result.provenance.ai_revealed is False
        assert result.provenance.accepted_ai_proposal is False

    def test_reviewers_who_set_different_fields_do_not_agree(self):
        record = reviewed(review("a", REFUND), review("b", {"intent": "refund"}))
        assert skip_reason(promote(record)) == SkipReason.partial_agreement

    def test_a_reviewer_who_rejected_without_labels_blocks_agreement(self):
        record = reviewed(review("a", REFUND), review("b", None, decision="reject"))
        assert skip_reason(promote(record)) == SkipReason.review_without_labels

    def test_one_reviewer_needs_the_opt_in_and_is_marked(self):
        record = reviewed(review("a", REFUND))
        assert skip_reason(promote(record)) == SkipReason.single_reviewer

        result = promote(record, allow_single_reviewer=True)
        assert isinstance(result, GoldItem)
        assert result.provenance.source == GoldSource.single_reviewer

    def test_a_record_with_an_open_copy_is_skipped(self):
        record = reviewed(review("a", REFUND), review("b", REFUND), open_copies=1)
        assert skip_reason(promote(record)) == SkipReason.open_copies

    def test_an_agent_proposal_alone_is_never_promoted(self):
        proposal = Proposal(agent_output_id="o1", agent_run_id="run", labels=REFUND)
        record = reviewed(proposals=(proposal,))
        assert skip_reason(promote(record, allow_single_reviewer=True)) == (
            SkipReason.no_human_label
        )

    @pytest.mark.parametrize(
        ("taken", "proposed", "took_ai"),
        [
            (("o1",), OTHER, True),
            ((), {"intent": "refund", "urgent": False, "note": ""}, True),
            ((), OTHER, False),
        ],
    )
    def test_an_adjudicator_who_took_the_ai_column_accepted_the_proposal(
        self, taken, proposed, took_ai
    ):
        resolution = Resolution(**{**RESOLVED.__dict__, "agent_output_ids": taken})
        proposal = Proposal(agent_output_id="o1", agent_run_id="run", labels=proposed)
        result = promote(
            reviewed(
                review("a", OTHER, ai_revealed=True),
                review("b", {"intent": "bug", "urgent": False}, ai_revealed=True),
                disagreement=True,
                resolution=resolution,
                proposals=(proposal,),
            )
        )

        assert isinstance(result, GoldItem)
        assert result.provenance.adjudicator_took_ai is took_ai
        assert result.provenance.accepted_ai_proposal is took_ai

    def test_accepting_a_hidden_proposal_is_not_accepting_a_shown_one(self):
        result = promote(
            reviewed(
                review("a", REFUND, decision="accept"),
                review("b", REFUND, decision="edit", ai_revealed=True),
            )
        )
        assert result.provenance.ai_revealed is True
        assert result.provenance.accepted_ai_proposal is False


class TestFailures:
    def test_a_human_label_that_contradicts_the_proposal_is_a_failure(self):
        proposal = Proposal(agent_output_id="o1", agent_run_id="run", labels=OTHER)
        record = reviewed(
            review("a", REFUND), review("b", REFUND), proposals=(proposal,)
        )

        result = promote(record, failures_only=True)

        assert isinstance(result, GoldItem)
        assert result.expected == REFUND
        failure = result.provenance.model_failure
        assert (failure.agent_output_id, failure.agent_run_id) == ("o1", "run")
        assert failure.proposed == OTHER
        assert failure.failed_fields == ["intent"]

    def test_a_proposal_the_humans_kept_is_not_a_failure(self):
        proposal = Proposal(
            agent_output_id="o1",
            agent_run_id="run",
            labels={**REFUND, "note": None, "tags": []},
        )
        record = reviewed(
            review("a", REFUND), review("b", REFUND), proposals=(proposal,)
        )
        assert (
            skip_reason(promote(record, failures_only=True)) == SkipReason.model_agreed
        )

    def test_a_record_with_no_proposal_is_not_a_failure(self):
        record = reviewed(review("a", REFUND), review("b", REFUND))
        assert skip_reason(promote(record, failures_only=True)) == (
            SkipReason.no_model_proposal
        )


def answer(reviewer: str, record: str, intent: str | None) -> ReviewEventLabels:
    return ReviewEventLabels(
        event_id=f"{reviewer}-{record}",
        record_id=record,
        reviewer_id=reviewer,
        decision="edit",
        labels={"note": "unsure"} if intent is None else {"intent": intent},
        supersedes_event_id=None,
        created_at=datetime(2026, 11, 17, tzinfo=UTC),
    )


class TestCalibration:
    def test_accuracy_and_kappa_against_gold(self):
        gold = {
            f"r{i}": item(f"text {i}", intent, record=f"r{i}")
            for i, intent in enumerate(["refund", "refund", "bug", "bug"])
        }
        events = [
            answer("rev", f"r{i}", intent)
            for i, intent in enumerate(["refund", "bug", "bug", "bug"])
        ]

        (score,) = score_against_gold(gold, events, ["intent"])

        # p_o = 3/4. Gold has refund 2, bug 2; the reviewer refund 1, bug 3,
        # so p_e = (2*1 + 2*3) / 16 = 1/2 and kappa = (3/4 - 1/2) / (1/2).
        field = score.fields["intent"]
        assert field.accuracy == pytest.approx(0.75)
        assert field.cohen_kappa == pytest.approx(0.5)
        assert field.compared == 4
        assert score.exact_match == pytest.approx(0.75)
        assert score.items_answered == 4

    def test_always_guessing_the_majority_label_scores_zero_kappa(self):
        intents = ["refund", "refund", "refund", "refund", "bug"]
        gold = {
            f"r{i}": item(f"text {i}", intent, record=f"r{i}")
            for i, intent in enumerate(intents)
        }
        events = [answer("rev", f"r{i}", "refund") for i in range(5)]

        (score,) = score_against_gold(gold, events, ["intent"])

        assert score.fields["intent"].accuracy == pytest.approx(0.8)
        assert score.fields["intent"].cohen_kappa == pytest.approx(0.0)

    def test_a_field_left_empty_is_missing_not_compared(self):
        gold = {"r0": item("a", "bug", record="r0"), "r1": item("b", "bug", "r1")}
        events = [answer("rev", "r0", "bug"), answer("rev", "r1", None)]

        (score,) = score_against_gold(gold, events, ["intent"])

        assert score.fields["intent"].compared == 1
        assert score.fields["intent"].missing == 1
        assert score.exact_match == pytest.approx(0.5)

    def test_answers_on_records_outside_the_gold_set_are_ignored(self):
        gold = {"r0": item("a", "bug", record="r0")}
        scores = score_against_gold(
            gold, [answer("rev", "elsewhere", "bug")], ["intent"]
        )
        assert scores == []
