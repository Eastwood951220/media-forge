from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from scrapling.parser import Adaptor

from scraper.core.utils import clean_text


@dataclass
class AvjohoProfilePayload:
    display_name: str
    reading: str
    source_url: str
    image_url: str = ""
    aliases: list[str] = field(default_factory=list)
    debut_date: date | None = None
    birth_date: date | None = None
    height_cm: int | None = None
    bust_cm: int | None = None
    waist_cm: int | None = None
    hip_cm: int | None = None
    cup: str = ""
    birthplace: str = ""
    blood_type: str = ""
    hobbies: str = ""
    biography: str = ""
    exclusive_maker: str = ""
    sns_links: list[dict] = field(default_factory=list)
    representative_works: list[dict] = field(default_factory=list)
    similar_actresses: list[dict] = field(default_factory=list)
    raw_profile: dict = field(default_factory=dict)


def _first_text(page: Adaptor, selector: str) -> str:
    value = page.css(selector).get()
    return str(clean_text(value or ""))


def _first_attr(page: Adaptor, selector: str) -> str:
    value = page.css(selector).get()
    return str(clean_text(value or ""))


def _text_content(node) -> str:
    texts = [str(clean_text(value)) for value in node.css("::text").getall()]
    return "\n".join(text for text in texts if text)


def _parse_japanese_date(value: str) -> date | None:
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value or "")
    if not match:
        return None
    return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _parse_int_cm(value: str) -> int | None:
    match = re.search(r"(\d+)\s*cm", value or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def _parse_measurements(value: str) -> tuple[int | None, int | None, int | None]:
    text = value or ""
    bust = re.search(r"B\s*(\d+)\s*cm", text, re.IGNORECASE)
    waist = re.search(r"W\s*(\d+)\s*cm", text, re.IGNORECASE)
    hip = re.search(r"H\s*(\d+)\s*cm", text, re.IGNORECASE)
    return (
        int(bust.group(1)) if bust else None,
        int(waist.group(1)) if waist else None,
        int(hip.group(1)) if hip else None,
    )


def _split_title(value: str) -> tuple[str, str]:
    title = str(clean_text(value or ""))
    match = re.match(r"^(.+?)（(.+?)）$", title)
    if match:
        return str(clean_text(match.group(1))), str(clean_text(match.group(2)))
    return title, ""


def _collect_tables(page: Adaptor) -> dict[str, str]:
    fields: dict[str, str] = {}
    for row in page.css(".database table tr"):
        label = _first_text(row, "th::text")
        td = row.css("td")
        value = _text_content(td[0]) if td else ""
        if label:
            fields[label] = value
    return fields


def _parse_aliases(value: str) -> list[str]:
    text = str(clean_text(value or ""))
    if text in {"", "-", "–", "—"}:
        return []
    aliases: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,、，]", text):
        alias = str(clean_text(part))
        if alias and alias not in seen:
            seen.add(alias)
            aliases.append(alias)
    return aliases


def _parse_sns(page: Adaptor) -> list[dict]:
    links: list[dict] = []
    for row in page.css(".sns tr"):
        label = _first_text(row, "th::text")
        href = _first_attr(row, "td a::attr(href)")
        text = _first_text(row, "td a::text") or _text_content(row.css("td")[0]) if row.css("td") else ""
        if label and (href or text):
            links.append({"label": label, "url": href, "text": text})
    return links


def _parse_representative_works(page: Adaptor) -> list[dict]:
    works: list[dict] = []
    images = page.css(".gazou-large")
    titles = page.css(".text-link")
    for index, image_node in enumerate(images):
        title_node = titles[index] if index < len(titles) else None
        title = _first_text(title_node, "a::text") if title_node is not None else ""
        url = _first_attr(title_node, "a::attr(href)") if title_node is not None else _first_attr(image_node, "a::attr(href)")
        image_url = _first_attr(image_node, "img::attr(src)")
        if title or url or image_url:
            works.append({"title": title, "url": url, "image_url": image_url})
    return works


def _parse_similar_actresses(page: Adaptor) -> list[dict]:
    actresses: list[dict] = []
    for node in page.css(".yarpp-thumbnail"):
        name = _first_text(node, ".yarpp-thumbnail-title::text") or _first_attr(node, "::attr(title)")
        url = _first_attr(node, "::attr(href)")
        image_url = _first_attr(node, "img::attr(src)")
        if name or url or image_url:
            actresses.append({"name": name, "url": url, "image_url": image_url})
    return actresses


def parse_avjoho_profile(html: str, source_url: str) -> AvjohoProfilePayload | None:
    page = Adaptor(html)
    title = _first_text(page, "h1.entry-title::text")
    display_name, reading = _split_title(title)
    if not display_name:
        return None

    fields = _collect_tables(page)
    bust, waist, hip = _parse_measurements(fields.get("スリーサイズ", ""))
    return AvjohoProfilePayload(
        display_name=display_name,
        reading=reading,
        source_url=source_url,
        image_url=_first_attr(page, ".gazou img::attr(src)"),
        aliases=_parse_aliases(fields.get("別名", "")),
        debut_date=_parse_japanese_date(fields.get("デビュー", "")),
        birth_date=_parse_japanese_date(fields.get("生年月日", "")),
        height_cm=_parse_int_cm(fields.get("身長", "")),
        bust_cm=bust,
        waist_cm=waist,
        hip_cm=hip,
        cup=fields.get("カップ", ""),
        birthplace=fields.get("出身地", ""),
        blood_type=fields.get("血液型", ""),
        hobbies=fields.get("趣味・特技", ""),
        biography=_first_text(page, ".profile2::text"),
        exclusive_maker=fields.get("専属メーカー", ""),
        sns_links=_parse_sns(page),
        representative_works=_parse_representative_works(page),
        similar_actresses=_parse_similar_actresses(page),
        raw_profile=fields,
    )
