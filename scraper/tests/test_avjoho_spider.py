from datetime import date

from scraper.profiles.actress import (
    ActorMetadata,
    ActressProfileMatch,
    ActressProfilePayload,
    dedupe_text,
)


def test_dedupe_text_preserves_order_and_drops_empty_values() -> None:
    assert dedupe_text(["七瀬アリス", "", None, "七瀬アリス", "七瀬愛麗絲"]) == [
        "七瀬アリス",
        "七瀬愛麗絲",
    ]


def test_actress_payload_dataclass_keeps_current_profile_fields() -> None:
    payload = ActressProfilePayload(
        display_name="宮上唯依花",
        reading="みやうえゆいか",
        source_url="https://db.avjoho.com/example/",
        aliases=["Miyaue Yuika"],
        debut_date=date(2020, 1, 2),
        birth_date=date(1998, 3, 4),
        height_cm=163,
        bust_cm=90,
        waist_cm=59,
        hip_cm=88,
        cup="E",
        sns_links=[{"label": "X", "url": "https://x.example"}],
    )

    assert payload.display_name == "宮上唯依花"
    assert payload.aliases == ["Miyaue Yuika"]
    assert payload.sns_links == [{"label": "X", "url": "https://x.example"}]


def test_actress_match_defaults_to_no_profile() -> None:
    match = ActressProfileMatch(
        profile=None,
        attempted_urls=["https://db.avjoho.com/missing/"],
        candidate_names=["missing"],
    )

    assert match.profile is None
    assert match.matched_url == ""


from urllib.parse import quote

import pytest

from scraper.spiders.avjoho.avjoho_spider import AvjohoActressSpider


class FakeResponse:
    def __init__(self, html: str) -> None:
        self._html = html

    @property
    def html(self):
        return self._html


class FakeFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requested: list[str] = []

    def get(self, url: str):
        self.requested.append(url)
        if url not in self.pages:
            raise FileNotFoundError(url)
        return FakeResponse(self.pages[url])


NANASE_PROFILE_HTML = """
<h1 class="entry-title">七瀬アリス（ななせありす）</h1>
<div class="database">
  <table><tbody><tr><th>別名</th><td>七瀨愛麗絲</td></tr></tbody></table>
</div>
"""


def test_avjoho_spider_builds_direct_profile_urls() -> None:
    spider = AvjohoActressSpider(fetcher=FakeFetcher({}))

    assert spider.build_direct_profile_urls(["七瀬アリス"]) == [
        "https://db.avjoho.com/%E4%B8%83%E7%80%AC%E3%82%A2%E3%83%AA%E3%82%B9/"
    ]


def test_avjoho_spider_matches_manual_profile_url() -> None:
    html = "<h1 class='entry-title'>七瀬アリス（ななせありす）</h1><div class='database'><table></table></div>"
    spider = AvjohoActressSpider(fetcher=FakeFetcher({"https://db.avjoho.com/nanase/": html}))

    result = spider.find_first_matching_profile(["七瀬アリス"], manual_url="https://db.avjoho.com/nanase/")

    assert result.profile is not None
    assert result.profile.display_name == "七瀬アリス"
    assert result.matched_url == "https://db.avjoho.com/nanase/"


def test_avjoho_spider_rejects_manual_url_on_other_host() -> None:
    spider = AvjohoActressSpider(fetcher=FakeFetcher({}))

    with pytest.raises(ValueError):
        spider.find_first_matching_profile(["七瀬アリス"], manual_url="https://example.test/nanase/")


def test_avjoho_spider_parses_search_result_urls_and_skips_non_profile_links() -> None:
    html = """
    <div id="list">
      <article><h2 class="entry-title"><a href="https://db.avjoho.com/nanase-alice/">七瀬アリス</a></h2></article>
      <article><h2 class="entry-title"><a href="https://db.avjoho.com/category/actress/">カテゴリ</a></h2></article>
      <article><h2 class="entry-title"><a href="https://db.avjoho.com/">ホーム</a></h2></article>
      <article><h2 class="entry-title"><a href="https://example.test/offsite/">別サイト</a></h2></article>
      <article><h2 class="entry-title"><a href="https://db.avjoho.com/nanase-alice/">重複</a></h2></article>
    </div>
    """

    assert AvjohoActressSpider.parse_search_result_urls(html) == [
        "https://db.avjoho.com/nanase-alice/"
    ]


def test_avjoho_spider_falls_back_to_search_after_direct_candidates_miss() -> None:
    spider = AvjohoActressSpider(
        fetcher=FakeFetcher({
            f"https://db.avjoho.com/?s={quote('七瀬愛麗絲')}": """
            <div id="list">
              <article><h2 class="entry-title">
                <a href="https://db.avjoho.com/nanase-alice/">七瀬アリス</a>
              </h2></article>
            </div>
            """,
            "https://db.avjoho.com/nanase-alice/": NANASE_PROFILE_HTML,
        })
    )

    result = spider.find_first_matching_profile(["七瀨愛麗絲"])

    assert result.profile is not None
    assert result.profile.display_name == "七瀬アリス"
    assert result.matched_url == "https://db.avjoho.com/nanase-alice/"
    assert result.attempted_urls == [
        "https://db.avjoho.com/%E4%B8%83%E7%80%A8%E6%84%9B%E9%BA%97%E7%B5%B2/",
        "https://db.avjoho.com/nanase-alice/",
    ]


def test_avjoho_spider_skips_candidate_whose_profile_name_does_not_match() -> None:
    spider = AvjohoActressSpider(
        fetcher=FakeFetcher({
            "https://db.avjoho.com/%E4%B8%83%E7%80%AC%E3%82%A2%E3%83%AA%E3%82%B9/": """
            <h1 class="entry-title">別の人（べつのひと）</h1><div class="database"><table></table></div>
            """,
            f"https://db.avjoho.com/?s={quote('七瀬アリス')}": """
            <div id="list">
              <article><h2 class="entry-title">
                <a href="https://db.avjoho.com/nanase-alice/">七瀬アリス</a>
              </h2></article>
            </div>
            """,
            "https://db.avjoho.com/nanase-alice/": NANASE_PROFILE_HTML,
        })
    )

    result = spider.find_first_matching_profile(["七瀬アリス"])

    assert result.matched_url == "https://db.avjoho.com/nanase-alice/"
    assert result.attempted_urls == [
        "https://db.avjoho.com/%E4%B8%83%E7%80%AC%E3%82%A2%E3%83%AA%E3%82%B9/",
        "https://db.avjoho.com/nanase-alice/",
    ]
