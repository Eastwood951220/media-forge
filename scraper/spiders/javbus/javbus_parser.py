import re
from typing import Any
from urllib.parse import urljoin

from scrapling.parser import Adaptor

from scraper.core.utils import clean_text

FIELD_MAPPING = {
    "識別碼": "code",
    "發行日期": "release_date",
    "長度": "duration",
    "導演": "director",
    "發行商": "maker",
    "系列": "series",
    "類別": "tags",
    "演員": "actors",
}


def _first_text(node, selector: str) -> str:
    value = node.css(selector).get()
    return str(clean_text(value)) if value else ""


def _all_text(node, selector: str) -> list[str]:
    values = node.css(selector).getall()
    return [str(clean_text(v)) for v in values if clean_text(v)]


def _parse_basic_info(row) -> tuple[str, str | list[str]]:
    label = _first_text(row, "span.header::text")
    label = label.rstrip(":").strip()

    if label in ("類別", "演員"):
        link_texts = _all_text(row, "a::text")
        return label, link_texts

    link_text = _first_text(row, "a::text")
    if link_text:
        return label, link_text

    text = _first_text(row, "p::text")
    if not text and label:
        full = clean_text(row.css("::text").getall())
        for t in full:
            t = str(t).strip()
            if t and t != label and not t.startswith(":"):
                text = t
                break

    return label, text


def _extract_code_from_url(url: str) -> str:
    match = re.search(r"/([A-Za-z]+-\d+)", url)
    return match.group(1) if match else ""


def parse_list_page(page: Adaptor, source_url: str) -> tuple[list[dict[str, Any]], str | None]:
    items: list[dict[str, Any]] = []
    for node in page.css("div.item a.movie-box"):
        href = node.css("::attr(href)").get("")
        if not href:
            continue
        detail_url = urljoin(source_url, href)
        title = _first_text(node, "img::attr(title)")
        code = _extract_code_from_url(href)
        items.append({
            "url": detail_url,
            "title": title,
            "code": code,
        })

    next_href = page.css("a#next::attr(href)").get("")
    next_url = urljoin(source_url, next_href) if next_href else None
    return items, next_url


def parse_detail_page(page: Adaptor, source_url: str) -> dict[str, Any]:
    title = _first_text(page, ".screencap img::attr(title)")
    cover_url = _first_text(page, ".screencap img::attr(src)")

    result: dict[str, Any] = {
        "source": "javbus",
        "source_url": source_url,
        "source_name": title,
        "title": title,
        "code": "",
        "release_date": "",
        "duration": 0,
        "director": "",
        "maker": "",
        "series": "",
        "tags": [],
        "actors": [],
        "cover_url": cover_url,
        "magnets": [],
    }

    for row in page.css("div.col-md-3.info p"):
        label, value = _parse_basic_info(row)
        field = FIELD_MAPPING.get(label)
        if not field:
            continue
        if field == "duration":
            match = re.search(r"\d+", str(value))
            result["duration"] = int(match.group()) if match else 0
        else:
            result[field] = value

    return result


def extract_ajax_params(page: Adaptor) -> dict[str, str]:
    scripts = page.css("script::text").getall()
    params: dict[str, str] = {}
    for script in scripts:
        gid_match = re.search(r"var\s+gid\s*=\s*(\d+)", script)
        uc_match = re.search(r"var\s+uc\s*=\s*(\d+)", script)
        img_match = re.search(r"var\s+img\s*=\s*['\"]([^'\"]+)['\"]", script)
        if gid_match:
            params["gid"] = gid_match.group(1)
        if uc_match:
            params["uc"] = uc_match.group(1)
        if img_match:
            params["img"] = img_match.group(1)
    return params


def _parse_magnet_row(row) -> dict[str, Any] | None:
    magnet_href = row.css("a[href^='magnet:']::attr(href)").get("")
    if not magnet_href:
        return None

    name = _first_text(row, "a[href^='magnet:']::text")
    if not name:
        return None

    cells = row.css("td")
    size_text = ""
    file_text = ""
    file_count = 0
    date = ""
    tags: list[str] = []

    if len(cells) >= 2:
        cell_texts = cells[1].css("::text").getall()
        texts = [str(clean_text(t)) for t in cell_texts if clean_text(t)]
        if texts:
            size_text = texts[0]
        for t in texts:
            if "files" in t.lower():
                file_text = t
                match = re.search(r"(\d+)", t)
                if match:
                    file_count = int(match.group(1))

    if len(cells) >= 3:
        date = str(clean_text(cells[2].css("::text").get("")))

    if len(cells) >= 4:
        btn_texts = cells[3].css(".btn::text").getall()
        tags = [str(clean_text(t)) for t in btn_texts if clean_text(t)]

    has_chinese_sub = any("中字" in tag or "字幕" in tag for tag in tags)

    return {
        "magnet": magnet_href,
        "name": name,
        "size_text": size_text,
        "file_text": file_text,
        "file_count": file_count,
        "tags": tags,
        "has_chinese_sub": has_chinese_sub,
        "date": date,
    }


def parse_magnet_ajax(page: Adaptor) -> list[dict[str, Any]]:
    magnets: list[dict[str, Any]] = []
    for row in page.css("tr"):
        magnet = _parse_magnet_row(row)
        if magnet:
            magnets.append(magnet)
    return magnets
