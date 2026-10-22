from __future__ import annotations

import json
import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from lxml import html

from backend.app.modules.scraping.paths import normalize_code
from backend.app.modules.scraping.source_types import SourceMetadata

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.dmm.co.jp/search/=/searchstr={}/limit=120/sort=date/"
GRAPHQL_URL = "https://api.video.dmm.co.jp/graphql"
VIDEO_REFERER = "https://video.dmm.co.jp/"
DVD_REFERER = "https://www.dmm.co.jp/"
TIMEOUT = 15.0
GRAPHQL_QUERY = """query($id: ID!) {
  ppvContent(id: $id) {
    id makerContentId title description deliveryStartDate makerReleasedAt
    packageImage { largeUrl mediumUrl }
    sampleImages { largeImageUrl imageUrl }
    maker { name } series { name } label { name }
    actresses { name } amateurActress { name } genres { name }
  }
}"""


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._inside = tag == "script"

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._inside = False

    def handle_data(self, data: str) -> None:
        if self._inside:
            self.scripts.append(data)


def _find_backend_response(node: Any) -> dict[str, Any] | None:
    if isinstance(node, dict):
        value = node.get("backendResponse")
        if isinstance(value, dict):
            return value
        for child in node.values():
            found = _find_backend_response(child)
            if found is not None:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_backend_response(child)
            if found is not None:
                return found
    return None


def _search_products(page: str) -> list[dict[str, Any]]:
    scripts = _Scripts()
    scripts.feed(page)
    marker = "self.__next_f.push("
    decoder = json.JSONDecoder()
    for script in scripts.scripts:
        start = script.find(marker)
        while start >= 0:
            try:
                push, end = decoder.raw_decode(script[start + len(marker):])
                if isinstance(push, list) and len(push) > 1 and isinstance(push[1], str):
                    for line in push[1].splitlines():
                        if "backendResponse" not in line:
                            continue
                        payload = line.split(":", 1)[-1]
                        response = _find_backend_response(json.loads(payload))
                        products = (response or {}).get("contents", {}).get("data", [])
                        if isinstance(products, list):
                            return [item for item in products if isinstance(item, dict)]
                start = script.find(marker, start + len(marker) + end)
            except (ValueError, TypeError):
                start = script.find(marker, start + len(marker))
    return []


def _product_code(content_id: str) -> str:
    match = re.search(r"([A-Za-z]+)(\d+)", content_id)
    if not match:
        return ""
    return f"{match.group(1).upper()}-{int(match.group(2)):03d}"


def _date(value: Any) -> str | None:
    match = re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", str(value or ""))
    return match.group().replace("/", "-") if match else None


def _name(value: Any) -> str | None:
    return str(value.get("name") or "").strip() or None if isinstance(value, dict) else None


def _names(values: Any) -> list[str]:
    return [name for item in (values or []) if (name := _name(item))]


def _preview_src(url: str) -> str:
    if re.search(r"p[a-z]\.jpg$", url):
        return re.sub(r"p[a-z]\.jpg$", "pl.jpg", url)
    if re.search(r"js-\d+\.jpg$", url):
        return url.replace("js-", "jp-")
    if re.search(r"ts-\d+\.jpg$", url):
        return url.replace("ts-", "tl-")
    return url


class FanzaAdapter:
    key = "fanza"
    site_key = "FANZA"

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self.transport = transport

    def _search(self, client: httpx.Client, code: str) -> list[dict[str, Any]]:
        variants = []
        if "-" in code:
            variants.append(code.replace("-", "00", 1).lower() + "#")
        variants.append(code.replace("-", "", 1).lower())
        for keyword in variants:
            url = SEARCH_URL.format(quote(keyword, safe=""))
            response = client.get(url)
            response.raise_for_status()
            if "age_check" in str(response.url) or "not-available-in-your-region" in response.text:
                return []
            products = _search_products(response.text)
            if products:
                return products
        return []

    def _digital(self, client: httpx.Client, product: dict[str, Any], wanted: str) -> SourceMetadata | None:
        content_id = str(product.get("content_id") or "")
        response = client.post(
            GRAPHQL_URL,
            json={"query": GRAPHQL_QUERY, "variables": {"id": content_id}},
            headers={"Referer": VIDEO_REFERER, "Fanza-Device": "BROWSER", "Cache-Control": "no-cache"},
        )
        response.raise_for_status()
        data = response.json().get("data") or {}
        detail = data.get("ppvContent") or {}
        if not isinstance(detail, dict) or normalize_code(str(detail.get("makerContentId") or _product_code(str(detail.get("id") or "")))) != wanted:
            return None
        package = detail.get("packageImage") or {}
        previews = [str(img.get("largeImageUrl") or img.get("imageUrl") or "") for img in (detail.get("sampleImages") or [])]
        previews = [url for url in previews if url]
        actors = _names(detail.get("actresses"))
        if not actors and (amateur := _name(detail.get("amateurActress"))):
            actors = [amateur]
        return SourceMetadata(
            site_key=self.site_key,
            title=str(detail.get("title") or "") or None,
            original_title=str(detail.get("title") or "") or None,
            premiered=_date(detail.get("deliveryStartDate")) or _date(detail.get("makerReleasedAt")),
            genres=_names(detail.get("genres")), tags=_names(detail.get("genres")),
            studio=_name(detail.get("maker")), series=_name(detail.get("series")), actors=actors,
            cover_url=str(package.get("largeUrl") or package.get("mediumUrl") or "") or None,
            backdrop_url=previews[0] if previews else None,
            landscape_url=previews[1] if len(previews) > 1 else None,
            preview_urls=previews,
        )

    def _dvd(self, client: httpx.Client, product: dict[str, Any], wanted: str) -> SourceMetadata | None:
        url = str(product.get("detail_url") or "")
        response = client.get(url)
        response.raise_for_status()
        if "age_check" in str(response.url) or "not-available-in-your-region" in response.text:
            return None
        tree = html.fromstring(response.text)
        json_text = tree.xpath('//script[@type="application/ld+json"]/text()')
        structured = json.loads(json_text[0]) if json_text else {}
        if not isinstance(structured, dict):
            return None
        sku = str(structured.get("sku") or product.get("content_id") or "")
        if normalize_code(_product_code(sku)) != wanted:
            return None
        fields: dict[str, str] = {}
        for row in tree.xpath("//tr"):
            cells = [" ".join(cell.itertext()).strip() for cell in row.xpath("./td")]
            if len(cells) >= 2:
                fields[cells[0]] = cells[1]
        cover_links = tree.xpath('//*[@name="package-image"]/@href')
        previews = []
        for img in tree.xpath('//*[@id="sample-image-block"]//a[@name="sample-image"]//img'):
            source = img.get("data-lazy") or img.get("src") or ""
            if source:
                previews.append(_preview_src(str(httpx.URL(url).join(source))))
        genres = [" ".join(node.itertext()).strip() for node in tree.xpath('//tr[td[1][contains(.,"ジャンル")]]/td[2]/a')]
        actors = [" ".join(node.itertext()).strip() for node in tree.xpath('//tr[td[1][contains(.,"名前")]]/td[2]/a')]
        cover = str(httpx.URL(url).join(cover_links[0])) if cover_links else _preview_src(str(structured.get("image") or ""))
        return SourceMetadata(
            site_key=self.site_key,
            title=str(structured.get("name") or "") or None,
            original_title=str(structured.get("name") or "") or None,
            premiered=_date(fields.get("発売日：") or fields.get("配信開始日：") or fields.get("商品発売日：")),
            genres=genres, tags=genres,
            studio=fields.get("メーカー："), series=fields.get("シリーズ："), actors=actors,
            cover_url=cover or None,
            backdrop_url=previews[0] if previews else None,
            landscape_url=previews[1] if len(previews) > 1 else None,
            preview_urls=previews,
        )

    def fetch_by_code(self, code: str) -> SourceMetadata | None:
        wanted = normalize_code(code)
        if not wanted:
            return None
        try:
            with httpx.Client(timeout=TIMEOUT, transport=self.transport, follow_redirects=False, cookies={"age_check_done": "1"}) as client:
                products = self._search(client, code)
                exact = [item for item in products if normalize_code(_product_code(str(item.get("content_id") or ""))) == wanted]
                exact.sort(key=lambda item: urlparse(str(item.get("detail_url") or "")).hostname != "video.dmm.co.jp")
                for item in exact:
                    url = str(item.get("detail_url") or "")
                    parsed = urlparse(url)
                    if parsed.scheme != "https" or parsed.hostname not in {"www.dmm.co.jp", "video.dmm.co.jp"}:
                        continue
                    try:
                        metadata = self._digital(client, item, wanted) if urlparse(url).hostname == "video.dmm.co.jp" else self._dvd(client, item, wanted)
                        if metadata and metadata.cover_url:
                            return metadata
                    except (httpx.HTTPError, ValueError, TypeError, KeyError):
                        logger.warning("FANZA detail unavailable: code=%s url=%s", code, url, exc_info=True)
                logger.info("FANZA exact metadata not found: code=%s", code)
        except (httpx.HTTPError, ValueError, TypeError):
            logger.warning("FANZA search unavailable: code=%s", code, exc_info=True)
        return None
