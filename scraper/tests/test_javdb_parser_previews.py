from scrapling.parser import Adaptor

from scraper.spiders.javdb.javdb_parser import parse_detail_page


def _page(html: str) -> Adaptor:
    return Adaptor(html)


def test_parse_detail_page_extracts_preview_images() -> None:
    html = """
    <html><body>
      <h2 class="title is-4"><strong>ADN-784</strong><strong class="current-title">Title</strong></h2>
      <div class="video-cover"><img src="https://c0.jdbstatic.com/cover.jpg"></div>
      <div class="preview-images">
        <a class="tile-item" href="https://c0.jdbstatic.com/preview-1.jpg"><img src="https://c0.jdbstatic.com/thumb-1.jpg"></a>
        <a class="tile-item" href="https://c0.jdbstatic.com/preview-2.jpg"><img src="https://c0.jdbstatic.com/thumb-2.jpg"></a>
      </div>
    </body></html>
    """

    detail = parse_detail_page(_page(html))

    assert detail["preview_images"] == [
        "https://c0.jdbstatic.com/preview-1.jpg",
        "https://c0.jdbstatic.com/preview-2.jpg",
    ]
