import uuid
from pathlib import Path
from zipfile import ZipFile

from backend.app.models.crawl_task import (
    CrawlTask,
    CrawlTaskUrl,
)
from backend.app.models.user import User
from backend.app.modules.backup.format import (
    inspect_backup_archive,
    read_jsonl,
    write_jsonl,
    write_manifest,
)
from backend.app.modules.backup.schemas import BackupExportRequest, BackupRestoreRequest
from backend.app.modules.backup.service import BackupService
from shared.database.models.content import (
    ActressProfile,
    ActressTag,
    Movie,
    MovieMagnet,
    actress_tag_links,
)


def _write_tasks_archive_manifest(zip_file: ZipFile) -> None:
    write_manifest(
        zip_file,
        {
            "format": "media-forge-backup",
            "version": 1,
            "groups": ["tasks"],
            "include_sensitive": False,
            "row_counts": {},
        },
    )


def _write_legacy_task_tag_archive(path: Path, *, owner_id: uuid.UUID) -> None:
    """Write a tasks-group archive as an older release wrote it, without actress tags."""
    with ZipFile(path, "w") as zip_file:
        _write_tasks_archive_manifest(zip_file)
        write_jsonl(zip_file, "data/crawl_tasks.jsonl", [])
        write_jsonl(
            zip_file,
            "data/crawl_task_tags.jsonl",
            [{"id": str(uuid.uuid4()), "owner_id": str(owner_id), "name": "旧任务标签"}],
        )
        write_jsonl(
            zip_file,
            "data/crawl_task_tag_links.jsonl",
            [{"task_id": str(uuid.uuid4()), "tag_id": str(uuid.uuid4())}],
        )


def _write_actress_tag_archive(
    path: Path,
    *,
    owner_id: uuid.UUID,
    profile_id: uuid.UUID,
    tag_id: uuid.UUID,
) -> None:
    """Write a tasks-group archive with actress tags plus legacy task tag files."""
    with ZipFile(path, "w") as zip_file:
        _write_tasks_archive_manifest(zip_file)
        write_jsonl(zip_file, "data/crawl_tasks.jsonl", [])
        write_jsonl(
            zip_file,
            "data/actress_tags.jsonl",
            [{"id": str(tag_id), "owner_id": str(owner_id), "name": "企划"}],
        )
        write_jsonl(
            zip_file,
            "data/actress_tag_links.jsonl",
            [{"actress_profile_id": str(profile_id), "tag_id": str(tag_id)}],
        )
        # Legacy files an older release would have written.
        write_jsonl(
            zip_file,
            "data/crawl_task_tags.jsonl",
            [{"id": str(uuid.uuid4()), "owner_id": str(owner_id), "name": "旧任务标签"}],
        )
        write_jsonl(
            zip_file,
            "data/crawl_task_tag_links.jsonl",
            [{"task_id": str(uuid.uuid4()), "tag_id": str(uuid.uuid4())}],
        )


def _seed_actress_profile(db_session) -> ActressProfile:
    profile = ActressProfile(
        display_name="三上悠亚",
        canonical_names=["三上悠亚"],
        source_url="https://example.test/actress-1",
    )
    db_session.add(profile)
    db_session.commit()
    return profile


def test_export_writes_selected_groups_without_runs(db_session, test_user: User, tmp_path: Path):
    movie = Movie(code="ABC-001", source_url="https://example.test/abc-001", source_name="javdb")
    magnet = MovieMagnet(movie=movie, dedupe_key="hash-1", magnet_url="magnet:?xt=urn:btih:hash")
    task = CrawlTask(name="Actors", owner_id=test_user.id, storage_location="/Movies")
    task.urls.append(CrawlTaskUrl(position=0, url="https://example.test/a", url_type="actors", final_url="https://example.test/a"))
    db_session.add_all([movie, magnet, task])
    db_session.commit()

    path = BackupService(db_session).export_to_file(
        BackupExportRequest(groups=["movies", "tasks"], include_sensitive=False),
        output_dir=tmp_path,
        owner_id=test_user.id,
    )

    assert path.suffix == ".mfbackup"
    inspected = inspect_backup_archive(path)
    assert inspected.groups == ["movies", "tasks"]
    assert "data/movies.jsonl" in inspected.row_counts
    assert "data/crawl_tasks.jsonl" in inspected.row_counts
    assert "data/crawl_runs.jsonl" not in inspected.row_counts

    with ZipFile(path) as zip_file:
        movies = list(read_jsonl(zip_file, "data/movies.jsonl"))
        tasks = list(read_jsonl(zip_file, "data/crawl_tasks.jsonl"))
    assert movies[0]["code"] == "ABC-001"
    assert tasks[0]["owner_id"] == str(test_user.id)


def test_export_writes_actress_tags_instead_of_task_tags(db_session, test_user: User, tmp_path: Path):
    profile = _seed_actress_profile(db_session)
    tag = ActressTag(owner_id=test_user.id, name="企划")
    db_session.add(tag)
    db_session.flush()
    profile.tags.append(tag)
    db_session.commit()

    path = BackupService(db_session).export_to_file(
        BackupExportRequest(groups=["tasks"], include_sensitive=False),
        output_dir=tmp_path,
        owner_id=test_user.id,
    )

    inspected = inspect_backup_archive(path)
    with ZipFile(path) as zip_file:
        archive_names = {info.filename for info in zip_file.infolist()}
        tags = list(read_jsonl(zip_file, "data/actress_tags.jsonl"))
        links = list(read_jsonl(zip_file, "data/actress_tag_links.jsonl"))

    assert "data/actress_tags.jsonl" in archive_names
    assert "data/actress_tag_links.jsonl" in archive_names
    assert "data/crawl_task_tags.jsonl" not in archive_names
    assert "data/crawl_task_tag_links.jsonl" not in archive_names
    assert inspected.row_counts["data/actress_tags.jsonl"] == 1
    assert inspected.row_counts["data/actress_tag_links.jsonl"] == 1
    assert [(row["name"], row["owner_id"]) for row in tags] == [("企划", str(test_user.id))]
    assert links == [{"actress_profile_id": str(profile.id), "tag_id": str(tag.id)}]


def test_export_scopes_actress_tags_and_links_to_the_requesting_user(
    db_session, test_user: User, other_user: User, tmp_path: Path
):
    """Per-user export keeps only the requester's tags and links on a shared profile."""
    shared_profile = _seed_actress_profile(db_session)
    my_tag = ActressTag(owner_id=test_user.id, name="我的标签")
    other_tag = ActressTag(owner_id=other_user.id, name="别人标签")
    db_session.add_all([my_tag, other_tag])
    db_session.flush()
    shared_profile.tags.extend([my_tag, other_tag])
    db_session.commit()

    path = BackupService(db_session).export_to_file(
        BackupExportRequest(groups=["tasks"], include_sensitive=False),
        output_dir=tmp_path,
        owner_id=test_user.id,
    )

    with ZipFile(path) as zip_file:
        tags = list(read_jsonl(zip_file, "data/actress_tags.jsonl"))
        links = list(read_jsonl(zip_file, "data/actress_tag_links.jsonl"))

    assert [(row["name"], row["owner_id"]) for row in tags] == [("我的标签", str(test_user.id))]
    assert links == [{"actress_profile_id": str(shared_profile.id), "tag_id": str(my_tag.id)}]


def test_restore_reads_actress_tags_and_ignores_legacy_task_tag_files(
    db_session, test_user: User, tmp_path: Path
):
    profile = _seed_actress_profile(db_session)
    archive = tmp_path / "legacy.mfbackup"
    _write_actress_tag_archive(
        archive,
        owner_id=test_user.id,
        profile_id=profile.id,
        tag_id=uuid.uuid4(),
    )

    result = BackupService(db_session).restore_from_file(
        archive,
        BackupRestoreRequest(mode="merge", groups=["tasks"]),
        owner_id=test_user.id,
    )

    assert result["tasks"]["errors"] == 0
    db_session.expire_all()
    restored = db_session.get(ActressProfile, profile.id)
    assert [tag.name for tag in restored.tags] == ["企划"]


def test_restore_accepts_archive_with_only_legacy_task_tag_files(
    db_session, test_user: User, tmp_path: Path
):
    archive = tmp_path / "old-format.mfbackup"
    _write_legacy_task_tag_archive(archive, owner_id=test_user.id)

    with ZipFile(archive) as zip_file:
        assert "data/crawl_task_tags.jsonl" in zip_file.namelist()
        assert "data/crawl_task_tag_links.jsonl" in zip_file.namelist()

    result = BackupService(db_session).restore_from_file(
        archive,
        BackupRestoreRequest(mode="merge", groups=["tasks"]),
        owner_id=test_user.id,
    )

    assert result["tasks"]["errors"] == 0
    assert db_session.query(ActressTag).count() == 0


def test_overwrite_restore_keeps_actress_tags_when_archive_has_none(
    db_session, test_user: User, tmp_path: Path
):
    profile = _seed_actress_profile(db_session)
    kept_tag = ActressTag(owner_id=test_user.id, name="保留标签")
    db_session.add(kept_tag)
    db_session.flush()
    profile.tags.append(kept_tag)
    db_session.commit()

    archive = tmp_path / "tasks-only.mfbackup"
    _write_legacy_task_tag_archive(archive, owner_id=test_user.id)

    BackupService(db_session).restore_from_file(
        archive,
        BackupRestoreRequest(mode="overwrite", groups=["tasks"]),
        owner_id=test_user.id,
    )

    db_session.expire_all()
    owned_tags = db_session.query(ActressTag).filter(ActressTag.owner_id == test_user.id).all()
    assert [tag.name for tag in owned_tags] == ["保留标签"]
    restored = db_session.get(ActressProfile, profile.id)
    assert [tag.name for tag in restored.tags] == ["保留标签"]


def test_restore_skips_actress_tag_links_without_matching_profile(
    db_session, test_user: User, tmp_path: Path
):
    archive = tmp_path / "orphan-link.mfbackup"
    _write_actress_tag_archive(
        archive,
        owner_id=test_user.id,
        profile_id=uuid.uuid4(),
        tag_id=uuid.uuid4(),
    )

    result = BackupService(db_session).restore_from_file(
        archive,
        BackupRestoreRequest(mode="merge", groups=["tasks"]),
        owner_id=test_user.id,
    )

    assert result["tasks"]["errors"] == 0
    assert result["tasks"]["skipped"] == 1
    assert db_session.query(ActressTag).filter(ActressTag.owner_id == test_user.id).count() == 1
    assert db_session.query(actress_tag_links).count() == 0


def test_overwrite_restore_replaces_owned_actress_tags(db_session, test_user: User, tmp_path: Path):
    profile = _seed_actress_profile(db_session)
    stale_tag = ActressTag(owner_id=test_user.id, name="旧标签")
    db_session.add(stale_tag)
    db_session.flush()
    profile.tags.append(stale_tag)
    db_session.commit()

    archive = tmp_path / "overwrite-actress-tags.mfbackup"
    _write_actress_tag_archive(
        archive,
        owner_id=test_user.id,
        profile_id=profile.id,
        tag_id=uuid.uuid4(),
    )

    BackupService(db_session).restore_from_file(
        archive,
        BackupRestoreRequest(mode="overwrite", groups=["tasks"]),
        owner_id=test_user.id,
    )

    db_session.expire_all()
    owned_tags = db_session.query(ActressTag).filter(ActressTag.owner_id == test_user.id).all()
    assert [tag.name for tag in owned_tags] == ["企划"]
    restored = db_session.get(ActressProfile, profile.id)
    assert [tag.name for tag in restored.tags] == ["企划"]


def test_merge_restore_preserves_movie_code_uniqueness(db_session, test_user: User, tmp_path: Path):
    source_movie = Movie(code="ABC-001", source_url="https://backup.test/abc-001", source_name="javdb")
    db_session.add(source_movie)
    db_session.commit()
    backup = BackupService(db_session).export_to_file(
        BackupExportRequest(groups=["movies"], include_sensitive=False),
        output_dir=tmp_path,
        owner_id=test_user.id,
    )

    db_session.delete(source_movie)
    db_session.flush()
    conflicting_movie = Movie(code="ABC-001", source_url="https://local.test/different", source_name="javdb")
    db_session.add(conflicting_movie)
    db_session.commit()

    result = BackupService(db_session).restore_from_file(
        backup,
        BackupRestoreRequest(mode="merge", groups=["movies"]),
        owner_id=test_user.id,
    )

    assert result["movies"]["conflicts"] == 1
    assert db_session.query(Movie).filter(Movie.code == "ABC-001").count() == 1
    assert db_session.query(Movie).filter(Movie.source_url == "https://backup.test/abc-001").count() == 0


def test_overwrite_restore_clears_selected_movie_group(db_session, test_user: User, tmp_path: Path):
    kept_task = CrawlTask(name="Keep Task", owner_id=test_user.id, storage_location="/Movies")
    backup_movie = Movie(code="ABC-002", source_url="https://backup.test/abc-002", source_name="javdb")
    db_session.add_all([kept_task, backup_movie])
    db_session.commit()
    backup = BackupService(db_session).export_to_file(
        BackupExportRequest(groups=["movies"], include_sensitive=False),
        output_dir=tmp_path,
        owner_id=test_user.id,
    )

    db_session.query(Movie).delete()
    db_session.add(Movie(code="LOCAL-001", source_url="https://local.test/one", source_name="javdb"))
    db_session.commit()

    result = BackupService(db_session).restore_from_file(
        backup,
        BackupRestoreRequest(mode="overwrite", groups=["movies"]),
        owner_id=test_user.id,
    )

    assert result["movies"]["created"] == 1
    assert db_session.query(Movie).filter(Movie.code == "LOCAL-001").count() == 0
    assert db_session.query(CrawlTask).filter(CrawlTask.name == "Keep Task").count() == 1
