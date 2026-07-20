from scrapling.parser import Adaptor

from scraper.spiders.javbus.javbus_parser import (
    extract_ajax_params,
    parse_detail_page,
    parse_list_page,
    parse_magnet_ajax,
)

LIST_PAGE_HTML = """
<html>
<body>
<div class="item">
  <a class="movie-box" href="/ABCD-123">
    <img title="Movie Title One" src="https://pics.example/thumb1.jpg" />
    <date>2026-07-15</date>
  </a>
</div>
<div class="item">
  <a class="movie-box" href="/EFGH-456">
    <img title="Movie Title Two" src="https://pics.example/thumb2.jpg" />
    <date>2026-07-16</date>
  </a>
</div>
<a id="next" href="https://www.javbus.com/page/2">Next</a>
</body>
</html>
"""

LIST_PAGE_NO_NEXT_HTML = """
<html>
<body>
<div class="item">
  <a class="movie-box" href="/IJKL-789">
    <img title="Last Movie" src="https://pics.example/thumb3.jpg" />
    <date>2026-07-17</date>
  </a>
</div>
</body>
</html>
"""

DETAIL_PAGE_HTML = """
<html>
<body>
<div class="screencap">
  <img title="Movie Title One" src="https://pics.example/cover.jpg" />
</div>
<div class="col-md-3 info">
  <p><span class="header">識別碼:</span> ABCD-123</p>
  <p><span class="header">發行日期:</span> 2026-07-15</p>
  <p><span class="header">長度:</span> 120分鐘</p>
  <p><span class="header">導演:</span> Director Name</p>
  <p><span class="header">發行商:</span> Maker Name</p>
  <p><span class="header">系列:</span> Series Name</p>
  <p>
    <span class="header">類別:</span>
    <span class="genre"><a href="/genre/1">Drama</a></span>
    <span class="genre"><a href="/genre/2">Action</a></span>
  </p>
  <p>
    <span class="header">演員:</span>
    <span class="star"><a href="/star/1">Actor A</a></span>
    <span class="star"><a href="/star/2">Actor B</a></span>
  </p>
</div>
<script>
var gid = 12345;
var uc = 678;
var img = 'https://pics.example/cover.jpg';
</script>
</body>
</html>
"""

AJAX_MAGNET_HTML = """
<html>
<body>
<table>
  <tr>
    <td><a href="magnet:?xt=urn:btih:FIRST">ABCD-123-C</a></td>
    <td>2.1 GB<br>12 files</td>
    <td>2026-07-15</td>
    <td><span class="btn">HD</span><span class="btn">中字</span></td>
  </tr>
  <tr>
    <td><a href="magnet:?xt=urn:btih:SECOND">ABCD-123-uncensored</a></td>
    <td>3.5 GB<br>20 files</td>
    <td>2026-07-16</td>
    <td><span class="btn">uncensored</span></td>
  </tr>
</table>
</body>
</html>
"""


def _page(html: str) -> Adaptor:
    return Adaptor(html)


def test_parse_list_page_extracts_items_and_next_url() -> None:
    items, next_url = parse_list_page(_page(LIST_PAGE_HTML), "https://www.javbus.com/page/1")

    assert len(items) == 2
    assert items[0]["url"] == "https://www.javbus.com/ABCD-123"
    assert items[0]["title"] == "Movie Title One"
    assert items[0]["code"] == "ABCD-123"
    assert items[1]["url"] == "https://www.javbus.com/EFGH-456"
    assert items[1]["title"] == "Movie Title Two"
    assert items[1]["code"] == "EFGH-456"
    assert next_url == "https://www.javbus.com/page/2"


def test_parse_list_page_returns_none_when_no_next() -> None:
    items, next_url = parse_list_page(_page(LIST_PAGE_NO_NEXT_HTML), "https://www.javbus.com/page/1")

    assert len(items) == 1
    assert items[0]["code"] == "IJKL-789"
    assert next_url is None


def test_parse_detail_page_extracts_fields() -> None:
    result = parse_detail_page(_page(DETAIL_PAGE_HTML), "https://www.javbus.com/ABCD-123")

    assert result["code"] == "ABCD-123"
    assert result["title"] == "Movie Title One"
    assert result["source_name"] == "Movie Title One"
    assert result["release_date"] == "2026-07-15"
    assert result["duration"] == 120
    assert result["director"] == "Director Name"
    assert result["maker"] == "Maker Name"
    assert result["series"] == "Series Name"
    assert result["tags"] == ["Drama", "Action"]
    assert result["actors"] == ["Actor A", "Actor B"]
    assert result["cover_url"] == "https://pics.example/cover.jpg"
    assert result["source"] == "javbus"
    assert result["source_url"] == "https://www.javbus.com/ABCD-123"


def test_extract_ajax_params_from_detail_page() -> None:
    params = extract_ajax_params(_page(DETAIL_PAGE_HTML))

    assert params["gid"] == "12345"
    assert params["uc"] == "678"
    assert params["img"] == "https://pics.example/cover.jpg"


def test_parse_magnet_ajax_extracts_all_magnets() -> None:
    magnets = parse_magnet_ajax(_page(AJAX_MAGNET_HTML))

    assert len(magnets) == 2
    assert [item["magnet"] for item in magnets] == [
        "magnet:?xt=urn:btih:FIRST",
        "magnet:?xt=urn:btih:SECOND",
    ]
    assert magnets[0]["name"] == "ABCD-123-C"
    assert magnets[0]["size_text"] == "2.1 GB"
    assert magnets[0]["file_text"] == "12 files"
    assert magnets[0]["has_chinese_sub"] is True
    assert magnets[0]["date"] == "2026-07-15"
    assert magnets[1]["has_chinese_sub"] is False
