"""Write YAML files that people also edit by hand.

``dump_yaml`` renders new data over the text it replaces, so the comments,
key order, quoting and indentation of every key that survives are kept.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from typing import Any

from ruamel.yaml import YAML
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
    yaml.width = 4096
    return yaml


def _same(old: Any, new: Any) -> bool:
    return isinstance(old, bool) == isinstance(new, bool) and old == new


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
    indentation. Keys *data* lacks are removed and new keys go at the end.
    """
    yaml = _round_trip_yaml()
    document: Any = data
    sequence_indent, offset = 4, 2
    if previous is not None:
        loaded, indent, block_seq_indent = load_yaml_guess_indent(previous, yaml=yaml)
        document = _merge(loaded, data)
        if indent is not None and block_seq_indent is not None:
            sequence_indent, offset = indent, block_seq_indent
    yaml.indent(mapping=2, sequence=sequence_indent, offset=offset)
    stream = io.StringIO()
    yaml.dump(document, stream)
    return stream.getvalue()
