from scrapling.parser import Adaptor

from scraper.spiders.javdb.javdb_parser import parse_detail_page


def page(html: str) -> Adaptor:
    return Adaptor(html)


def test_parse_detail_page_extracts_code_and_current_title_from_video_detail_heading() -> None:
    parsed = parse_detail_page(
        page(
            """
            <html>
              <body>
                <div class="video-detail">
                  <h2 class="title is-4">
                    <strong>TIMD-036 </strong>
                    <strong class="current-title">極上メス男子ゆうきくん無限アクメ肉棒大乱交！！ </strong>
                  </h2>
                </div>
                <nav class="movie-panel-info">
                  <div class="panel-block"><strong>日期:</strong><span class="value">2026-07-10</span></div>
                </nav>
              </body>
            </html>
            """
        )
    )

    assert parsed["code"] == "TIMD-036"
    assert parsed["source_name"] == "極上メス男子ゆうきくん無限アクメ肉棒大乱交！！"
    assert parsed["release_date"] == "2026-07-10"


def test_parse_detail_page_uses_second_strong_when_current_title_class_is_missing() -> None:
    parsed = parse_detail_page(
        page(
            """
            <html>
              <body>
                <div class="video-detail">
                  <h2 class="title is-4">
                    <strong>ABC-123</strong>
                    <strong>Second Title</strong>
                  </h2>
                </div>
              </body>
            </html>
            """
        )
    )

    assert parsed["code"] == "ABC-123"
    assert parsed["source_name"] == "Second Title"


def test_parse_detail_page_keeps_existing_title_fallback_when_structured_heading_is_missing() -> None:
    parsed = parse_detail_page(
        page(
            """
            <html>
              <body>
                <h2 class="title">Fallback Title</h2>
              </body>
            </html>
            """
        )
    )

    assert "code" not in parsed
    assert parsed["source_name"] == "Fallback Title"


def test_parse_detail_page_returns_empty_actors_when_actor_row_has_only_male_symbols() -> None:
    parsed = parse_detail_page(
        page(
            """
            <html>
              <body>
                <nav class="movie-panel-info">
                  <div class="panel-block">
                    <strong>演員:</strong>
                    &nbsp;<span class="value">
                      <a href="/actors/Wr0g">タイ</a><strong class="symbol male">♂</strong>&nbsp;
                      <a href="/actors/274p">左慈半造</a><strong class="symbol male">♂</strong>&nbsp;
                      <a href="/actors/1BePW">渋谷優太</a><strong class="symbol male">♂</strong>&nbsp;
                    </span>
                  </div>
                </nav>
              </body>
            </html>
            """
        )
    )

    assert parsed["actors"] == []


def test_parse_detail_page_keeps_only_actors_followed_by_female_symbols() -> None:
    parsed = parse_detail_page(
        page(
            """
            <html>
              <body>
                <nav class="movie-panel-info">
                  <div class="panel-block">
                    <strong>演員:</strong>
                    &nbsp;<span class="value">
                      <a href="/actors/male">男優</a><strong class="symbol male">♂</strong>&nbsp;
                      <a href="/actors/female-a">女優A</a><strong class="symbol female">♀</strong>&nbsp;
                      <a href="/actors/female-b">女優B</a><strong class="symbol female">♀</strong>&nbsp;
                    </span>
                  </div>
                </nav>
              </body>
            </html>
            """
        )
    )

    assert parsed["actors"] == ["女優A", "女優B"]
