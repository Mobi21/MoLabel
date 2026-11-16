"""Write YAML files that people also edit by hand."""

from __future__ import annotations

import io
from collections.abc import Mapping
from typing import Any

import yaml as pyyaml
from ruamel.yaml import YAML, YAMLError
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.representer import RoundTripRepresenter
from ruamel.yaml.resolver import VersionedResolver
from ruamel.yaml.util import load_yaml_guess_indent


class _Yaml11Resolver(VersionedResolver):
    """Resolve plain scalars as YAML 1.1, the version PyYAML reads.

    Without it ``"yes"`` is written unquoted and read back as ``True``.
    """

    @property
    def processing_version(self) -> Any:
        return (1, 1)


class _Representer(RoundTripRepresenter):
    def represent_none(self, data: Any) -> Any:
        return self.represent_scalar("tag:yaml.org,2002:null", "null")


_Representer.add_representer(type(None), _Representer.represent_none)


def _round_trip_yaml() -> YAML:
    yaml = YAML()
    yaml.Resolver = _Yaml11Resolver
    yaml.Representer = _Representer
    yaml.preserve_quotes = True
    yaml.allow_duplicate_keys = True
    yaml.width = 4096
    return yaml


def _kind(value: Any) -> type:
    for kind in (bool, int, float, str):
        if isinstance(value, kind):
            return kind
    return type(value)


def _same(old: Any, new: Any) -> bool:
    """Equal, and of the same scalar kind at every depth (``True`` is not ``1``)."""
    if isinstance(old, Mapping) and isinstance(new, Mapping):
        keys = {(_kind(k), k) for k in new}
        return {(_kind(k), k) for k in old} == keys and all(
            _same(old[k], new[k]) for k in new
        )
    if isinstance(old, list) and isinstance(new, list):
        return len(old) == len(new) and all(map(_same, old, new))
    return _kind(old) is _kind(new) and old == new


def _shares_nodes(node: Any, seen: set[int] | None = None) -> bool:
    """Whether *node* uses anchors, aliases or merge keys, which a merge corrupts."""
    seen = set() if seen is None else seen
    if not isinstance(node, CommentedMap | CommentedSeq):
        return False
    if id(node) in seen or node.anchor.value is not None:
        return True
    if isinstance(node, CommentedMap) and getattr(node, "merge", None):
        return True
    seen.add(id(node))
    children = node.values() if isinstance(node, CommentedMap) else node
    return any(_shares_nodes(child, seen) for child in children)


def _merge(old: Any, new: Any) -> Any:
    if _same(old, new):
        return old
    if isinstance(old, CommentedMap) and isinstance(new, Mapping) and old:
        for key in [key for key in old if key not in new]:
            del old[key]
        for key, value in new.items():
            old[key] = _merge(old[key], value) if key in old else value
        return old
    if isinstance(old, CommentedSeq) and isinstance(new, list) and old:
        del old[len(new) :]
        for index, value in enumerate(new):
            if index < len(old):
                old[index] = _merge(old[index], value)
            else:
                old.append(value)
        return old
    return new


def dump_yaml(data: Mapping[str, Any], previous: str | None = None) -> str:
    """Render *data* as YAML, keeping the layout of *previous* where it can.

    *previous* is the text of the file being replaced. Keys and list items
    that *data* still has keep their comments, order, quoting and the file's
    sequence indentation. Keys *data* lacks are removed and new keys go at
    the end. The result always reads back with PyYAML as exactly *data*:
    each candidate is checked, and when the merged and fresh renders both
    fail, *data* is written with a plain PyYAML dump that escapes non-ASCII,
    so characters such as U+0085 survive.
    """
    for candidate in (_merged(data, previous), _render(data, 4, 2)):
        if candidate is not None and _reads_back(candidate, data):
            return candidate
    return pyyaml.safe_dump(dict(data), sort_keys=False, allow_unicode=False)


def _merged(data: Mapping[str, Any], previous: str | None) -> str | None:
    if previous is None:
        return None
    try:
        loaded, indent, block_seq_indent = load_yaml_guess_indent(
            previous, yaml=_round_trip_yaml()
        )
    except YAMLError:
        return None
    if loaded is None or _shares_nodes(loaded):
        return None
    if indent is None or block_seq_indent is None:
        indent, block_seq_indent = 4, 2
    return _render(_merge(loaded, data), indent, block_seq_indent)


def _reads_back(text: str, data: Mapping[str, Any]) -> bool:
    try:
        return _same(pyyaml.safe_load(text), data)
    except pyyaml.YAMLError:
        return False


def _render(document: Any, sequence_indent: int, offset: int) -> str:
    yaml = _round_trip_yaml()
    yaml.indent(mapping=2, sequence=sequence_indent, offset=offset)
    stream = io.StringIO()
    yaml.dump(document, stream)
    return stream.getvalue()
