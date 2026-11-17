"""Gold sets: released labels kept as files in the workspace.

A set is ``gold/<slug>/gold.yaml``, the header, and ``gold/<slug>/gold.jsonl``,
one item per line. ``docs/architecture/gold-sets.md`` gives the rules this
module implements: the item shape and its hashes, the version rule, and what a
duplicate and a conflict are.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

GOLD_DIRECTORY = "gold"
HEADER_FILENAME = "gold.yaml"
ITEMS_FILENAME = "gold.jsonl"
FORMAT_VERSION = 1

_ITEM_NAMESPACE = uuid.UUID("9b1c4d57-3f0e-5a8e-9c61-6d2f7a40b8e3")

_LINE_SEPARATOR_ESCAPES = {"\x85": "\\u0085", "\u2028": "\\u2028", "\u2029": "\\u2029"}
"""Characters that ``ensure_ascii=False`` writes raw and editors break lines on.

JSON allows them only inside strings, so escaping them there keeps one item
per line for every tool that reads the file.
"""


class GoldFileError(ValueError):
    """A gold file that does not parse, with the 1-based line it failed on."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message if line is None else f"line {line}: {message}")
        self.line = line


def _sorted_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sorted_keys(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted_keys(item) for item in value]
    return value


def _normalized(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n")).strip()
    if isinstance(value, dict):
        return {key: _normalized(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    return value


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def file_hash(data: bytes) -> str:
    """The content hash of a gold file, the same whatever line ends git wrote."""
    digest = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
    return f"sha256:{digest}"


def expected_labels(labels: dict[str, Any]) -> dict[str, Any]:
    """*labels* as an item stores them: null fields dropped, keys sorted."""
    return _sorted_keys({k: v for k, v in labels.items() if v is not None})


class GoldSource(StrEnum):
    """What the expected labels of an item rest on."""

    adjudication = "adjudication"
    reviewer_agreement = "reviewer_agreement"
    single_reviewer = "single_reviewer"


class GoldModel(BaseModel):
    """A gold-file mapping that keeps the keys it does not declare."""

    model_config = ConfigDict(extra="allow")


class GoldInputRef(GoldModel):
    """Where the input came from in the review database."""

    dataset: str | None = None
    external_id: str | None = None
    record_id: str | None = None


class GoldReview(GoldModel):
    """A counted human review event the expected labels rest on."""

    review_event_id: str
    reviewer_id: str
    decision: str | None = None
    ai_revealed: bool = False


class GoldAdjudication(GoldModel):
    """The adjudication that settled the expected labels."""

    adjudication_id: str
    adjudicator_id: str
    review_event_id: str | None = None
    ai_revealed: bool = False


class GoldModelFailure(GoldModel):
    """An agent proposal that the expected labels contradict."""

    agent_output_id: str
    agent_run_id: str
    proposed: dict[str, Any]
    failed_fields: list[str]


class GoldProvenance(GoldModel):
    """Where an item's expected labels came from, and who promoted it."""

    source: GoldSource
    queue_id: str
    workflow_execution_id: str | None = None
    adjudication: GoldAdjudication | None = None
    reviews: list[GoldReview] = Field(default_factory=list)
    reviewer_ids: list[str] = Field(default_factory=list)
    ai_revealed: bool = Field(
        description="An AI proposal was shown to a human the label rests on"
    )
    accepted_ai_proposal: bool = Field(
        description="A counted reviewer accepted an AI proposal they were shown"
    )
    model_failure: GoldModelFailure | None = None
    promoted_at: str
    promoted_by: str


class GoldItem(GoldModel):
    """One gold item. ``item_id`` and both hashes are derived from its content."""

    item_id: str
    input_ref: GoldInputRef
    input: dict[str, Any]
    input_hash: str
    expected: dict[str, Any]
    content_hash: str
    provenance: GoldProvenance

    @classmethod
    def build(
        cls,
        *,
        task_schema: str,
        input: dict[str, Any],
        expected: dict[str, Any],
        input_ref: GoldInputRef,
        provenance: GoldProvenance,
        extra: dict[str, Any] | None = None,
    ) -> Self:
        """The item for this content, with its id and hashes computed."""
        expected = expected_labels(expected)
        input_hash = _sha256(_normalized(input))
        return cls.model_validate(
            {
                "item_id": str(
                    uuid.uuid5(_ITEM_NAMESPACE, f"{task_schema}\n{input_hash}")
                ),
                "input_ref": input_ref,
                "input": _sorted_keys(input),
                "input_hash": input_hash,
                "expected": expected,
                "content_hash": _sha256(
                    {"input_hash": input_hash, "expected": expected}
                ),
                "provenance": provenance,
                **(extra or {}),
            }
        )

    @classmethod
    def parse(cls, task_schema: str, document: Any) -> Self:
        """Read an item from a line of a gold file, recomputing its id and hashes."""
        if not isinstance(document, dict):
            raise ValueError("an item must be a JSON object")
        for key in ("input", "expected"):
            if not isinstance(document.get(key), dict):
                raise ValueError(f"an item needs an object '{key}'")
        declared = set(cls.model_fields)
        return cls.build(
            task_schema=task_schema,
            input=document["input"],
            expected=document["expected"],
            input_ref=GoldInputRef.model_validate(document.get("input_ref") or {}),
            provenance=GoldProvenance.model_validate(document.get("provenance")),
            extra={k: v for k, v in document.items() if k not in declared},
        )

    def line(self) -> str:
        line = json.dumps(self.model_dump(mode="json"), ensure_ascii=False)
        for separator, escape in _LINE_SEPARATOR_ESCAPES.items():
            line = line.replace(separator, escape)
        return line


def render_items(items: Iterable[GoldItem]) -> bytes:
    """``gold.jsonl``: one item per line, LF line ends, in the order given."""
    return "".join(f"{item.line()}\n" for item in items).encode("utf-8")


def parse_items(task_schema: str, data: bytes) -> tuple[GoldItem, ...]:
    """The items of a ``gold.jsonl`` file. Blank lines are allowed.

    Lines end at LF alone; the CR of a CRLF end is JSON whitespace.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GoldFileError(f"not UTF-8: {exc}") from exc
    items: list[GoldItem] = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            items.append(GoldItem.parse(task_schema, json.loads(line)))
        except ValueError as exc:
            raise GoldFileError(str(exc), number) from exc
    return tuple(items)


class GoldSetSource(GoldModel):
    """A queue a set took items from."""

    queue_id: str
    workflow_execution_id: str | None = None
    workflow: str | None = None


class GoldSetHeader(GoldModel):
    """``gold.yaml``: what the set is, and which version of its items it holds."""

    gold_set_id: str
    name: str
    task_schema: str
    format_version: int = FORMAT_VERSION
    version: int
    item_count: int
    content_hash: str
    previous_hash: str | None = None
    sources: list[GoldSetSource] = Field(default_factory=list)
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class GoldSet:
    """A set as read: its header, its items, and the hash of its items file."""

    header: GoldSetHeader
    items: tuple[GoldItem, ...]
    file_hash: str

    @classmethod
    def new(cls, *, slug: str, name: str, task_schema: str, now: str) -> Self:
        data = render_items(())
        header = GoldSetHeader(
            gold_set_id=slug,
            name=name,
            task_schema=task_schema,
            version=1,
            item_count=0,
            content_hash=file_hash(data),
            created_at=now,
            updated_at=now,
        )
        return cls(header=header, items=(), file_hash=file_hash(data))

    @property
    def content_hash_matches(self) -> bool:
        """Whether the items file is the one MoLabel last wrote."""
        return self.header.content_hash == self.file_hash

    def revised(
        self,
        items: Sequence[GoldItem],
        *,
        now: str,
        sources: Sequence[GoldSetSource] = (),
    ) -> Self | None:
        """The next version holding *items*, or None if the file would not change.

        It also lists *sources* the header does not list yet.
        """
        data = render_items(items)
        if file_hash(data) == self.file_hash:
            return None
        listed = [*self.header.sources]
        for source in sources:
            if all(s.queue_id != source.queue_id for s in listed):
                listed.append(source)
        header = self.header.model_copy(
            update={
                "version": self.header.version + 1,
                "item_count": len(items),
                "content_hash": file_hash(data),
                "previous_hash": self.file_hash,
                "sources": listed,
                "updated_at": now,
            }
        )
        return type(self)(header=header, items=tuple(items), file_hash=file_hash(data))


class GoldItemRef(BaseModel):
    """An item named by its id and where its input came from."""

    item_id: str
    input_ref: GoldInputRef


class GoldConflict(BaseModel):
    """Two items with the same input and different expected labels."""

    item_id: str
    fields: list[str] = Field(description="The fields whose labels differ")
    gold: GoldItem = Field(description="The item the set holds, which is kept")
    other: GoldItem = Field(description="The item with the other labels")


def _conflict(gold: GoldItem, other: GoldItem) -> GoldConflict:
    fields = sorted(
        name
        for name in gold.expected.keys() | other.expected.keys()
        if gold.expected.get(name) != other.expected.get(name)
    )
    return GoldConflict(item_id=gold.item_id, fields=fields, gold=gold, other=other)


def _ref(item: GoldItem) -> GoldItemRef:
    return GoldItemRef(item_id=item.item_id, input_ref=item.input_ref)


@dataclass(frozen=True)
class Merged:
    """The items after adding candidates, and what happened to each candidate."""

    items: tuple[GoldItem, ...]
    added: tuple[GoldItem, ...]
    duplicates: tuple[GoldItemRef, ...]
    conflicts: tuple[GoldConflict, ...]


def merge(items: Sequence[GoldItem], candidates: Iterable[GoldItem]) -> Merged:
    """Append each candidate whose input is new; report the rest.

    A candidate with an input the set holds is a duplicate when its labels
    match and a conflict when they differ. Neither changes the set.
    """
    held = {item.item_id: item for item in items}
    added: list[GoldItem] = []
    duplicates: list[GoldItemRef] = []
    conflicts: list[GoldConflict] = []
    for candidate in candidates:
        existing = held.get(candidate.item_id)
        if existing is None:
            held[candidate.item_id] = candidate
            added.append(candidate)
        elif existing.content_hash == candidate.content_hash:
            duplicates.append(_ref(candidate))
        else:
            conflicts.append(_conflict(existing, candidate))
    return Merged(
        items=(*items, *added),
        added=tuple(added),
        duplicates=tuple(duplicates),
        conflicts=tuple(conflicts),
    )


@dataclass(frozen=True)
class Deduped:
    """A set's items with repeats removed, and the conflicts left in it."""

    items: tuple[GoldItem, ...]
    removed: tuple[GoldItemRef, ...]
    conflicts: tuple[GoldConflict, ...]


def dedupe(items: Sequence[GoldItem]) -> Deduped:
    """Drop each item that repeats an earlier one's input and labels.

    Items with the same input and different labels are conflicts. Both stay,
    for a person to settle.
    """
    first: dict[str, GoldItem] = {}
    seen: set[tuple[str, str]] = set()
    kept: list[GoldItem] = []
    removed: list[GoldItemRef] = []
    conflicts: list[GoldConflict] = []
    for item in items:
        key = (item.item_id, item.content_hash)
        if key in seen:
            removed.append(_ref(item))
            continue
        seen.add(key)
        kept.append(item)
        if item.item_id in first:
            conflicts.append(_conflict(first[item.item_id], item))
        else:
            first[item.item_id] = item
    return Deduped(
        items=tuple(kept), removed=tuple(removed), conflicts=tuple(conflicts)
    )
