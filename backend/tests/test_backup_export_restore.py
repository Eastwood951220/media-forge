from pathlib import Path
from zipfile import ZipFile

from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.user import User
from backend.app.modules.backup.format import inspect_backup_archive, read_jsonl
from backend.app.modules.backup.schemas import BackupExportRequest
from backend.app.modules.backup.service import BackupService
from shared.database.models.content import Movie, MovieMagnet


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
