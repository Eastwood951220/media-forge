import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette import status

from shared.schemas.common import failure

logger = logging.getLogger(__name__)


def _detail_to_message_and_data(detail: Any) -> tuple[str, Any, int | None]:
    if isinstance(detail, dict):
        msg = detail.get("msg") or detail.get("message") or detail.get("detail") or "请求失败"
        code = detail.get("code")
        data = detail.get("data")
        return str(msg), data, int(code) if isinstance(code, int) else None
    if isinstance(detail, str) and detail:
        return detail, None, None
    if detail is None:
        return "请求失败", None, None
    return str(detail), detail, None


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        msg, data, body_code = _detail_to_message_and_data(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=failure(code=body_code or exc.status_code, msg=msg, data=data),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=failure(
                code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                msg="请求参数错误",
                data=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("Unhandled request error: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=failure(
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                msg="服务器内部错误",
                data=None,
            ),
        )
