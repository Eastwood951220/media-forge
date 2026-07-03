from dataclasses import dataclass

from backend.app.modules.storage.worker.file_finder import find_existing_video_files
from backend.app.modules.storage.worker.steps import select_main_videos


@dataclass
class FakeRemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool = False
    is_search_result: bool = False


class FakeProvider:
    def __init__(self) -> None:
        self.search_calls = []
        self.original_paths = {"/Search/ABC-123-C.mp4": "/Movies/A/ABC-123-C.mp4"}

    def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
        self.search_calls.append((term, path))
        return [FakeRemoteFile("ABC-123-C.mp4", "/Search/ABC-123-C.mp4", 500 * 1024 * 1024, False, True)]

    def get_original_path(self, path):
        return self.original_paths[path]

    def list_files(self, path, force_refresh=False):
        return []


def test_find_existing_video_files_uses_search_and_original_path() -> None:
    provider = FakeProvider()

    files = find_existing_video_files(
        provider,
        search_terms=["ABC-123"],
        search_paths=["/Downloads"],
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert files[0]["path"] == "/Movies/A/ABC-123-C.mp4"
    assert provider.search_calls == [("ABC-123", "/Downloads")]


def test_select_main_videos_requires_video_extension_and_min_size() -> None:
    files = [
        {"name": "small.mp4", "path": "/a/small.mp4", "size": 20 * 1024 * 1024},
        {"name": "main.mkv", "path": "/a/main.mkv", "size": 900 * 1024 * 1024},
    ]

    selected = select_main_videos(files, {"video_extensions": [".mp4", ".mkv"], "minimum_video_size_mb": 100})

    assert selected == [{"name": "main.mkv", "path": "/a/main.mkv", "size": 900 * 1024 * 1024}]
