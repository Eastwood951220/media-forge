from backend.app.modules.storage.worker.timeline import PIPELINE_STEPS, STEP_LABELS, classify_scanned_files


def test_pipeline_steps_match_original_storage_flow() -> None:
    assert PIPELINE_STEPS == [
        "prepare",
        "submit_magnet",
        "waiting_download",
        "scan_files",
        "select_videos",
        "rename_files",
        "move_files",
        "verify_result",
        "cleanup_files",
    ]
    assert STEP_LABELS["prepare"] == "准备任务"
    assert STEP_LABELS["submit_magnet"] == "提交磁力"
    assert STEP_LABELS["waiting_download"] == "云端下载"
    assert STEP_LABELS["scan_files"] == "扫描文件"
    assert STEP_LABELS["select_videos"] == "识别主视频"
    assert STEP_LABELS["rename_files"] == "重命名"
    assert STEP_LABELS["move_files"] == "移动文件"
    assert STEP_LABELS["verify_result"] == "校验结果"
    assert STEP_LABELS["cleanup_files"] == "清理临时文件"


def test_classify_scanned_files_counts_original_categories() -> None:
    scanned = [
        {"name": "ABC-001.mp4", "path": "/d/ABC-001.mp4", "size": 200 * 1024 * 1024},
        {"name": "sample.mp4", "path": "/d/sample.mp4", "size": 5 * 1024 * 1024},
        {"name": "ABC-001.srt", "path": "/d/ABC-001.srt", "size": 1000},
        {"name": "cover.jpg", "path": "/d/cover.jpg", "size": 1000},
        {"name": "readme.txt", "path": "/d/readme.txt", "size": 1000},
    ]
    result = classify_scanned_files(
        scanned,
        {
            "video_extensions": [".mp4", ".mkv"],
            "minimum_video_size_mb": 100,
            "excluded_filename_keywords": ["sample"],
        },
    )

    assert [item["name"] for item in result.selected_videos] == ["ABC-001.mp4"]
    assert [item["name"] for item in result.excluded_files] == ["sample.mp4"]
    assert [item["name"] for item in result.subtitle_files] == ["ABC-001.srt"]
    assert [item["name"] for item in result.cover_files] == ["cover.jpg"]
    assert [item["name"] for item in result.other_files] == ["readme.txt"]
