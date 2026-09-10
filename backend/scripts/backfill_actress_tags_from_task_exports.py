from __future__ import annotations

import argparse
import re
import sys
import uuid
import zipfile
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.models.crawl_task import CrawlTask
from backend.app.modules.content.actresses.tag_service import normalize_actress_tag_names
from shared.database.models.content import ActressProfile, ActressTag
from shared.database.session import get_session_factory
from shared.runtime_config import load_runtime_config

DEFAULT_TAG_LINKS_PATH = Path("/Users/eastwood-mac/crawl_task_tag_links.xlsx")
DEFAULT_TAGS_PATH = Path("/Users/eastwood-mac/crawl_task_tags.xlsx")
_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass
class ActressTagBackfillResult:
    tag_rows: int = 0
    link_rows: int = 0
    profiles_matched: int = 0
    tags_created: int = 0
    links_created: int = 0
    links_existing: int = 0
    skipped_unknown_tag: int = 0
    skipped_invalid_tag: int = 0
    skipped_missing_task: int = 0
    skipped_no_profile: int = 0


def _cell_column(ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", ref.upper())
    value = 0
    for letter in letters:
        value = value * 26 + ord(letter) - ord("A") + 1
    return value - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        data = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(data)
    values = []
    for item in root.findall("main:si", _NS):
        values.append("".join(text.text or "" for text in item.findall(".//main:t", _NS)))
    return values


def _workbook_sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_paths = {
        rel.attrib["Id"]: rel.attrib["Target"].lstrip("/")
        for rel in rels
        if rel.attrib.get("Type", "").endswith("/worksheet")
    }
    sheets: dict[str, str] = {}
    rel_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for sheet in workbook.findall(".//main:sheet", _NS):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[rel_key]
        target = rel_paths[rel_id]
        sheets[name] = target if target.startswith("xl/") else f"xl/{target}"
    return sheets


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//main:t", _NS))
    value = cell.find("main:v", _NS)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        return shared_strings[int(value.text)]
    return value.text


def read_xlsx_rows(path: Path, sheet_name: str = "Result 1") -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        sheet_paths = _workbook_sheet_paths(archive)
        if sheet_name not in sheet_paths:
            available = ", ".join(sheet_paths)
            raise ValueError(f"workbook {path} does not contain sheet {sheet_name!r}; available: {available}")
        shared_strings = _shared_strings(archive)
        root = ElementTree.fromstring(archive.read(sheet_paths[sheet_name]))

    rows: list[list[str]] = []
    for row in root.findall(".//main:row", _NS):
        values: list[str] = []
        for fallback_column, cell in enumerate(row.findall("main:c", _NS)):
            column = _cell_column(cell.attrib["r"]) if "r" in cell.attrib else fallback_column
            while len(values) <= column:
                values.append("")
            values[column] = _cell_value(cell, shared_strings)
        rows.append(values)
    if not rows:
        return []
    headers = [value.strip() for value in rows[0]]
    return [
        {headers[index]: value.strip() for index, value in enumerate(row) if index < len(headers) and headers[index]}
        for row in rows[1:]
        if any(value.strip() for value in row)
    ]


def _parse_uuid(raw_value: str | None) -> uuid.UUID | None:
    if raw_value is None or not str(raw_value).strip():
        return None
    return uuid.UUID(str(raw_value).strip())


def _report(reporter: Callable[[str], None] | None, message: str) -> None:
    if reporter is not None:
        reporter(message)


def _get_or_create_tag(
    db: Session,
    *,
    owner_id: uuid.UUID,
    name: str,
    dry_run: bool,
    result: ActressTagBackfillResult,
) -> ActressTag:
    tag = db.scalar(select(ActressTag).where(ActressTag.owner_id == owner_id, ActressTag.name == name))
    if tag is not None:
        return tag
    tag = ActressTag(owner_id=owner_id, name=name)
    result.tags_created += 1
    if not dry_run:
        db.add(tag)
        db.flush()
    else:
        tag.id = uuid.uuid4()
    return tag


def backfill_actress_tags_from_task_exports(
    db: Session,
    *,
    tag_links_path: Path = DEFAULT_TAG_LINKS_PATH,
    tags_path: Path = DEFAULT_TAGS_PATH,
    dry_run: bool = True,
    reporter: Callable[[str], None] | None = print,
) -> ActressTagBackfillResult:
    result = ActressTagBackfillResult()
    tag_rows = read_xlsx_rows(tags_path)
    link_rows = read_xlsx_rows(tag_links_path)
    result.tag_rows = len(tag_rows)
    result.link_rows = len(link_rows)

    legacy_tags: dict[uuid.UUID, str] = {}
    for row in tag_rows:
        tag_id = _parse_uuid(row.get("id"))
        if tag_id is None:
            continue
        try:
            names = normalize_actress_tag_names([row.get("name") or ""])
        except Exception:
            result.skipped_invalid_tag += 1
            _report(reporter, f"status=invalid_tag ok=false legacy_tag_id={tag_id} name={row.get('name') or '-'}")
            continue
        if not names:
            result.skipped_invalid_tag += 1
            _report(reporter, f"status=invalid_tag ok=false legacy_tag_id={tag_id} name={row.get('name') or '-'}")
            continue
        legacy_tags[tag_id] = names[0]

    task_ids = {
        task_id
        for row in link_rows
        if (task_id := _parse_uuid(row.get("task_id"))) is not None
    }
    tasks = list(db.scalars(select(CrawlTask).where(CrawlTask.id.in_(task_ids)))) if task_ids else []
    tasks_by_id = {task.id: task for task in tasks}
    profiles = list(db.scalars(select(ActressProfile)).unique())
    profiles_by_task_id: dict[uuid.UUID, list[ActressProfile]] = defaultdict(list)
    for profile in profiles:
        for task_id in profile.source_task_ids or []:
            profiles_by_task_id[_parse_uuid(str(task_id))].append(profile)

    matched_profile_ids: set[uuid.UUID] = set()
    for row_index, row in enumerate(link_rows, start=2):
        task_id = _parse_uuid(row.get("task_id"))
        legacy_tag_id = _parse_uuid(row.get("tag_id"))
        tag_name = legacy_tags.get(legacy_tag_id) if legacy_tag_id is not None else None
        if task_id is None or legacy_tag_id is None or tag_name is None:
            result.skipped_unknown_tag += 1
            _report(
                reporter,
                f"status=unknown_tag ok=false row={row_index} task_id={row.get('task_id') or '-'} tag_id={row.get('tag_id') or '-'}",
            )
            continue
        task = tasks_by_id.get(task_id)
        if task is None:
            result.skipped_missing_task += 1
            _report(reporter, f"status=missing_task ok=false row={row_index} task_id={task_id} tag={tag_name}")
            continue
        matched_profiles = profiles_by_task_id.get(task_id, [])
        if not matched_profiles:
            result.skipped_no_profile += 1
            _report(reporter, f"status=no_actress_profile ok=false row={row_index} task_id={task_id} tag={tag_name}")
            continue

        tag = _get_or_create_tag(db, owner_id=task.owner_id, name=tag_name, dry_run=dry_run, result=result)
        for profile in matched_profiles:
            matched_profile_ids.add(profile.id)
            existing_tag_ids = {existing.id for existing in profile.tags}
            if tag.id in existing_tag_ids:
                result.links_existing += 1
                _report(
                    reporter,
                    f"status=already_linked ok=true row={row_index} profile_id={profile.id} task_id={task_id} tag={tag_name}",
                )
                continue
            result.links_created += 1
            if not dry_run:
                profile.tags = [*profile.tags, tag]
            _report(
                reporter,
                f"status=linked ok=true row={row_index} profile_id={profile.id} task_id={task_id} tag={tag_name}",
            )

    result.profiles_matched = len(matched_profile_ids)
    if not dry_run and (result.links_created or result.tags_created):
        db.commit()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag-links", type=Path, default=DEFAULT_TAG_LINKS_PATH)
    parser.add_argument("--tags", type=Path, default=DEFAULT_TAGS_PATH)
    parser.add_argument("--execute", action="store_true", help="正式写入；默认只 dry-run")
    parser.add_argument("--quiet", action="store_true", help="只输出最终汇总")
    args = parser.parse_args()

    load_runtime_config(override=True)
    db = get_session_factory()()
    try:
        result = backfill_actress_tags_from_task_exports(
            db,
            tag_links_path=args.tag_links,
            tags_path=args.tags,
            dry_run=not args.execute,
            reporter=None if args.quiet else print,
        )
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
