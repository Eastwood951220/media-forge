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


def test_order_selected_videos_uses_differing_numeric_token_before_shared_suffix_number() -> None:
    from backend.app.modules.storage.tasks.policies import order_selected_videos_for_rename

    videos = [
        {"name": "4k2.com@vrkm01668_10_12000.mp4", "path": "/d/4k2.com@vrkm01668_10_12000.mp4"},
        {"name": "4k2.com@vrkm01668_1_12000.mp4", "path": "/d/4k2.com@vrkm01668_1_12000.mp4"},
        {"name": "4k2.com@vrkm01668_2_12000.mp4", "path": "/d/4k2.com@vrkm01668_2_12000.mp4"},
    ]

    ordered = order_selected_videos_for_rename(videos)

    assert [item["name"] for item in ordered] == [
        "4k2.com@vrkm01668_1_12000.mp4",
        "4k2.com@vrkm01668_2_12000.mp4",
        "4k2.com@vrkm01668_10_12000.mp4",
    ]


def test_order_selected_videos_falls_back_to_natural_filename_sort() -> None:
    from backend.app.modules.storage.tasks.policies import order_selected_videos_for_rename

    videos = [
        {"name": "sample-10-extra-2.mp4", "path": "/d/b.mp4"},
        {"name": "sample-2-extra-10.mp4", "path": "/d/a.mp4"},
        {"name": "sample-1-extra-20.mp4", "path": "/d/c.mp4"},
    ]

    ordered = order_selected_videos_for_rename(videos)

    assert [item["name"] for item in ordered] == [
        "sample-1-extra-20.mp4",
        "sample-2-extra-10.mp4",
        "sample-10-extra-2.mp4",
    ]


def test_infer_disc_number_preserves_explicit_markers_and_bare_part_tokens() -> None:
    from backend.app.modules.storage.tasks.policies import infer_disc_number

    assert infer_disc_number("XXX.part2.mp4", 0) == 2
    assert infer_disc_number("XXX-cd03.mp4", 0) == 3
    assert infer_disc_number("XXX disc 4.mp4", 0) == 4
    assert infer_disc_number("XXX_B.mp4", 0) == 2
    assert infer_disc_number("4k2.com@vrkm01668_10_12000.mp4", 0) == 10
