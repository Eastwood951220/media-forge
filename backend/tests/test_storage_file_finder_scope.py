from dataclasses import dataclass


@dataclass
class FakeRemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool = False
    is_search_result: bool = False


class ScopedSearchProvider:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, str]] = []
        self.list_calls: list[str] = []
        self.original_paths = {
            "/Search/ACZD-165.mp4": "/Downloads/storage_sub/ACZD-165.mp4",
            "/Search/MIDA-628.mp4": "/Downloads/storage_old/MIDA-628.mp4",
        }

    def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
        self.search_calls.append((term, path))
        return [
            FakeRemoteFile("ACZD-165.mp4", "/Search/ACZD-165.mp4", 500 * 1024 * 1024, False, True),
            FakeRemoteFile("MIDA-628.mp4", "/Search/MIDA-628.mp4", 500 * 1024 * 1024, False, True),
            FakeRemoteFile("ACZD-165.txt", "/Downloads/storage_sub/ACZD-165.txt", 1024, False, False),
        ]

    def get_original_path(self, path):
        return self.original_paths.get(path, "")

    def list_files(self, path, force_refresh=False):
        self.list_calls.append(path)
        return []


def test_scoped_search_logs_raw_resolved_accepted_and_rejected_files() -> None:
    from backend.app.modules.storage.worker.file_finder import find_scoped_video_files

    provider = ScopedSearchProvider()

    result = find_scoped_video_files(
        provider=provider,
        search_terms=["ACZD-165"],
        search_path="/Downloads/storage_sub",
        search_scope="task_download_folder",
        movie_code="ACZD-165",
        task_download_folder="/Downloads/storage_sub",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert provider.search_calls == [("ACZD-165", "/Downloads/storage_sub")]
    assert [file["path"] for file in result.accepted_files] == ["/Downloads/storage_sub/ACZD-165.mp4"]
    assert result.log_context["search_term"] == "ACZD-165"
    assert result.log_context["search_path"] == "/Downloads/storage_sub"
    assert result.log_context["search_scope"] == "task_download_folder"
    assert result.log_context["search_method"] == "search_files"
    assert result.log_context["raw_results"] == [
        {"name": "ACZD-165.mp4", "path": "/Search/ACZD-165.mp4", "size": 524288000},
        {"name": "MIDA-628.mp4", "path": "/Search/MIDA-628.mp4", "size": 524288000},
        {"name": "ACZD-165.txt", "path": "/Downloads/storage_sub/ACZD-165.txt", "size": 1024},
    ]
    assert result.log_context["resolved_results"] == [
        {"name": "ACZD-165.mp4", "path": "/Downloads/storage_sub/ACZD-165.mp4", "size": 524288000},
        {"name": "MIDA-628.mp4", "path": "/Downloads/storage_old/MIDA-628.mp4", "size": 524288000},
        {"name": "ACZD-165.txt", "path": "/Downloads/storage_sub/ACZD-165.txt", "size": 1024},
    ]
    assert result.log_context["accepted_files"] == [
        {"name": "ACZD-165.mp4", "path": "/Downloads/storage_sub/ACZD-165.mp4", "size": 524288000}
    ]
    assert result.log_context["rejected_files"] == [
        {
            "name": "MIDA-628.mp4",
            "path": "/Downloads/storage_old/MIDA-628.mp4",
            "size": 524288000,
            "reason": "movie_code_mismatch",
        },
        {
            "name": "ACZD-165.txt",
            "path": "/Downloads/storage_sub/ACZD-165.txt",
            "size": 1024,
            "reason": "extension_not_allowed",
        },
    ]


class RootSearchProvider:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, str]] = []
        self.original_paths = {
            "/Search/CHERD-105.mp4": "/Downloads/storage_old/CHERD-105/CHERD-105.mp4",
            "/Search/ACZD-165.mp4": "/Downloads/storage_other/ACZD-165/ACZD-165.mp4",
        }

    def search_files(self, term, path="/", force_refresh=False, fuzzy_match=False):
        self.search_calls.append((term, path))
        return [
            FakeRemoteFile("CHERD-105.mp4", "/Search/CHERD-105.mp4", 900 * 1024 * 1024, False, True),
            FakeRemoteFile("ACZD-165.mp4", "/Search/ACZD-165.mp4", 900 * 1024 * 1024, False, True),
        ]

    def get_original_path(self, path):
        return self.original_paths.get(path, "")

    def list_files(self, path, force_refresh=False):
        return []


def test_root_recovery_rejects_other_movie_codes() -> None:
    from backend.app.modules.storage.worker.file_finder import find_scoped_video_files

    provider = RootSearchProvider()

    result = find_scoped_video_files(
        provider=provider,
        search_terms=["ACZD-165"],
        search_path="/Downloads",
        search_scope="download_root",
        movie_code="ACZD-165",
        task_download_folder="/Downloads/storage_sub",
        config={"video_extensions": [".mp4"], "minimum_video_size_mb": 100},
    )

    assert provider.search_calls == [("ACZD-165", "/Downloads")]
    assert [file["path"] for file in result.accepted_files] == [
        "/Downloads/storage_other/ACZD-165/ACZD-165.mp4"
    ]
    assert result.log_context["rejected_files"] == [
        {
            "name": "CHERD-105.mp4",
            "path": "/Downloads/storage_old/CHERD-105/CHERD-105.mp4",
            "size": 943718400,
            "reason": "movie_code_mismatch",
        }
    ]
