import re
from typing import Any

from scraper.core.utils import clean_text, parse_size
from scraper.spiders.javdb.javdb_constants import (
    FIELD_MAPPING,
    FILTER_KEYWORD_FC2,
    TASK_STATUS_PENDING,
    TASK_STATUS_SKIPPED,
)
from scraper.spiders.javdb.javdb_urls import build_detail_url


def _first_text(node, selectors: list[str]) -> str:
    for selector in selectors:
        value = node.css(selector).get()
        if value:
            return str(clean_text(value))
    return ""


def _all_text(node, selector: str) -> list[str]:
    values = node.css(selector).getall()
    return [str(clean_text(value)) for value in values if clean_text(value)]


def _first_magnet_url(node, selectors: list[str]) -> str:
    for selector in selectors:
        values = node.css(selector).getall()
        for value in values:
            candidate = str(clean_text(value))
            if candidate.startswith("magnet:?"):
                return candidate
    return ""


def _parse_field_value(field_name: str, row) -> Any:
    text = _first_text(row, ["span.value::text", "span::text"])
    link_texts = _all_text(row, "span.value a::text") or _all_text(row, "a::text")

    if field_name == "日期":
        return text

    if field_name == "時長":
        match = re.search(r"\d+", text)
        return int(match.group()) if match else 0

    if field_name in ("導演", "导演", "片商", "系列"):
        return link_texts[0] if link_texts else text

    if field_name in ("評分", "评分"):
        match = re.search(r"([\d.]+)", text)
        return float(match.group(1)) if match else 0.0

    if field_name in ("演員", "演员"):
        # Only include female actors (those followed by <strong class="symbol female">)
        female_actors = []
        value_node = row.css("span.value")
        if value_node:
            # Get all <a> and <strong> children in order
            children = value_node.css("a, strong.symbol")
            current_actor = None
            for child in children:
                class_name = child.css("::attr(class)").get("") or ""
                child_text = clean_text(child.css("::text").get() or "")
                if "symbol" not in class_name:
                    current_actor = child_text
                elif "female" in class_name and current_actor:
                    female_actors.append(current_actor)
                    current_actor = None
        if female_actors:
            return female_actors
        return link_texts or ([text] if text else [])

    if field_name in ("類別", "类别"):
        return link_texts or ([text] if text else [])

    return text


def _parse_magnet_meta(meta_text: str) -> tuple[str, int | None, str]:
    parts = [str(clean_text(part)) for part in meta_text.split(",")]
    size_text = parts[0] if parts else ""
    file_text = parts[1] if len(parts) > 1 else ""
    file_count_match = re.search(r"\d+", file_text)
    file_count = int(file_count_match.group()) if file_count_match else None

    return size_text, file_count, file_text


# Keywords that indicate uncensored/pirated content
UNCENSORED_KEYWORDS = ("无码破解", "无码", "破解")

# Tags to filter out from tag name extraction
TAGS_FILTER_KEYWORDS = ("含磁鏈", "含磁链", "含字幕")

# Code suffixes: -C = Chinese subtitle, -U = uncensored, -UC = both
_SUFFIX_RE = re.compile(r"-(UC|C|U)(?:\.|$)", re.IGNORECASE)


def derive_magnet_tags(
    name: str, existing_tags: list[str]
) -> tuple[list[str], bool]:
    """Derive tags from magnet name keywords and code suffixes.

    Returns (enriched_tags, has_chinese_sub).
    """
    if not name:
        has_sub = any("字幕" in t or "中字" in t for t in existing_tags)
        return list(existing_tags), has_sub

    tags = list(existing_tags)
    has_chinese_sub = any("字幕" in t or "中字" in t for t in tags)

    # Keyword-based: name contains uncensored keywords
    for keyword in UNCENSORED_KEYWORDS:
        if keyword in name:
            if "破解" not in tags:
                tags.append("破解")
            break

    # Suffix-based: parse code suffixes from the name
    match = _SUFFIX_RE.search(name)
    if match:
        suffix = match.group(1).upper()
        if suffix == "UC":
            if "中文字幕" not in tags:
                tags.append("中文字幕")
            has_chinese_sub = True
            if "破解" not in tags:
                tags.append("破解")
        elif suffix == "C":
            if "中文字幕" not in tags:
                tags.append("中文字幕")
            has_chinese_sub = True
        elif suffix == "U":
            if "破解" not in tags:
                tags.append("破解")

    return tags, has_chinese_sub


def is_fc2_task(name: str | None, url: str | None, code: str | None = None) -> bool:
    values = [
        name or "",
        url or "",
        code or "",
    ]
    joined = " ".join(values).lower()

    return FILTER_KEYWORD_FC2 in joined


def parse_search_page(
    page,
    source_page: int,
) -> list[dict]:
    tasks: list[dict] = []

    for node in page.css("div.item a.box"):
        name = _first_text(
            node,
            [
                "::attr(title)",
                ".video-title::text",
                ".video-title strong::text",
                "strong::text",
            ],
        )
        code = _first_text(node, [".video-title strong::text", "strong::text"])
        href = _first_text(node, ["::attr(href)", "a::attr(href)"])
        cover = _first_text(node, ["img::attr(src)", "img::attr(data-src)"])

        if not href:
            continue

        url = build_detail_url(href)
        task = {
            "url": url,
            "name": clean_text(name),
            "code": clean_text(code),
            "source_page": source_page,
            "status": TASK_STATUS_PENDING,
        }

        if cover:
            task["cover"] = cover

        if is_fc2_task(task.get("name"), task.get("url"), task.get("code")):
            task["status"] = TASK_STATUS_SKIPPED
            task["reason"] = "filtered_fc2"

        tasks.append(task)

    return tasks


def parse_detail_page(page) -> dict:
    title = _first_text(page, ["h2.title::text", ".title::text", "title::text"])
    cover = _first_text(
        page,
        [
            ".video-cover img::attr(src)",
            ".movie-panel .cover img::attr(src)",
            "img.video-cover::attr(src)",
        ],
    )

    detail: dict[str, Any] = {
        "source_name": title,
        "cover": cover,
        "release_date": "",
        "duration": 0,
        "director": "",
        "maker": "",
        "series": "",
        "rating": 0.0,
        "tags": [],
        "actors": [],
    }

    for row in page.css("nav.movie-panel-info > div.panel-block, .movie-panel-info .panel-block"):
        label = _first_text(row, ["strong::text"]).rstrip(":").strip()
        key = FIELD_MAPPING.get(label)
        if not key:
            continue
        detail[key] = _parse_field_value(label, row)

    magnets = parse_magnets(page)
    if magnets:
        detail["magnets"] = magnets

    return detail


# 不同 url_type 对应的 section name 提取配置
_SECTION_NAME_CONFIG: dict[str, dict[str, str | bool]] = {
    "actors": {"selector": ".actor-section-name::text", "split_comma": True},
    "lists": {"selector": ".actor-section-name::text", "split_comma": False},
    "series": {"selector": ".section-title .section-name::text", "split_comma": False},
    "makers": {"selector": ".section-title .section-name::text", "split_comma": False},
    "directors": {"selector": ".section-title .section-name::text", "split_comma": False},
    "video_codes": {"selector": ".section-title .section-name::text", "split_comma": False},
}


def _extract_tags_name(page) -> str:
    """从页面提取标签名称。

    优先从 .section-title .section-name 提取（列表页），
    回退到 #tags 区域的 div.tag.is-info 提取（详情页）。
    """
    # Try listing page structure first: .section-title .section-name
    raw = _first_text(page, [".section-title .section-name::text"])
    if raw:
        return raw

    # Fall back to detail page structure: #tags div.tag.is-info
    tags_div = page.css("#tags")
    if not tags_div:
        return ""

    tag_elements = tags_div[0].css("div.tag.is-info")
    if not tag_elements:
        return ""

    tag_names = []
    for elem in tag_elements:
        text = clean_text(elem.css("::text").get() or "")
        if not text:
            continue

        if any(keyword in text for keyword in TAGS_FILTER_KEYWORDS):
            continue

        tag_names.append(text)

    if not tag_names:
        return ""

    return "-".join(tag_names)


def parse_page_section_name(page, url_type: str) -> str:
    """从页面的 section-title 区域提取名称。

    actors 类型: 取 actor-section-name，逗号分割取第一个
    lists 类型: 取 actor-section-name，完整返回
    series/makers/directors/video_codes 类型: 取 section-name
    search 类型: 返回空字符串
    tags 类型: 从 #tags 区域的 div.tag.is-info 提取
    """
    if url_type == "tags":
        return _extract_tags_name(page)

    config = _SECTION_NAME_CONFIG.get(url_type)
    if not config:
        return ""

    raw = _first_text(page, [config["selector"]])
    if not raw:
        return ""

    if config.get("split_comma"):
        return raw.split(",")[0].strip()

    return raw


def parse_magnets(page) -> list[dict]:
    magnets: list[dict] = []

    for node in page.css("#magnets-content .item"):
        magnet_url = _first_magnet_url(
            node,
            [
                ".magnet-name a::attr(href)",
                "a::attr(href)",
                "button.copy-to-clipboard::attr(data-clipboard-text)",
            ],
        )

        name = _first_text(node, [".magnet-name .name::text", ".name::text", ".magnet-name a::text"])
        meta_text = _first_text(node, [".magnet-name .meta::text", ".meta::text"])
        if not (magnet_url or name or meta_text):
            continue

        size_text, file_count, file_text = _parse_magnet_meta(meta_text)
        html_tags = _all_text(node, ".magnet-name .tags .tag::text") or _all_text(node, ".tag::text")
        tags, has_chinese_sub = derive_magnet_tags(name, html_tags)
        date = _first_text(node, [".date .time::text", ".time::text"])

        magnets.append(
            {
                "magnet": magnet_url,
                "name": name,
                "size": round(parse_size(size_text), 2),
                "size_text": size_text,
                "file_count": file_count,
                "file_text": file_text,
                "tags": tags,
                "has_chinese_sub": has_chinese_sub,
                "date": date,
            }
        )

    return magnets
