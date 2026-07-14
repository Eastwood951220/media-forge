from datetime import datetime, timezone

import pytest

from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord
from backend.app.modules.storage.index.store import StorageIndexMissingError, StorageIndexStore
from shared.runtime_config import RuntimeConfigPaths


def paths_for(tmp_path):
    return RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )


def record(code="ALDN-206", folder="/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U"):
    return StorageIndexRecord(
        code=code,
        path=f"{folder}/ALDN-206-U.mp4",
        target_folder=folder,
        storage_location="巨乳|熟女|BBW",
        file_name="ALDN-206-U.mp4",
        size=524288000,
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )


def completed_metadata() -> StorageIndexMetadata:
    return StorageIndexMetadata(
        target_folder="/嘿嘿/日本",
        status="completed",
        started_at="2026-07-09T00:00:00+00:00",
        completed_at="2026-07-09T00:01:00+00:00",
        category_count=1,
        code_folder_count=1,
        video_count=1,
        force_refresh_mode="full",
        errors=[],
    )


def test_storage_index_store_writes_tree_and_flattens_by_code(tmp_path):
    store = StorageIndexStore(paths_for(tmp_path))
    item = record()
    tree = store.tree_from_records("/嘿嘿/日本", [item], indexed_at=item.indexed_at)

    store.begin_temp_index("/嘿嘿/日本")
    store.write_temp_tree(tree)
    store.finalize_temp_index(completed_metadata())

    saved_tree = store.read_index_tree()
    assert saved_tree["version"] == 1
    assert saved_tree["target_folder"] == "/嘿嘿/日本"
    assert "巨乳|熟女|BBW" in saved_tree["categories"]
    assert store.load_index_by_code()["ALDN-206"][0].path == item.path


def test_storage_index_store_upserts_records_into_existing_tree(tmp_path):
    store = StorageIndexStore(paths_for(tmp_path))
    first = record()
    second = StorageIndexRecord(
        code="BBBB-001",
        path="/嘿嘿/日本/新分类/BBBB-001/BBBB-001.mp4",
        target_folder="/嘿嘿/日本/新分类/BBBB-001",
        storage_location="新分类",
        file_name="BBBB-001.mp4",
        size=734003200,
        indexed_at="2026-07-10T00:00:00+00:00",
    )

    store.begin_temp_index("/嘿嘿/日本")
    store.write_temp_tree(store.tree_from_records("/嘿嘿/日本", [first], indexed_at=first.indexed_at))
    store.finalize_temp_index(completed_metadata())

    store.upsert_records([second], target_folder="/嘿嘿/日本")

    grouped = store.load_index_by_code()
    assert grouped["ALDN-206"][0].path == first.path
    assert grouped["BBBB-001"][0].path == second.path


def test_storage_index_store_does_not_load_running_temp_index(tmp_path):
    store = StorageIndexStore(paths_for(tmp_path))
    store.begin_temp_index("/嘿嘿/日本")
    store.write_running_metadata(StorageIndexMetadata(
        target_folder="/嘿嘿/日本",
        status="running",
        started_at="2026-07-09T00:00:00+00:00",
        current_path="/嘿嘿/日本/巨乳|熟女|BBW",
        video_count=1,
    ))

    with pytest.raises(StorageIndexMissingError, match="存储索引不存在或尚未完成"):
        store.load_index_by_code()


from backend.app.modules.storage.index.tree import (
    group_records_by_code,
    insert_record,
    known_code_folder_paths,
    tree_from_records,
)


def test_storage_index_tree_helpers_replace_duplicate_video_path():
    first = record()
    updated = StorageIndexRecord(
        code=first.code,
        path=first.path,
        target_folder=first.target_folder,
        storage_location=first.storage_location,
        file_name=first.file_name,
        size=first.size + 1,
        indexed_at="2026-07-14T00:00:00+00:00",
    )
    tree = tree_from_records("/嘿嘿/日本", [first], indexed_at=first.indexed_at)

    insert_record(tree, updated)

    grouped = group_records_by_code(tree)
    assert len(grouped["ALDN-206"]) == 1
    assert grouped["ALDN-206"][0].size == first.size + 1
    assert known_code_folder_paths(tree) == {first.target_folder}
