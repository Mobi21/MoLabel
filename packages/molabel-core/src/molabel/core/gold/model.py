"""Gold sets: released labels kept as files in the workspace.

A set is ``gold/<slug>/gold.yaml``, the header, and ``gold/<slug>/gold.jsonl``,
one item per line. ``gold/<slug>/conflicts.jsonl`` keeps the open conflicts.
``docs/architecture/gold-sets.md`` gives the rules this module implements: the
item shape and its hashes, the version rule, and what a duplicate and a
conflict are.
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
CONFLICTS_FILENAME = "conflicts.jsonl"
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
        description=(
            "A counted reviewer accepted an AI proposal they were shown, or the "
            "adjudicator took one"
        )
    )
    adjudicator_took_ai: bool = Field(
        default=False,
        description=(
            "The adjudicator took an AI proposal's column, or resolved to labels "
            "equal to a proposal the adjudication screen showed"
        ),
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
        return _json_line(self)


def _json_line(model: BaseModel) -> str:
    line = json.dumps(model.model_dump(mode="json"), ensure_ascii=False)
    for separator, escape in _LINE_SEPARATOR_ESCAPES.items():
        line = line.replace(separator, escape)
    return line


def render_items(items: Iterable[GoldItem]) -> bytes:
    """``gold.jsonl``: one item per line, LF line ends, in the order given."""
    return "".join(f"{item.line()}\n" for item in items).encode("utf-8")


DERIVED_FIELDS = ("item_id", "input_hash", "content_hash")
"""The stored fields of an item that its content determines."""


@dataclass(frozen=True)
class StaleLine:
    """A line of ``gold.jsonl`` whose stored id or hashes disagree with its content."""

    line: int
    """1-based."""
    item: GoldItem
    """The line's item, with the id and hashes its content gives."""
    fields: tuple[str, ...]
    """The ``DERIVED_FIELDS`` the line stores wrong or leaves out."""


def _read_items(
    task_schema: str, data: bytes
) -> tuple[tuple[GoldItem, ...], tuple[StaleLine, ...]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GoldFileError(f"not UTF-8: {exc}") from exc
    items: list[GoldItem] = []
    stale: list[StaleLine] = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            document = json.loads(line)
            item = GoldItem.parse(task_schema, document)
        except ValueError as exc:
            raise GoldFileError(str(exc), number) from exc
        items.append(item)
        fields = tuple(f for f in DERIVED_FIELDS if document.get(f) != getattr(item, f))
        if fields:
            stale.append(StaleLine(line=number, item=item, fields=fields))
    return tuple(items), tuple(stale)


def parse_items(task_schema: str, data: bytes) -> tuple[GoldItem, ...]:
    """The items of a ``gold.jsonl`` file. Blank lines are allowed.

    Lines end at LF alone; the CR of a CRLF end is JSON whitespace.
    """
    return _read_items(task_schema, data)[0]


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
    """A set as read: its header, its items, and its items file's bytes."""

    header: GoldSetHeader
    items: tuple[GoldItem, ...]
    data: bytes
    """``gold.jsonl`` byte for byte, as read or as it is to be written."""
    stale: tuple[StaleLine, ...] = ()
    """The lines of *data* whose stored id or hashes disagree with their content."""

    @classmethod
    def read(cls, header: GoldSetHeader, data: bytes) -> Self:
        """The set these files hold. Raises ``GoldFileError`` on a bad line."""
        items, stale = _read_items(header.task_schema, data)
        return cls(header=header, items=items, data=data, stale=stale)

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
        return cls(header=header, items=(), data=data)

    @property
    def file_hash(self) -> str:
        return file_hash(self.data)

    @property
    def content_hash_matches(self) -> bool:
        """Whether the items file is the one MoLabel last wrote."""
        return self.header.content_hash == self.file_hash

    @property
    def items_consistent(self) -> bool:
        """Whether every line stores the id and hashes its content gives."""
        return not self.stale

    def appended(
        self,
        added: Sequence[GoldItem],
        *,
        now: str,
        sources: Sequence[GoldSetSource] = (),
    ) -> Self | None:
        """The next version with *added* as lines after the file's bytes.

        Every earlier line stays byte for byte, hand formatting included,
        except a stale line, which is rendered afresh so that no line stores an
        id or hash its content contradicts. It also lists *sources* the header
        does not list yet. None when there is nothing to add.
        """
        if not added:
            return None
        lines = self.data.split(b"\n")
        for stale in self.stale:
            lines[stale.line - 1] = stale.item.line().encode("utf-8")
        data = b"\n".join(lines)
        if data and not data.endswith(b"\n"):
            data += b"\n"
        return self._next(
            data + render_items(added), (*self.items, *added), now, sources
        )

    def revised(self, items: Sequence[GoldItem], *, now: str) -> Self | None:
        """The next version holding *items*, every line rendered afresh.

        None if the file would not change. Only an operation that changes
        existing items, such as dedupe, rewrites the whole file.
        """
        data = render_items(items)
        if file_hash(data) == self.file_hash:
            return None
        return self._next(data, items, now, ())

    def _next(
        self,
        data: bytes,
        items: Sequence[GoldItem],
        now: str,
        sources: Sequence[GoldSetSource],
    ) -> Self:
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
        return type(self)(header=header, items=tuple(items), data=data)


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


def _differing(first: dict[str, Any], second: dict[str, Any]) -> list[str]:
    return sorted(
        name
        for name in first.keys() | second.keys()
        if first.get(name) != second.get(name)
    )


def _conflict(gold: GoldItem, other: GoldItem) -> GoldConflict:
    fields = _differing(gold.expected, other.expected)
    return GoldConflict(item_id=gold.item_id, fields=fields, gold=gold, other=other)


class GoldOpenConflict(GoldModel):
    """A line of ``conflicts.jsonl``: labels for an input the set holds otherwise."""

    item_id: str
    input_hash: str
    input_ref: GoldInputRef = Field(
        description="The record the incoming labels are for"
    )
    fields: list[str] = Field(description="The fields whose labels differ")
    existing: dict[str, Any] = Field(description="The labels gold.jsonl holds")
    incoming: dict[str, Any] = Field(description="The labels that were not added")
    provenance: GoldProvenance = Field(
        description="Where the incoming labels came from"
    )
    detected_at: str

    @classmethod
    def of(cls, conflict: GoldConflict, *, detected_at: str) -> Self:
        other = conflict.other
        return cls(
            item_id=conflict.item_id,
            input_hash=conflict.gold.input_hash,
            input_ref=other.input_ref,
            fields=conflict.fields,
            existing=conflict.gold.expected,
            incoming=other.expected,
            provenance=other.provenance,
            detected_at=detected_at,
        )

    @property
    def key(self) -> tuple[str, str, str]:
        """What makes two lines the same conflict: item, incoming labels, source."""
        return (self.item_id, _sha256(self.incoming), self.provenance.source)


@dataclass(frozen=True)
class GoldConflictLog:
    """``conflicts.jsonl`` as read: each line's bytes and its conflict.

    The log is not gold. Writing it never changes ``gold.jsonl`` or the header.
    """

    lines: tuple[tuple[bytes, GoldOpenConflict], ...]
    data: bytes

    @classmethod
    def read(cls, data: bytes) -> Self:
        """The log these bytes hold. Raises ``GoldFileError`` on a bad line."""
        lines = []
        for number, raw in enumerate(data.split(b"\n"), start=1):
            raw = raw.rstrip(b"\r")
            if not raw.strip():
                continue
            try:
                conflict = GoldOpenConflict.model_validate(json.loads(raw))
            except ValueError as exc:
                raise GoldFileError(str(exc), number) from exc
            lines.append((raw, conflict))
        return cls(lines=tuple(lines), data=data)

    def _open(
        self, items: Sequence[GoldItem]
    ) -> Iterable[tuple[bytes, GoldOpenConflict]]:
        """The lines *items* still contradict, with ``existing`` as they hold it.

        A line whose item the set no longer holds, or holds with the incoming
        labels, is settled. A line whose item holds a third label set is
        rendered afresh with those labels.
        """
        held = {item.item_id: item for item in items}
        for raw, conflict in self.lines:
            item = held.get(conflict.item_id)
            if item is None or item.expected == conflict.incoming:
                continue
            if item.expected != conflict.existing:
                conflict = conflict.model_copy(
                    update={
                        "existing": item.expected,
                        "fields": _differing(item.expected, conflict.incoming),
                    }
                )
                raw = _json_line(conflict).encode("utf-8")
            yield raw, conflict

    def open(self, items: Sequence[GoldItem]) -> tuple[GoldOpenConflict, ...]:
        """The conflicts *items* have not settled, in the order they were found."""
        return tuple(conflict for _raw, conflict in self._open(items))

    def recorded(
        self, items: Sequence[GoldItem], conflicts: Iterable[GoldConflict], *, now: str
    ) -> Self:
        """The log without settled lines and with *conflicts* it lacks appended."""
        kept = list(self._open(items))
        seen = {conflict.key for _raw, conflict in kept}
        for found in conflicts:
            conflict = GoldOpenConflict.of(found, detected_at=now)
            if conflict.key not in seen:
                seen.add(conflict.key)
                kept.append((_json_line(conflict).encode("utf-8"), conflict))
        return type(self)(
            lines=tuple(kept), data=b"".join(raw + b"\n" for raw, _ in kept)
        )


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
