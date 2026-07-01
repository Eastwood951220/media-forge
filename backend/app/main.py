import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import get_settings
from backend.app.core.dependencies import close_redis
from backend.app.modules.auth.router import router as auth_router
from backend.app.modules.health.router import router as health_router
from backend.app.modules.init.router import router as init_router
from shared.database.session import close_postgres, connect_postgres
from shared.runtime_config import load_runtime_config, runtime_config_exists
import os

# -- Logging setup --

settings = get_settings()

logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Console handler
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Plain text file handler
os.makedirs(settings.log_dir, exist_ok=True)
file_handler = logging.FileHandler(
    os.path.join(settings.log_dir, "backend.log"), encoding="utf-8"
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

    if runtime_config_exists():
        connect_postgres()
        logger.info("PostgreSQL connected.")
    else:
        logger.warning("Backend not initialized — only init endpoints available.")

    yield

    # Shutdown
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


@app.get("/")
def root() -> dict[str, str]:
    return {"message": f"{settings.app_name} API", "version": settings.app_version}
