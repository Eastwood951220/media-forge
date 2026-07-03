from datetime import datetime

from backend.app.modules.storage.tasks.policies import (
    build_video_filename,
    code_folder_from_filename,
    generate_default_alias,
    order_magnet_candidates,
)


def test_generate_default_alias() -> None:
    alias = generate_default_alias(datetime(2026, 7, 4, 11, 22, 33), 7)
    assert alias == "云存储_20260704112233_0007"


def test_order_magnet_candidates_selected_first_then_weight() -> None:
    magnets = [
        {"id": "low", "weight": 1, "selected": False},
        {"id": "selected", "weight": 2, "selected": True},
        {"id": "high", "weight": 99, "selected": False},
    ]

    assert [m["id"] for m in order_magnet_candidates(magnets, max_attempts=3)] == [
        "selected",
        "high",
        "low",
    ]


def test_order_magnet_candidates_limits_attempts() -> None:
    magnets = [
        {"id": "selected", "weight": 1, "selected": True},
        {"id": "high", "weight": 99, "selected": False},
        {"id": "middle", "weight": 50, "selected": False},
    ]

    assert [m["id"] for m in order_magnet_candidates(magnets, max_attempts=2)] == [
        "selected",
        "high",
    ]


def test_build_video_filename_uppercase_suffix_and_disc() -> None:
    filename = build_video_filename(
        movie_code="abc-123",
        original_name="XXX.part2.mp4",
        tags=["中文字幕", "无码破解"],
        index=1,
        total=3,
    )

    assert filename == "ABC-123-UC-CD2.mp4"
    assert code_folder_from_filename(filename) == "ABC-123-UC"


def test_build_video_filename_single_chinese() -> None:
    assert build_video_filename("abc-123", "movie.mkv", ["中字"], 0, 1) == "ABC-123-C.mkv"
