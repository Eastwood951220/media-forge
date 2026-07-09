from datetime import datetime, timezone

from backend.app.modules.storage.index.models import StorageIndexMetadata, StorageIndexRecord
from backend.app.modules.storage.index.store import StorageIndexStore
from shared.runtime_config import RuntimeConfigPaths


def test_storage_index_store_streams_temp_then_finalizes_completed_index(tmp_path):
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )
    store = StorageIndexStore(paths)
    metadata = StorageIndexMetadata(
        target_folder="/嘿嘿/日本",
        status="completed",
        started_at="2026-07-09T00:00:00+00:00",
        completed_at="2026-07-09T00:01:00+00:00",
        category_count=1,
        code_folder_count=1,
        video_count=1,
        force_refresh_mode="none",
        errors=[],
    )
    record = StorageIndexRecord(
        code="ALDN-206",
        path="/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U/ALDN-206-U.mp4",
        target_folder="/嘿嘿/日本/巨乳|熟女|BBW/ALDN-206-U",
        storage_location="巨乳|熟女|BBW",
        file_name="ALDN-206-U.mp4",
        size=524288000,
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )

    temp_path = store.begin_temp_index()
    store.append_temp_record(record)

    assert temp_path.exists()
    assert temp_path.read_text(encoding="utf-8").strip()
    assert not paths.storage_index_file.exists()

    store.finalize_temp_index(metadata)

    assert not temp_path.exists()
    assert paths.storage_index_file.exists()
    assert paths.storage_index_meta_file.exists()
    assert store.read_metadata().status == "completed"
    assert store.load_index_by_code()["ALDN-206"][0].path == record.path


def test_storage_index_store_does_not_load_running_temp_index(tmp_path):
    paths = RuntimeConfigPaths(
        config_dir=tmp_path,
        database_file=tmp_path / "database.conf",
        redis_file=tmp_path / "redis.conf",
        storage_file=tmp_path / "storage.conf",
        storage_index_file=tmp_path / "storage_index.jsonl",
        storage_index_meta_file=tmp_path / "storage_index.meta.json",
    )
    store = StorageIndexStore(paths)
    store.begin_temp_index()
    store.write_running_metadata(StorageIndexMetadata(
        target_folder="/嘿嘿/日本",
        status="running",
        started_at="2026-07-09T00:00:00+00:00",
        current_path="/嘿嘿/日本/巨乳|熟女|BBW",
        video_count=1,
    ))

    try:
        store.load_index_by_code()
    except Exception as exc:
        assert "存储索引不存在或尚未完成" in str(exc)
    else:
        raise AssertionError("running temp index must not be loaded for bulk sync")
