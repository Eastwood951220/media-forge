from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel):
    """Standard API response wrapper."""

    code: int = 200
    msg: str = "success"
    data: Any = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    code: int = 200
    msg: str = "success"
    rows: list[T] = Field(default_factory=list)
    total: int = 0


def success(data: Any = None, msg: str = "success") -> dict:
    """Build a success response dict with data wrapper."""
    return {
        "code": 200,
        "msg": msg,
        "data": data,
    }


def paginated(
    rows: list[T],
    total: int,
    msg: str = "success",
) -> dict:
    """Build a paginated response dict."""
    return {
        "code": 200,
        "msg": msg,
        "rows": rows,
        "total": total,
    }


def failure(code: int = 500, msg: str = "error", data: Any = None) -> dict:
    """Build a failed response dict with the standard data wrapper."""
    return {
        "code": code,
        "msg": msg,
        "data": data,
    }
