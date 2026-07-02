"""Tests for shared.schemas.common response helpers."""

from shared.schemas.common import ApiResponse, PaginatedResponse, paginated, success


class TestSuccessFunction:
    """Tests for the success() helper."""

    def test_success_returns_dict_with_code_msg_data(self) -> None:
        data = {"id": 1, "name": "test"}
        result = success(data=data)

        assert result["code"] == 200
        assert result["msg"] == "success"
        assert result["data"] == data

    def test_success_with_none_data(self) -> None:
        result = success()

        assert result["code"] == 200
        assert result["msg"] == "success"
        assert result["data"] is None

    def test_success_with_custom_msg(self) -> None:
        result = success(data="ok", msg="操作成功")

        assert result["code"] == 200
        assert result["msg"] == "操作成功"
        assert result["data"] == "ok"


class TestPaginatedFunction:
    """Tests for the paginated() helper."""

    def test_paginated_returns_dict_with_rows_and_total(self) -> None:
        rows = [{"id": 1, "name": "item-1"}, {"id": 2, "name": "item-2"}]
        result = paginated(rows=rows, total=50)

        assert result["code"] == 200
        assert result["msg"] == "success"
        assert result["rows"] == rows
        assert result["total"] == 50

    def test_paginated_with_empty_rows(self) -> None:
        result = paginated(rows=[], total=0)

        assert result["code"] == 200
        assert result["rows"] == []
        assert result["total"] == 0

    def test_paginated_preserves_row_order(self) -> None:
        rows = [{"id": 3}, {"id": 1}, {"id": 2}]
        result = paginated(rows=rows, total=3)

        assert result["rows"] == [{"id": 3}, {"id": 1}, {"id": 2}]

    def test_paginated_with_custom_msg(self) -> None:
        rows = [{"id": 1}]
        result = paginated(rows=rows, total=1, msg="查询成功")

        assert result["code"] == 200
        assert result["msg"] == "查询成功"
        assert result["rows"] == rows
        assert result["total"] == 1


class TestApiResponseModel:
    """Tests for the ApiResponse Pydantic model."""

    def test_default_values(self) -> None:
        response = ApiResponse()

        assert response.code == 200
        assert response.msg == "success"
        assert response.data is None

    def test_with_data(self) -> None:
        data = {"id": 1, "name": "test"}
        response = ApiResponse(data=data)

        assert response.code == 200
        assert response.msg == "success"
        assert response.data == data

    def test_model_serialization(self) -> None:
        data = {"id": 1}
        response = ApiResponse(data=data)
        result = response.model_dump()

        assert result["code"] == 200
        assert result["msg"] == "success"
        assert result["data"] == data


class TestPaginatedResponseModel:
    """Tests for the PaginatedResponse Pydantic model."""

    def test_default_values(self) -> None:
        response = PaginatedResponse()

        assert response.code == 200
        assert response.msg == "success"
        assert response.rows == []
        assert response.total == 0

    def test_with_data(self) -> None:
        rows = [{"id": 1, "name": "test"}]
        response = PaginatedResponse(rows=rows, total=1)

        assert response.code == 200
        assert response.msg == "success"
        assert response.rows == rows
        assert response.total == 1

    def test_model_serialization(self) -> None:
        rows = [{"id": 1}]
        response = PaginatedResponse(rows=rows, total=1)
        data = response.model_dump()

        assert data["code"] == 200
        assert data["msg"] == "success"
        assert data["rows"] == rows
        assert data["total"] == 1
