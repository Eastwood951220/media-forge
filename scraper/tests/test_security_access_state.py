from scraper.core.security import detect_access_state, get_response_status, is_security_check_page


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class FakePage:
    def __init__(self, text: str = "", status=None, status_code=None, response=None, metadata=None):
        self.text = text
        if status is not None:
            self.status = status
        if status_code is not None:
            self.status_code = status_code
        if response is not None:
            self.response = response
        if metadata is not None:
            self.metadata = metadata


def test_get_response_status_reads_direct_status_code() -> None:
    assert get_response_status(FakePage(status_code=403)) == 403


def test_get_response_status_reads_nested_response_status_code() -> None:
    assert get_response_status(FakePage(response=FakeResponse(429))) == 429


def test_get_response_status_reads_metadata_status() -> None:
    assert get_response_status(FakePage(metadata={"status": 403})) == 403


def test_detect_access_state_blocks_403() -> None:
    state = detect_access_state(FakePage(status_code=403, text="Forbidden"))

    assert state.ok is False
    assert state.status_code == 403
    assert state.reason == "http_403"
    assert "403" in state.message
    assert is_security_check_page(FakePage(status_code=403)) is True


def test_detect_access_state_blocks_429() -> None:
    state = detect_access_state(FakePage(status_code=429, text="Too many requests"))

    assert state.ok is False
    assert state.status_code == 429
    assert state.reason == "http_429"
    assert "429" in state.message


def test_detect_access_state_blocks_security_keywords() -> None:
    state = detect_access_state(FakePage(text="请完成安全检查后继续"))

    assert state.ok is False
    assert state.reason == "security_keywords"
    assert is_security_check_page(FakePage(text="captcha required")) is True


def test_detect_access_state_allows_normal_page() -> None:
    state = detect_access_state(FakePage(status_code=200, text="JavDB 成人影片數據庫"))

    assert state.ok is True
    assert state.status_code == 200
    assert state.reason == "ok"
