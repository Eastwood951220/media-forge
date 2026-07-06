import uuid

from backend.app.models.crawl_task import CrawlTask
from backend.app.models.storage_task import StorageMainTask, StorageSubTask
from backend.app.modules.storage.tasks.serializers import (
    storage_main_task_to_dict,
    storage_subtask_to_dict,
)
from backend.app.modules.storage.tasks.skip_rules import classify_storage_skip
from backend.app.modules.storage.tasks.target_locations import resolve_target_locations
from shared.database.models.content import Movie, MovieMagnet


def test_classify_storage_skip_returns_expected_reasons() -> None:
    assert classify_storage_skip(None) == "movie_not_found"

    marked = Movie(code="A", source_name="A", marked=True)
    assert classify_storage_skip(marked) == "movie_marked"

    no_magnets = Movie(code="B", source_name="B", marked=False)
    no_magnets.magnets = []
    assert classify_storage_skip(no_magnets) == "no_magnets"

    no_url = Movie(code="C", source_name="C", marked=False)
    no_url.magnets = [MovieMagnet(magnet_url="", dedupe_key="empty")]
    assert classify_storage_skip(no_url) == "no_magnet_url"

    usable = Movie(code="D", source_name="D", marked=False)
    usable.magnets = [MovieMagnet(magnet_url="magnet:?xt=urn:btih:abc", dedupe_key="abc")]
    assert classify_storage_skip(usable) is None


def test_resolve_target_locations_uses_source_task_locations(db_session, test_user) -> None:
    task_a = CrawlTask(name="A", owner_id=test_user.id, storage_location="A")
    task_b = CrawlTask(name="B", owner_id=test_user.id, storage_location="B")
    db_session.add_all([task_a, task_b])
    db_session.flush()
    movie = Movie(code="LOC-1", source_name="LOC", source_task_ids=[task_a.id, task_b.id])

    assert resolve_target_locations(db_session, movie, "single", "B") == ["B"]
    assert resolve_target_locations(db_session, movie, "batch", None) == ["A"]
    assert resolve_target_locations(db_session, movie, "single", None) == ["A", "B"]


def test_storage_task_serializers_preserve_response_shape(test_user) -> None:
    main_id = uuid.uuid4()
    movie_id = uuid.uuid4()
    main = StorageMainTask(
        id=main_id,
        alias="alias",
        display_name="alias",
        source="single",
        storage_mode="single",
        status="queued",
        total_count=1,
        success_count=0,
        failed_count=0,
        skipped_count=0,
        created_by=test_user.id,
    )
    sub = StorageSubTask(
        id=uuid.uuid4(),
        main_task_id=main_id,
        movie_id=movie_id,
        movie_code="ABC-123",
        movie_title="Title",
        status="queued",
        step="prepare",
        storage_mode="single",
        selected_storage_location="A",
        target_locations=["A"],
        target_paths=["/Movies/A/ABC-123"],
        download_path="",
    )

    main_payload = storage_main_task_to_dict(main)
    sub_payload = storage_subtask_to_dict(sub)

    assert main_payload["id"] == str(main_id)
    assert main_payload["alias"] == "alias"
    assert main_payload["status"] == "queued"
    assert sub_payload["movie_code"] == "ABC-123"
    assert sub_payload["target_locations"] == ["A"]
    assert sub_payload["current_magnet_id"] is None


def test_storage_task_creator_creates_skipped_subtask_for_movie_without_magnets(db_session, test_user) -> None:
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.creation import StorageTaskCreator
    from backend.app.modules.storage.tasks.repository import StorageTaskRepository

    movie = Movie(code="NO-MAG", source_name="No Magnet")
    db_session.add(movie)
    db_session.flush()

    class ConfigService:
        def get_raw_config(self):
            return {"target_folder": "/Movies"}

    creator = StorageTaskCreator(
        db=db_session,
        repository=StorageTaskRepository(db_session),
        config_service=ConfigService(),
    )

    main = creator.create_main_task(
        movie_ids=[movie.id],
        user_id=test_user.id,
        source="single",
        alias="manual",
        storage_mode="single",
        selected_storage_location=None,
    )

    assert main.alias == "manual"
    assert main.subtasks[0].status == "skipped"
    assert main.subtasks[0].skip_reason == "no_magnets"


def test_storage_task_service_create_single_push_uses_creator_path(db_session, test_user, monkeypatch) -> None:
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.tasks.schemas import StorageSinglePushRequest
    from backend.app.modules.storage.tasks.service import StorageTaskService
    from shared.database.models.content import Movie

    movie = Movie(code="SVC-001", source_name="Service Movie")
    db_session.add(movie)
    db_session.flush()

    class ConfigService:
        provider_factory = None

        def get_raw_config(self):
            return {"target_folder": "/Movies"}

    service = StorageTaskService(db_session, ConfigService(), runtime=None)
    body = StorageSinglePushRequest(
        movie_id=movie.id,
        alias="service-path",
        storage_mode="single",
        selected_storage_location=None,
    )

    main_task = service.create_single_push(body, test_user.id)

    assert main_task.alias == "service-path"
    assert main_task.subtasks[0].status == "skipped"
    assert main_task.subtasks[0].skip_reason == "no_magnets"
