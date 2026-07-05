from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


def ensure_directory_chain(provider, folder_path: str) -> None:
    provider.ensure_directory(folder_path)


def _target_file_path(target_folder: str, file_name: str) -> str:
    return str(PurePosixPath(target_folder) / file_name)


@dataclass
class ExistingTargetFilesResult:
    all_targets_exist: bool
    any_target_exists: bool
    checked_targets: list[str]
    existing_targets: list[str]
    missing_targets: list[str]
    expected_names: list[str]
    existing_files: list[dict]
    source_path: str | None = None
    source_name: str | None = None
    source_size: int = 0


def _listed_entry_to_target_file(entry) -> dict:
    path = getattr(entry, "full_path", "") or getattr(entry, "fullPathName", "")
    name = getattr(entry, "name", "") or PurePosixPath(path).name
    return {
        "name": name,
        "path": path,
        "size": int(getattr(entry, "size", 0) or 0),
        "is_dir": bool(getattr(entry, "is_directory", False) or getattr(entry, "isDirectory", False)),
    }


def find_existing_target_files(provider, target_paths: list[str], expected_names: list[str]) -> ExistingTargetFilesResult:
    normalized_expected = {str(name).lower() for name in expected_names if name}
    checked_targets: list[str] = []
    existing_targets: list[str] = []
    missing_targets: list[str] = []
    existing_files: list[dict] = []
    source_path: str | None = None
    source_name: str | None = None
    source_size = 0

    for target_folder in target_paths:
        checked_targets.append(target_folder)
        matched_file: dict | None = None
        try:
            entries = provider.list_files(target_folder)
        except Exception:
            entries = []

        for entry in entries:
            item = _listed_entry_to_target_file(entry)
            if item["is_dir"]:
                continue
            if item["size"] <= 0:
                continue
            if item["name"].lower() not in normalized_expected:
                continue
            matched_file = {
                "target_folder": target_folder,
                "path": item["path"] or _target_file_path(target_folder, item["name"]),
                "name": item["name"],
                "size": item["size"],
            }
            break

        if matched_file:
            existing_targets.append(target_folder)
            existing_files.append(matched_file)
            if source_path is None:
                source_path = matched_file["path"]
                source_name = matched_file["name"]
                source_size = int(matched_file["size"] or 0)
            continue

        missing_targets.append(target_folder)

    return ExistingTargetFilesResult(
        all_targets_exist=bool(target_paths) and len(existing_targets) == len(target_paths),
        any_target_exists=bool(existing_targets),
        checked_targets=checked_targets,
        existing_targets=existing_targets,
        missing_targets=missing_targets,
        expected_names=list(expected_names),
        existing_files=existing_files,
        source_path=source_path,
        source_name=source_name,
        source_size=source_size,
    )


def copy_existing_target_to_missing_targets(context, result: ExistingTargetFilesResult) -> list[dict]:
    if not result.source_path or not result.source_name:
        return []
    if not result.missing_targets:
        return []

    copied_paths: list[str] = []
    for target_folder in result.missing_targets:
        ensure_directory_chain(context.provider, target_folder)
        context.provider.copy_file(result.source_path, target_folder)
        copied_paths.append(_target_file_path(target_folder, result.source_name))

    moved_file = {
        "name": result.source_name,
        "path": result.source_path,
        "size": result.source_size,
        "renamed_name": result.source_name,
        "moved_path": result.source_path,
        "copied_paths": copied_paths,
        "copy_source": result.source_path,
        "copy_source_target": result.existing_targets[0] if result.existing_targets else "",
    }
    context.log(
        "INFO",
        "已从命中的目标文件复制到缺失目标",
        {
            "source": result.source_path,
            "source_target": moved_file["copy_source_target"],
            "missing_targets": result.missing_targets,
            "copied_paths": copied_paths,
        },
        step="move_files",
    )
    return [moved_file]
