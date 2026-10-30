from pathlib import Path

from backend.app.modules.jellyfin.refresh import (
    changed_strm_paths,
    refresh_libraries_for_paths,
    snapshot_strm_files,
    wait_for_strm_changes,
)


class FakeJellyfin:
    def __init__(self):
        self.refreshed = []

    def get_virtual_folders(self):
        return [
            {"Name": "日本", "ItemId": "lib-jp", "Locations": ["/media/日本"]},
            {"Name": "合集", "ItemId": "lib-all", "Locations": ["/media"]},
            {"Name": "欧美", "ItemId": "lib-other", "Locations": ["/media/欧美"]},
        ]

    def refresh_item(self, item_id):
        self.refreshed.append(item_id)
        if item_id == "lib-all":
            raise RuntimeError("busy")


def test_refreshes_every_matching_library_once_and_reports_partial_failure(tmp_path: Path) -> None:
    local_root = tmp_path / "日本"
    first = local_root / "愛那あい" / "CJOD-496-C" / "CJOD-496-C.strm"
    second = local_root / "別" / "ABC-123" / "ABC-123.strm"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("url", encoding="utf-8")
    second.write_text("url", encoding="utf-8")
    client = FakeJellyfin()
    result = refresh_libraries_for_paths(
        {"scrape_root": str(local_root), "media_root": "/media/日本"},
        [first, second], client=client,
    )
    assert client.refreshed == ["lib-jp", "lib-all"]
    assert [(item.library_id, item.accepted) for item in result] == [
        ("lib-jp", True), ("lib-all", False),
    ]


def test_new_strm_file_is_detected_after_external_job_acceptance(tmp_path: Path) -> None:
    root = tmp_path / "media"
    root.mkdir()
    before = snapshot_strm_files(root)
    folder = root / "CJOD-496-C"
    folder.mkdir()
    strm = folder / "CJOD-496-C.strm"
    strm.write_text("url", encoding="utf-8")
    assert changed_strm_paths(before, snapshot_strm_files(root)) == [strm]


def test_auto_refresh_waits_for_later_files_in_same_generation(tmp_path: Path) -> None:
    a = tmp_path / "A.strm"
    b = tmp_path / "B.strm"
    snapshots = iter([
        {}, {a: (1, 1)}, {a: (1, 1), b: (2, 1)},
        {a: (1, 1), b: (2, 1)}, {a: (1, 1), b: (2, 1)},
    ])
    changed = wait_for_strm_changes(
        tmp_path, {}, poll_seconds=0, max_polls=5, quiet_polls=2,
        sleep_fn=lambda _seconds: None, snapshot_fn=lambda _root: next(snapshots),
    )
    assert changed == [a, b]
