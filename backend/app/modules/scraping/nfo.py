from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from backend.app.modules.scraping.paths import normalize_code
from shared.database.models.content import Movie

XML_DECLARATION = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'


def _title(movie: Movie) -> str:
    name = str(movie.source_name or "").strip()
    code = str(movie.code or "").upper()
    if not name:
        return code
    if normalize_code(name).startswith(normalize_code(code)):
        return name
    return f"{code} {name}".strip()


def _original_title(movie: Movie) -> str:
    name = str(movie.source_name or "").strip()
    code = str(movie.code or "").strip()
    if not name or not code:
        return name
    stripped = re.sub(rf"^{re.escape(code)}[\s\-_ ]*", "", name, flags=re.IGNORECASE).strip()
    return stripped or name


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def render_movie_nfo(
    movie: Movie,
    *,
    cloud_folder: str,
    source_site: str | None = None,
    dateadded: datetime | None = None,
) -> str:
    root = ET.Element("movie")
    ET.SubElement(root, "plot")
    ET.SubElement(root, "lockdata").text = "false"
    ET.SubElement(root, "dateadded").text = (dateadded or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    ET.SubElement(root, "title").text = _title(movie)
    ET.SubElement(root, "originaltitle").text = _original_title(movie)

    release_date = movie.release_date
    if release_date is not None:
        ET.SubElement(root, "year").text = str(release_date.year)
    ET.SubElement(root, "mpaa").text = "JP-18+"
    if release_date is not None:
        premiered = release_date.isoformat()
        ET.SubElement(root, "premiered").text = premiered
        ET.SubElement(root, "releasedate").text = premiered
        ET.SubElement(root, "tagline").text = f"配信開始日 {premiered}"

    for genre in _dedupe(list(movie.tags or [])):
        ET.SubElement(root, "genre").text = genre

    maker = str(movie.maker or "").strip()
    if maker:
        ET.SubElement(root, "studio").text = maker

    for tag in _dedupe([maker, str(movie.series or ""), *list(movie.tags or [])]):
        ET.SubElement(root, "tag").text = tag

    for actor in _dedupe(list(movie.actors or [])):
        actor_node = ET.SubElement(root, "actor")
        ET.SubElement(actor_node, "name").text = actor

    if source_site:
        ET.SubElement(root, "metatubeid").text = f"{source_site}:{movie.code}"

    art = ET.SubElement(root, "art")
    folder = str(cloud_folder or "").rstrip("/")
    ET.SubElement(art, "poster").text = f"{folder}/folder.jpg"
    ET.SubElement(art, "fanart").text = f"{folder}/backdrop.jpg"

    series = str(movie.series or "").strip()
    if series:
        set_node = ET.SubElement(root, "set")
        ET.SubElement(set_node, "name").text = series

    fileinfo = ET.SubElement(root, "fileinfo")
    ET.SubElement(fileinfo, "streamdetails")

    ET.indent(root, space="  ")
    return XML_DECLARATION + ET.tostring(root, encoding="unicode") + "\n"


def write_movie_nfo(
    folder: Path,
    movie: Movie,
    *,
    cloud_folder: str,
    source_site: str | None = None,
) -> None:
    text = render_movie_nfo(movie, cloud_folder=cloud_folder, source_site=source_site)
    target = Path(folder) / "movie.nfo"
    temp = target.with_suffix(".nfo.tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(target)
