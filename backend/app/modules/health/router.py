from fastapi import APIRouter

from shared.database.session import postgres_health_check

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health_check() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "database": postgres_health_check(),
    }
