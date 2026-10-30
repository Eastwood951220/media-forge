from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from backend.app.modules.scraping.paths import normalize_code
from shared.database.models.content import Movie


class UnsafeNasMovieFolder(ValueError):
    pass


@dataclass
class NasDeleteResult:
    deleted_folders: list[str] = field(default_factory=list)
    missing_folders: list[str] = field(default_factory=list)
    failed_folders: list[dict] = field(default_factory=list)


def resolve_nas_movie_folder(movie: Movie, config: Mapping[str, Any]) -> Path | None:
    if movie.scraping_status != "scraped":
        return None
    cloud_folder = str(movie.scraping_folder or "")
    media_root = str(config.get("media_root") or "/media")
    local_root = Path(str(config.get("scrape_root") or ""))
    if not cloud_folder.startswith("/") or not media_root.startswith("/") or not local_root.is_absolute() or not local_root.is_dir():
        raise UnsafeNasMovieFolder("刮削目录映射不可用")
    try:
        relative = PurePosixPath(cloud_folder).relative_to(PurePosixPath(media_root))
    except ValueError as exc:
        raise UnsafeNasMovieFolder("影片刮削目录不在媒体库根目录内") from exc
    if str(relative) == "." or any(part in {"..", "."} for part in relative.parts):
        raise UnsafeNasMovieFolder("不能删除刮削根目录或其上层目录")
    target = local_root.joinpath(*relative.parts)
    if normalize_code(target.name) != normalize_code(movie.code or "") or not movie.code:
        raise UnsafeNasMovieFolder("刮削文件夹与影片番号不匹配")
    root_real = local_root.resolve()
    current = local_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafeNasMovieFolder("不能删除符号链接目录")
    try:
        target.resolve().relative_to(root_real)
    except (OSError, RuntimeError, ValueError) as exc:
        raise UnsafeNasMovieFolder("刮削文件夹超出配置根目录") from exc
    if target.resolve() == root_real:
        raise UnsafeNasMovieFolder("不能删除刮削根目录")
    return target


def delete_nas_movie_folders(movies: list[Movie], config: Mapping[str, Any]) -> NasDeleteResult:
    targets: list[Path] = []
    for movie in movies:
        target = resolve_nas_movie_folder(movie, config)
        if target is not None and target not in targets:
            targets.append(target)
    validate_nas_targets(targets)
    result = NasDeleteResult()
    for target in targets:
        if not target.exists():
            result.missing_folders.append(str(target))
            continue
        try:
            shutil.rmtree(target)
            result.deleted_folders.append(str(target))
        except OSError as exc:
            result.failed_folders.append({"path": str(target), "error": str(exc)})
    return result


def validate_nas_targets(targets: list[Path]) -> None:
    for index, target in enumerate(targets):
        if any(index != other and (target in candidate.parents or candidate in target.parents) for other, candidate in enumerate(targets)):
            raise UnsafeNasMovieFolder("影片刮削目录相互包含，拒绝批量删除")
