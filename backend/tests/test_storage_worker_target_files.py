from dataclasses import dataclass

from backend.app.modules.storage.worker.target_files import (
    copy_existing_target_to_missing_targets,
    find_existing_target_files,
)


@dataclass
class RemoteFile:
    name: str
    full_path: str
    size: int
    is_directory: bool = False


class TargetProvider:
    def __init__(self) -> None:
        self.files = {
            "/Movies/A": [RemoteFile("ABC-123.mp4", "/Movies/A/ABC-123.mp4", 500)],
            "/Movies/B": [],
        }
        self.copied: list[tuple[str, str]] = []
        self.created: list[str] = []

    def list_files(self, path):
        return self.files.get(path, [])

    def ensure_directory(self, path):
        self.created.append(path)

    def copy_file(self, source, target_folder):
        self.copied.append((source, target_folder))


class Context:
    def __init__(self, provider) -> None:
        self.provider = provider
        self.logs = []

    def log(self, level, message, context=None, *, step=None, event=None):
        self.logs.append((level, message, context or {}, step, event))


def test_find_existing_target_files_reports_existing_and_missing_targets() -> None:
    provider = TargetProvider()

    result = find_existing_target_files(provider, ["/Movies/A", "/Movies/B"], ["ABC-123.mp4"])

    assert result.any_target_exists is True
    assert result.all_targets_exist is False
    assert result.existing_targets == ["/Movies/A"]
    assert result.missing_targets == ["/Movies/B"]
    assert result.source_path == "/Movies/A/ABC-123.mp4"
    assert result.source_name == "ABC-123.mp4"


def test_copy_existing_target_to_missing_targets_copies_from_first_existing_target() -> None:
    provider = TargetProvider()
    result = find_existing_target_files(provider, ["/Movies/A", "/Movies/B"], ["ABC-123.mp4"])

    copied = copy_existing_target_to_missing_targets(Context(provider), result)

    assert provider.created == ["/Movies/B"]
    assert provider.copied == [("/Movies/A/ABC-123.mp4", "/Movies/B")]
    assert copied[0]["copied_paths"] == ["/Movies/B/ABC-123.mp4"]
    assert copied[0]["copy_source"] == "/Movies/A/ABC-123.mp4"
