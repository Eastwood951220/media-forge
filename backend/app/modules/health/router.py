from fastapi import APIRouter

from shared.database.session import postgres_health_check
from shared.schemas.common import success

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health_check() -> dict:
    return success(data={
        "status": "ok",
        "database": postgres_health_check(),
    })
