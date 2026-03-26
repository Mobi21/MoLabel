"""Tests for atomic file writer (EX-006, EX-014).

Covers AtomicWriter, WriteVerification, ConflictCheck, ConflictResolution,
and AtomicWriteResult.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from molabel.core.export.atomic_writer import (
    AtomicWriter,
    ConflictResolution,
)

# ---------------------------------------------------------------------------
# EX-006: WriteVerification
# ---------------------------------------------------------------------------


class TestWriteVerification:
    def test_verify_valid_data(self) -> None:
        writer = AtomicWriter()
        data = b'{"id": 1}\n{"id": 2}\n'
        result = writer.verify_data(data, expected_record_count=2, line_delimited=True)
        assert result.valid is True
        assert result.record_count == 2
        assert result.content_hash != ""
        assert result.file_size_bytes == len(data)

    def test_verify_count_mismatch(self) -> None:
        writer = AtomicWriter()
        data = b'{"id": 1}\n'
        result = writer.verify_data(data, expected_record_count=5, line_delimited=True)
        assert result.valid is False
        assert len(result.errors) == 1
        assert "mismatch" in result.errors[0].lower()

    def test_verify_empty_data(self) -> None:
        writer = AtomicWriter()
        result = writer.verify_data(b"", expected_record_count=None)
        assert result.valid is True
        assert result.file_size_bytes == 0

    def test_verify_non_line_delimited(self) -> None:
        writer = AtomicWriter()
        data = b"binary data here"
        result = writer.verify_data(data, expected_record_count=1, line_delimited=False)
        assert result.valid is True
        assert result.record_count == 1

    def test_content_hash_deterministic(self) -> None:
        writer = AtomicWriter()
        data = b"hello world"
        r1 = writer.verify_data(data)
        r2 = writer.verify_data(data)
        assert r1.content_hash == r2.content_hash


# ---------------------------------------------------------------------------
# EX-014: ConflictCheck
# ---------------------------------------------------------------------------


class TestConflictCheck:
    def test_no_conflict_when_file_absent(self, tmp_path: Path) -> None:
        writer = AtomicWriter()
        target = tmp_path / "nonexistent.jsonl"
        result = writer.check_conflict(target, "abc123")
        assert result.has_conflict is False
        assert result.new_hash == "abc123"

    def test_no_conflict_when_hash_matches(self, tmp_path: Path) -> None:
        writer = AtomicWriter()
        target = tmp_path / "file.jsonl"
        data = b"same content"
        target.write_bytes(data)

        import hashlib

        h = hashlib.sha256(data).hexdigest()
        result = writer.check_conflict(target, h)
        assert result.has_conflict is False
        assert "unchanged" in result.message.lower()

    def test_conflict_when_hash_differs(self, tmp_path: Path) -> None:
        writer = AtomicWriter()
        target = tmp_path / "file.jsonl"
        target.write_bytes(b"old content")

        result = writer.check_conflict(target, "new_hash_value")
        assert result.has_conflict is True
        assert result.existing_hash is not None
        assert result.existing_hash != "new_hash_value"

    def test_conflict_with_record_count_delta(self, tmp_path: Path) -> None:
        writer = AtomicWriter()
        target = tmp_path / "file.jsonl"
        target.write_bytes(b"data")

        result = writer.check_conflict(
            target,
            "new_hash",
            new_record_count=150,
            existing_record_count=100,
        )
        assert result.has_conflict is True
        assert result.record_count_delta == 50

    def test_conflict_with_field_changes(self, tmp_path: Path) -> None:
        writer = AtomicWriter()
        target = tmp_path / "file.jsonl"
        target.write_bytes(b"data")

        result = writer.check_conflict(
            target,
            "new_hash",
            new_fields={"text", "sentiment", "new_field"},
            existing_fields={"text", "sentiment", "old_field"},
        )
        assert result.has_conflict is True
        assert len(result.field_changes) == 2  # added + removed


# ---------------------------------------------------------------------------
# EX-014: ConflictResolution
# ---------------------------------------------------------------------------


class TestConflictResolution:
    def test_force(self) -> None:
        r = ConflictResolution.force("Testing")
        assert r.strategy == "force"
        assert r.reason == "Testing"

    def test_refresh(self) -> None:
        r = ConflictResolution.refresh("Re-export needed")
        assert r.strategy == "refresh"

    def test_rebase(self) -> None:
        r = ConflictResolution.rebase()
        assert r.strategy == "rebase"

    def test_fail(self) -> None:
        r = ConflictResolution.fail("Abort")
        assert r.strategy == "fail"

    def test_frozen(self) -> None:
        r = ConflictResolution.force("test")
        with pytest.raises(AttributeError):
            r.strategy = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EX-006: Atomic writes
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_write_new_file(self, tmp_path: Path) -> None:
        writer = AtomicWriter(quarantine_dir=tmp_path / "quarantine")
        target = tmp_path / "output" / "latest.jsonl"
        data = b'{"id": 1}\n'

        result = writer.write_atomic(data, target)
        assert result.success is True
        assert result.final_path == target
        assert result.previous_path is None
        assert target.exists()
        assert target.read_bytes() == data

    def test_write_archives_previous(self, tmp_path: Path) -> None:
        writer = AtomicWriter(quarantine_dir=tmp_path / "quarantine")
        target = tmp_path / "output" / "latest.jsonl"

        # First write
        writer.write_atomic(b"first content", target)
        assert target.exists()

        # Second write with different content
        result = writer.write_atomic(
            b"second content",
            target,
            conflict_resolution=ConflictResolution.force("test"),
        )
        assert result.success is True
        assert result.previous_path is not None
        assert result.previous_path.exists()
        assert result.previous_path.read_bytes() == b"first content"
        assert target.read_bytes() == b"second content"

    def test_write_conflict_without_resolution_fails(self, tmp_path: Path) -> None:
        writer = AtomicWriter()
        target = tmp_path / "latest.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"existing content")

        result = writer.write_atomic(b"new content", target)
        assert result.success is False
        assert "conflict" in (result.error or "").lower()
        # Original file should be unchanged
        assert target.read_bytes() == b"existing content"

    def test_write_skip_conflict_check(self, tmp_path: Path) -> None:
        writer = AtomicWriter()
        target = tmp_path / "latest.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"existing")

        result = writer.write_atomic(b"new", target, skip_conflict_check=True)
        assert result.success is True
        assert target.read_bytes() == b"new"

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        writer = AtomicWriter()
        target = tmp_path / "deep" / "nested" / "dir" / "file.jsonl"

        result = writer.write_atomic(data=b"data", target=target)
        assert result.success is True
        assert target.exists()

    def test_write_content_hash_correct(self, tmp_path: Path) -> None:
        import hashlib

        writer = AtomicWriter()
        data = b"test data for hashing"
        target = tmp_path / "test.jsonl"

        result = writer.write_atomic(data, target)
        assert result.success is True
        expected_hash = hashlib.sha256(data).hexdigest()
        assert result.content_hash == expected_hash

    def test_write_file_size_correct(self, tmp_path: Path) -> None:
        writer = AtomicWriter()
        data = b"x" * 1024
        target = tmp_path / "test.jsonl"

        result = writer.write_atomic(data, target)
        assert result.success is True
        assert result.file_size_bytes == 1024

    def test_quarantine_cleanup(self, tmp_path: Path) -> None:
        quarantine = tmp_path / "quarantine"
        writer = AtomicWriter(quarantine_dir=quarantine)
        target = tmp_path / "output.jsonl"

        result = writer.write_atomic(b"data", target)
        assert result.success is True
        # Quarantine dir should be cleaned up if empty
        if quarantine.exists():
            assert not any(quarantine.iterdir())
