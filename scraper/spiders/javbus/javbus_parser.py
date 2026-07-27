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
    "製作商": "maker",
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


def _direct_texts(row) -> list[str]:
    values = row.xpath("./text()[normalize-space()]").getall()
    return [str(clean_text(value)) for value in values if clean_text(value)]


def _parse_basic_info(row) -> tuple[str, str | list[str]]:
    label = _first_text(row, "span.header::text").rstrip(":：").strip()
    if not label:
        return "", ""

    if label in {"類別", "演員"}:
        return label, _all_text(row, "a::text")

    link_text = _first_text(row, "a::text")
    if link_text:
        return label, link_text

    non_header_text = _first_text(row, "span:not(.header)::text")
    if non_header_text:
        return label, non_header_text

    direct_texts = _direct_texts(row)
    return label, direct_texts[0] if direct_texts else ""


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


def parse_javbus_url_name(page: Adaptor) -> str:
    raw = _first_text(
        page,
        ".alert.alert-success.alert-common p b:first-of-type::text",
    )
    return raw.split(" - ", 1)[0].strip() if raw else ""


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

    # Real markup: tags live in sibling <p> after the 類別 header
    tag_values = page.xpath(
        "//div[contains(@class,'info')]"
        "/p[contains(@class,'header') and contains(normalize-space(.),'類別')]"
        "/following-sibling::p[1]//span[contains(@class,'genre')]//a/text()"
    ).getall()
    if not tag_values:
        # Fallback: tags inline in same <p> as header
        tag_values = page.xpath(
            "//div[contains(@class,'info')]"
            "/p[span[contains(@class,'header') and contains(text(),'類別')]]"
            "//span[contains(@class,'genre')]//a/text()"
        ).getall()
    result["tags"] = [
        str(clean_text(value)) for value in tag_values if clean_text(value)
    ]

    # Real markup: actors live in #star-div
    actor_values = page.css("#star-div .avatar-box > span::text").getall()
    if not actor_values:
        actor_values = page.css(".star-name a::text").getall()
    if not actor_values:
        actor_values = page.css(".star a::text").getall()
    result["actors"] = [
        str(clean_text(value)) for value in actor_values if clean_text(value)
    ]

    # Make cover_url absolute
    result["cover_url"] = urljoin(source_url, result["cover_url"])

    # Validate code: "識別碼:" or empty → fallback to URL
    code = result["code"]
    if not code or code == "識別碼:" or code.startswith("識別碼"):
        result["code"] = _extract_code_from_url(source_url)
    if not result["code"]:
        result["code"] = _extract_code_from_url(source_url)

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
    cells = row.css("td")
    if len(cells) < 3:
        return None

    magnet_href = cells[0].css("a[href^='magnet:']::attr(href)").get("")
    if not magnet_href:
        return None

    name_parts = cells[0].css("a[href^='magnet:']::text").getall()
    name = next(
        (str(clean_text(value)) for value in name_parts if clean_text(value)),
        "",
    )
    if not name:
        return None

    size_text = _first_text(cells[1], "a::text")
    if not size_text:
        size_text = _first_text(cells[1], "::text")

    date = _first_text(cells[2], "a::text")
    if not date:
        date = _first_text(cells[2], "::text")

    row_texts = [str(clean_text(value)) for value in cells[1].css("::text").getall()]
    file_text = next(
        (value for value in row_texts if "files" in value.lower()),
        "",
    )
    file_match = re.search(r"\d+", file_text)
    file_count = int(file_match.group()) if file_match else None

    tags = [
        str(clean_text(value))
        for value in row.css(".btn::text").getall()
        if clean_text(value)
    ]

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
