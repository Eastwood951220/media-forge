import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from backend.app.models.crawl_task import CrawlTask
from backend.scripts.backfill_actress_tags_from_task_exports import (
    backfill_actress_tags_from_task_exports,
    read_xlsx_rows,
)
from shared.database.models.content import ActressProfile, ActressTag


def _write_xlsx(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    _write_xlsx_with_options(path, headers, rows, include_cell_refs=True)


def _write_xlsx_with_options(
    path: Path,
    headers: list[str],
    rows: list[list[str]],
    *,
    include_cell_refs: bool,
) -> None:
    all_rows = [headers, *rows]
    sheet_rows = []
    for row_index, row in enumerate(all_rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            column = chr(ord("A") + column_index)
            ref = f' r="{column}{row_index}"' if include_cell_refs else ""
            cells.append(
                f'<c{ref} t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""")
        archive.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""")
        archive.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Result 1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""")
        archive.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""")
        archive.writestr("xl/worksheets/sheet1.xml", f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{"".join(sheet_rows)}</sheetData>
</worksheet>""")


def _seed_task(db_session, owner, task_id: uuid.UUID | None = None) -> CrawlTask:
    task = CrawlTask(
        id=task_id or uuid.uuid4(),
        name="actress task",
        storage_location="actress task",
        owner_id=owner.id,
    )
    db_session.add(task)
    db_session.flush()
    return task


def test_read_xlsx_rows_reads_first_result_sheet(tmp_path: Path) -> None:
    workbook = tmp_path / "rows.xlsx"
    _write_xlsx(workbook, ["id", "name"], [["1", "巨乳"], ["2", "熟女"]])

    assert read_xlsx_rows(workbook) == [{"id": "1", "name": "巨乳"}, {"id": "2", "name": "熟女"}]


def test_read_xlsx_rows_handles_cells_without_coordinates(tmp_path: Path) -> None:
    workbook = tmp_path / "rows-without-refs.xlsx"
    _write_xlsx_with_options(
        workbook,
        ["task_id", "tag_id"],
        [["task-1", "tag-1"], ["task-2", "tag-2"]],
        include_cell_refs=False,
    )

    assert read_xlsx_rows(workbook) == [
        {"task_id": "task-1", "tag_id": "tag-1"},
        {"task_id": "task-2", "tag_id": "tag-2"},
    ]


def test_backfill_actress_tags_from_task_exports_appends_task_tags(
    db_session,
    test_user,
    tmp_path: Path,
) -> None:
    task = _seed_task(db_session, test_user)
    profile = ActressProfile(
        display_name="Test Actress",
        canonical_names=["Test Actress"],
        source_url="https://example.test/actress",
        source_task_ids=[task.id],
        source_task_url_ids=[],
    )
    existing_tag = ActressTag(owner_id=test_user.id, name="已有标签")
    profile.tags = [existing_tag]
    db_session.add_all([profile, existing_tag])
    db_session.commit()
    tags_path = tmp_path / "crawl_task_tags.xlsx"
    links_path = tmp_path / "crawl_task_tag_links.xlsx"
    tag_id = uuid.uuid4()
    _write_xlsx(tags_path, ["id", "owner_id", "name"], [[str(tag_id), str(test_user.id), " 巨乳 "]])
    _write_xlsx(links_path, ["task_id", "tag_id"], [[str(task.id), str(tag_id)]])
    lines: list[str] = []

    result = backfill_actress_tags_from_task_exports(
        db_session,
        tag_links_path=links_path,
        tags_path=tags_path,
        dry_run=False,
        reporter=lines.append,
    )
    db_session.refresh(profile)

    assert result.links_created == 1
    assert result.tags_created == 1
    assert sorted(tag.name for tag in profile.tags) == ["巨乳", "已有标签"]
    assert any("status=linked" in line and str(profile.id) in line for line in lines)


def test_backfill_actress_tags_from_task_exports_reports_missing_profile(
    db_session,
    test_user,
    tmp_path: Path,
) -> None:
    task = _seed_task(db_session, test_user)
    tags_path = tmp_path / "crawl_task_tags.xlsx"
    links_path = tmp_path / "crawl_task_tag_links.xlsx"
    tag_id = uuid.uuid4()
    _write_xlsx(tags_path, ["id", "owner_id", "name"], [[str(tag_id), str(test_user.id), "企划"]])
    _write_xlsx(links_path, ["task_id", "tag_id"], [[str(task.id), str(tag_id)]])
    lines: list[str] = []

    result = backfill_actress_tags_from_task_exports(
        db_session,
        tag_links_path=links_path,
        tags_path=tags_path,
        dry_run=False,
        reporter=lines.append,
    )

    assert result.links_created == 0
    assert result.skipped_no_profile == 1
    assert any("status=no_actress_profile" in line and str(task.id) in line for line in lines)
