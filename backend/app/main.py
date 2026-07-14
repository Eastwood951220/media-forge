import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from backend.app.core.config import get_settings
from backend.app.core.dependencies import close_redis, get_redis
from backend.app.core.exception_handlers import register_exception_handlers
from backend.app.modules.auth.router import router as auth_router
from backend.app.modules.content.movies.router import router as content_movies_router
from backend.app.modules.crawler.config.router import router as crawler_config_router
from backend.app.modules.crawler.runs.router import router as crawler_runs_router
from backend.app.modules.crawler.runtime.service import cleanup_interrupted_runs, get_runtime_state
from backend.app.modules.storage.worker.runner import cleanup_interrupted_storage_tasks
from backend.app.startup_database import connect_or_repair_postgres
from backend.app.modules.crawler.tasks.router import router as crawler_tasks_router
from backend.app.modules.realtime.bus import event_bus
from backend.app.modules.realtime.router import router as realtime_router
from backend.app.modules.dashboard.router import router as dashboard_router
from backend.app.modules.health.router import router as health_router
from backend.app.modules.init.router import router as init_router
from backend.app.modules.storage.config.router import router as storage_config_router
from backend.app.modules.storage.index.router import router as storage_index_router
from backend.app.modules.storage.tasks.router import router as storage_tasks_router
from shared.database.session import close_postgres, get_session_factory
from shared.logging.file_log import ensure_log_dir
from shared.runtime_config import load_runtime_config, runtime_config_exists

# -- Logging setup --

settings = get_settings()

FRONTEND_STATIC_DIR = Path(__file__).resolve().parent / "static"
FRONTEND_INDEX_FILE = "index.html"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Console handler
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Plain text file handler
ensure_log_dir(settings.log_dir)
file_handler = logging.FileHandler(
    f"{settings.log_dir}/backend.log", encoding="utf-8"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# -- Lifespan --


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle."""
    logger.info("Starting Media Forge backend v%s", settings.app_version)

    # Startup
    # Load runtime config (database.conf / redis.conf) into env
    load_runtime_config()

    event_bus.configure_redis(get_redis)

    if connect_or_repair_postgres():
        logger.info("PostgreSQL connected.")

        # Cleanup interrupted crawler runs on startup
        factory = get_session_factory()
        with factory() as session:
            stopped = cleanup_interrupted_runs(session, get_runtime_state())
            if stopped:
                logger.info("Stopped %d interrupted crawler runs.", stopped)

            # Cleanup interrupted storage tasks on startup
            from backend.app.modules.storage.runtime.redis_state import StorageRuntimeState
            storage_stopped = cleanup_interrupted_storage_tasks(session, StorageRuntimeState(get_redis()))
            if storage_stopped:
                logger.info("Stopped %d interrupted storage tasks.", storage_stopped)
    else:
        logger.warning("Backend not initialized — only init endpoints available.")

    yield

    # Shutdown
    event_bus.close()
    close_redis()
    if runtime_config_exists():
        close_postgres()
    logger.info("Media Forge backend shut down.")


# -- App --


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# Exception handlers
register_exception_handlers(app)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(init_router)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(realtime_router)
app.include_router(dashboard_router)
app.include_router(crawler_tasks_router)
app.include_router(crawler_config_router)
app.include_router(crawler_runs_router)
app.include_router(content_movies_router)
app.include_router(storage_config_router)
app.include_router(storage_index_router)
app.include_router(storage_tasks_router)


def configure_frontend(
    target_app: FastAPI,
    static_dir: Path = FRONTEND_STATIC_DIR,
) -> None:
    """Serve built frontend assets when the Vite dist output is present."""
    index_file = static_dir / FRONTEND_INDEX_FILE
    assets_dir = static_dir / "assets"
    if not index_file.exists():
        return

    if assets_dir.exists():
        target_app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="frontend-assets",
        )

    @target_app.get("/", include_in_schema=False)
    def frontend_root() -> FileResponse:
        return FileResponse(index_file)

    @target_app.get("/{full_path:path}", include_in_schema=False)
    def frontend_fallback(full_path: str) -> Response:
        if full_path == "api" or full_path.startswith("api/"):
            return Response(status_code=404, media_type="application/json", content='{"detail":"Not Found"}')
        requested_file = static_dir / full_path
        if requested_file.is_file():
            return FileResponse(requested_file)
        return FileResponse(index_file)


configure_frontend(app)
