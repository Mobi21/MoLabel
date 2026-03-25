"""Markdown data loader plugin.

Each Markdown file becomes one record. Front matter (YAML between ``---``
delimiters) is extracted as structured metadata; the body is the content.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from molabel.core.plugins.registry import PluginRegistry
from molabel.core.types import SENTINEL_DATASET_ID, PluginMetadata, Record

_FRONT_MATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def _parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown document into front matter dict and body string."""
    match = _FRONT_MATTER_RE.match(text)
    if match:
        fm_text = match.group(1)
        body = text[match.end() :]
        try:
            front_matter = yaml.safe_load(fm_text)
            if not isinstance(front_matter, dict):
                front_matter = {}
        except yaml.YAMLError:
            front_matter = {}
        return front_matter, body
    return {}, text


class MarkdownLoader:
    """Loads records from Markdown files.

    Each ``.md`` file becomes a single record with:
    - ``stable_fields.content``: the markdown body
    - ``stable_fields.front_matter``: parsed YAML front matter (if present)
    - ``stable_fields.title``: extracted from front matter or first heading

    When given a directory, recursively discovers all ``.md`` files.

    Supports config options:
    - ``id_field``: front-matter field to use as ``external_id``.
    - ``encoding``: file encoding (default ``"utf-8"``).
    - ``recursive``: whether to scan subdirectories (default ``True``).
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="molabel.loaders.markdown",
            version="0.1.0",
            compatible_core=">=0.1,<1.0",
            description="Loads records from Markdown files with front matter.",
            author="MoLabel",
            tags=["loader", "markdown", "text"],
        )

    @property
    def supported_formats(self) -> list[str]:
        return ["md", "markdown"]

    def can_load(self, path: Path) -> bool:
        if path.is_file():
            return path.suffix.lower() in {".md", ".markdown"}
        if path.is_dir():
            return any(path.glob("*.md")) or any(path.glob("*.markdown"))
        return False

    def _iter_files(self, path: Path, recursive: bool) -> Iterator[Path]:
        if path.is_file():
            yield path
        elif path.is_dir():
            glob_func = path.rglob if recursive else path.glob
            yield from sorted(glob_func("*.md"))
            yield from sorted(glob_func("*.markdown"))

    def _extract_title(self, front_matter: dict[str, Any], body: str) -> str | None:
        """Extract title from front matter or first heading."""
        if "title" in front_matter:
            return str(front_matter["title"])
        # Look for first # heading
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return None

    def load_records(
        self,
        path: Path,
        config: dict[str, Any],
    ) -> Iterator[Record]:
        id_field = config.get("id_field")
        encoding = config.get("encoding", "utf-8")
        recursive = config.get("recursive", True)

        for file_path in self._iter_files(path, recursive):
            text = file_path.read_text(encoding=encoding)
            front_matter, body = _parse_front_matter(text)
            title = self._extract_title(front_matter, body)

            stable_fields: dict[str, Any] = {
                "content": body.strip(),
                "front_matter": front_matter,
                "source_file": str(file_path),
            }
            if title:
                stable_fields["title"] = title

            external_id = (
                str(front_matter[id_field])
                if id_field and id_field in front_matter
                else None
            )

            yield Record(
                id=uuid4(),
                dataset_id=SENTINEL_DATASET_ID,
                external_id=external_id,
                stable_fields=stable_fields,
                payload={"content": text, "front_matter": front_matter},
                record_kind="markdown",
            )

    def get_schema(self, path: Path) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "front_matter": {"type": "object"},
                "title": {"type": "string"},
                "source_file": {"type": "string"},
            },
        }

    def estimate_record_count(self, path: Path) -> int | None:
        if path.is_file():
            return 1
        if path.is_dir():
            count = 0
            for ext in ("*.md", "*.markdown"):
                count += sum(1 for _ in path.rglob(ext))
            return count
        return None


def register(registry: PluginRegistry) -> None:
    """Entry point called by molabel-core at startup."""
    registry.register_data_loader(MarkdownLoader())
