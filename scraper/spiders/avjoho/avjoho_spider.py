from __future__ import annotations

from urllib.parse import quote, urlparse

from scrapling.parser import Adaptor

from scraper.profiles.actress import ActressProfileMatch, ActressProfilePayload, dedupe_text
from scraper.spiders.avjoho.avjoho_parser import parse_avjoho_profile


class AvjohoActressSpider:
    source = "avjoho"

    def __init__(self, fetcher):
        self.fetcher = fetcher

    @staticmethod
    def validate_profile_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != "db.avjoho.com":
            raise ValueError("avjoho_url must be an HTTP(S) URL on db.avjoho.com")
        return url

    @staticmethod
    def build_direct_profile_urls(names: list[str]) -> list[str]:
        return [f"https://db.avjoho.com/{quote(name)}/" for name in dedupe_text(names)]

    @staticmethod
    def build_search_names(names: list[str]) -> list[str]:
        variants: list[str] = []
        for name in names:
            variants.append(name)
            variants.append(str(name or "").replace("瀨", "瀬"))
        return dedupe_text(variants)

    @staticmethod
    def _page_to_html(page) -> str:
        html = getattr(page, "html", None)
        if html is not None:
            return html() if callable(html) else str(html)
        text = getattr(page, "text", None)
        if text is not None:
            return text() if callable(text) else str(text)
        return str(page)

    @staticmethod
    def _is_profile_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != "db.avjoho.com":
            return False
        path = parsed.path.strip("/")
        if not path:
            return False
        excluded_prefixes = ("category/", "tag/", "page/", "search/", "feed/", "wp-", "sitemap")
        return not path.startswith(excluded_prefixes)

    @classmethod
    def parse_search_result_urls(cls, html: str) -> list[str]:
        page = Adaptor(html)
        urls: list[str] = []
        for anchor in page.css("#list .entry-title a"):
            href = str(anchor.attrib.get("href") or "").strip()
            if cls._is_profile_url(href):
                urls.append(href)
        return dedupe_text(urls)

    def find_profile_urls_by_search(self, name: str) -> list[str]:
        search_url = f"https://db.avjoho.com/?s={quote(name)}"
        html = self._page_to_html(self.fetcher.get(search_url))
        return self.parse_search_result_urls(html)

    def fetch_profile(self, url: str) -> ActressProfilePayload | None:
        html = self._page_to_html(self.fetcher.get(url))
        return parse_avjoho_profile(html, url)

    @staticmethod
    def profile_matches_names(payload: ActressProfilePayload, names: list[str]) -> bool:
        haystack = {payload.display_name, *payload.aliases}
        return bool(set(dedupe_text(names)).intersection(haystack))

    def find_first_matching_profile(self, names: list[str], manual_url: str | None = None) -> ActressProfileMatch:
        candidate_names = dedupe_text(names)
        attempted_urls: list[str] = []
        if manual_url:
            url_candidates = [self.validate_profile_url(manual_url)]
        else:
            search_candidates: list[str] = []
            for name in self.build_search_names(candidate_names):
                try:
                    search_candidates.extend(self.find_profile_urls_by_search(name))
                except Exception:
                    continue
            url_candidates = dedupe_text([*self.build_direct_profile_urls(candidate_names), *search_candidates])

        for url in url_candidates:
            attempted_urls.append(url)
            try:
                payload = self.fetch_profile(url)
            except Exception:
                continue
            if payload is None:
                continue
            if manual_url is None and not self.profile_matches_names(payload, candidate_names):
                continue
            return ActressProfileMatch(
                profile=payload,
                attempted_urls=attempted_urls,
                candidate_names=candidate_names,
                matched_url=url,
            )

        return ActressProfileMatch(
            profile=None,
            attempted_urls=attempted_urls,
            candidate_names=candidate_names,
        )
