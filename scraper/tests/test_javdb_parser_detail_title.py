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
