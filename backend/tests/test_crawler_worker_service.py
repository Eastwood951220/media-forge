from datetime import datetime

from backend.app.core.security import get_password_hash
from backend.app.models.crawl_run import CrawlRun, CrawlRunDetailTask
from backend.app.models.crawl_task import CrawlTask, CrawlTaskUrl
from backend.app.models.user import User
from backend.app.modules.crawler.runtime.service import process_next_run
from backend.tests.conftest import TestingSessionLocal


class Runtime:
    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self.current = None
        self.progress = {}

    def claim_next_run(self):
        run_id, self._run_id = self._run_id, None
        return run_id

    def set_current_run(self, run_id):
        self.current = run_id

    def is_stop_requested(self, run_id):
        return False

    def write_progress(self, run_id, progress):
        self.progress = progress


class MovieServiceStub:
    def crawl_javdb_task(self, task, **kwargs):
        kwargs["on_tasks_batch_created"]([
            {"code": "AAA-001", "url": "https://javdb.com/v/aaa", "name": "AAA"}
        ])
        kwargs["on_item_saved"](
            {"code": "AAA-001", "url": "https://javdb.com/v/aaa", "name": "AAA"},
            {"code": "AAA-001", "source_url": "https://javdb.com/v/aaa", "source_name": "AAA", "source_task_name": [task.name]},
        )
        return {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}


def test_process_next_run_marks_saved(monkeypatch) -> None:
    session = TestingSessionLocal()
    user = User(username="worker-user", hashed_password=get_password_hash("pw"), role="admin")
    session.add(user)
    session.flush()
    task = CrawlTask(name="任务", owner_id=user.id, is_skip=False)
    task.urls = [CrawlTaskUrl(position=0, url="https://javdb.com/actors/a", url_type="actors", final_url="https://javdb.com/actors/a?page=1", source="javdb")]
    session.add(task)
    session.flush()
    run = CrawlRun(task_id=task.id, task_name=task.name, status="queued", crawl_mode="incremental", queued_at=datetime.now())
    session.add(run)
    session.commit()
    runtime = Runtime(str(run.id))

    # Mock the _execute_run function to avoid importing MovieService
    def mock_execute_run(db, run_obj, runtime_obj):
        run_obj.status = "completed"
        run_obj.result = {"total_tasks": 1, "completed_tasks": 1, "failed_tasks": 0}
        run_obj.finished_at = datetime.now()
        db.commit()
        detail = CrawlRunDetailTask(
            run_id=run_obj.id,
            task_name="任务",
            code="AAA-001",
            source_url="https://javdb.com/v/aaa",
            source_name="AAA",
            status="saved",
            created_at=datetime.now(),
        )
        db.add(detail)
        db.commit()

    monkeypatch.setattr("backend.app.modules.crawler.runtime.service._execute_run", mock_execute_run)

    processed = process_next_run(TestingSessionLocal, runtime)

    assert processed is True
    # Refresh session to see changes from process_next_run
    session.expire_all()
    refreshed = session.get(CrawlRun, run.id)
    assert refreshed.status == "completed"
    detail = session.query(CrawlRunDetailTask).one()
    assert detail.status == "saved"
