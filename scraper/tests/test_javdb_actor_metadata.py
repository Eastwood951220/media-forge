from scrapling.parser import Adaptor

from scraper.spiders.javdb.javdb_parser import parse_actor_section_metadata


def page(html: str) -> Adaptor:
    return Adaptor(html)


def test_parse_actor_section_metadata_extracts_alias() -> None:
    parsed = parse_actor_section_metadata(page("""
    <div class="column section-title">
      <h2 class="title is-4 has-text-justified">
        <span class="actor-section-name">咲乃柑菜</span>
        <br>
        <span class="section-meta">蘭華</span>
        <br>
        <span class="section-meta">339 部影片</span>
      </h2>
    </div>
    """))

    assert parsed == {"primary_names": ["咲乃柑菜"], "aliases": ["蘭華"]}


def test_parse_actor_section_metadata_splits_primary_names_and_aliases() -> None:
    parsed = parse_actor_section_metadata(page("""
    <div class="column section-title">
      <h2 class="title is-4 has-text-justified">
        <span class="actor-section-name">蓮實克蕾兒, 蓮実クレア</span>
        <br>
        <span class="section-meta">安達亜美, 新田絢, 蓮見クレア, 神楽坂唯, 蓮美クレア, 莲実クレア</span>
        <br>
        <span class="section-meta">1928 部影片</span>
      </h2>
    </div>
    """))

    assert parsed["primary_names"] == ["蓮實克蕾兒", "蓮実クレア"]
    assert parsed["aliases"] == ["安達亜美", "新田絢", "蓮見クレア", "神楽坂唯", "蓮美クレア", "莲実クレア"]


from scraper.spiders.javdb.actor_profile import parse_actor_metadata


def test_parse_actor_metadata_returns_source_neutral_payload() -> None:
    parsed = parse_actor_metadata(page("""
      <div class="column section-title">
        <h2 class="title is-4 has-text-justified">
          <span class="actor-section-name">蓮實克蕾兒, 蓮実クレア</span>
          <br>
          <span class="section-meta">安達亜美, 新田絢</span>
          <br>
          <span class="section-meta">1928 部影片</span>
        </h2>
      </div>
    """), source_url="https://javdb.com/actors/X301")

    assert parsed.primary_names == ["蓮實克蕾兒", "蓮実クレア"]
    assert parsed.aliases == ["安達亜美", "新田絢"]
    assert parsed.source_url == "https://javdb.com/actors/X301"
    assert parsed.source_site == "javdb"
