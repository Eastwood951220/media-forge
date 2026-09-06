from pathlib import Path
from zipfile import ZipFile

import pytest

from backend.app.modules.backup.format import (
    inspect_backup_archive,
    read_jsonl,
    write_jsonl,
    write_manifest,
)
from backend.app.modules.backup.paths import safe_backup_file_path


def test_jsonl_archive_round_trip(tmp_path: Path):
    archive = tmp_path / "sample.mfbackup"
    with ZipFile(archive, "w") as zip_file:
        write_manifest(zip_file, {
            "format": "media-forge-backup",
            "version": 1,
            "groups": ["movies"],
            "include_sensitive": False,
            "row_counts": {"data/movies.jsonl": 2},
        })
        count = write_jsonl(zip_file, "data/movies.jsonl", [{"id": "1"}, {"id": "2"}])

    assert count == 2
    with ZipFile(archive) as zip_file:
        assert list(read_jsonl(zip_file, "data/movies.jsonl")) == [{"id": "1"}, {"id": "2"}]

    inspected = inspect_backup_archive(archive)
    assert inspected.groups == ["movies"]
    assert inspected.row_counts == {"data/movies.jsonl": 2}


def test_safe_backup_file_path_rejects_traversal(tmp_path: Path):
    with pytest.raises(ValueError, match="Invalid backup file name"):
        safe_backup_file_path(tmp_path, "../escape.mfbackup")

    with pytest.raises(ValueError, match="Invalid backup file name"):
        safe_backup_file_path(tmp_path, "notes.txt")

    assert safe_backup_file_path(tmp_path, "ok.mfbackup") == tmp_path / "ok.mfbackup"


def test_inspect_rejects_archive_path_traversal(tmp_path: Path):
    archive = tmp_path / "bad.mfbackup"
    with ZipFile(archive, "w") as zip_file:
        write_manifest(zip_file, {
            "format": "media-forge-backup",
            "version": 1,
            "groups": ["movies"],
            "include_sensitive": False,
            "row_counts": {},
        })
        zip_file.writestr("../bad.jsonl", "{}\n")

    with pytest.raises(ValueError, match="Unsafe archive entry"):
        inspect_backup_archive(archive)
