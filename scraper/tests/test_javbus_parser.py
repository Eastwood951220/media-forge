from scrapling.parser import Adaptor

from scraper.spiders.javbus.javbus_parser import (
    extract_ajax_params,
    parse_detail_page,
    parse_javbus_url_name,
    parse_list_page,
    parse_magnet_ajax,
)

LIST_PAGE_HTML = """
<html>
<body>
<div class="item">
  <a class="movie-box" href="/ABCD-123">
    <img title="Movie Title One" src="https://pics.example/thumb1.jpg" />
    <date>ABCD-123</date> / <date>2026-07-15</date>
  </a>
</div>
<div class="item">
  <a class="movie-box" href="/EFGH-456">
    <img title="Movie Title Two" src="https://pics.example/thumb2.jpg" />
    <date>EFGH-456</date> / <date>2026-07-16</date>
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
    <date>IJKL-789</date> / <date>2026-07-17</date>
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
    assert items[0]["cover_url"] == "https://pics.example/thumb1.jpg"
    assert items[0]["release_date"] == "2026-07-15"
    assert items[1]["url"] == "https://www.javbus.com/EFGH-456"
    assert items[1]["title"] == "Movie Title Two"
    assert items[1]["code"] == "EFGH-456"
    assert next_url == "https://www.javbus.com/page/2"


def test_parse_list_page_returns_none_when_no_next() -> None:
    items, next_url = parse_list_page(_page(LIST_PAGE_NO_NEXT_HTML), "https://www.javbus.com/page/1")

    assert len(items) == 1
    assert items[0]["code"] == "IJKL-789"
    assert items[0]["cover_url"] == "https://pics.example/thumb3.jpg"
    assert items[0]["release_date"] == "2026-07-17"
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


# --- Real JavBus markup fixtures ---

REAL_DETAIL_HTML = """
<div class="container">
  <h3>CEMD-869 もしも人気AV女優と同棲したら 波多野結衣</h3>
  <div class="row movie">
    <div class="col-md-9 screencap">
      <img src="/pics/cover/cdor_b.jpg"
           title="もしも人気AV女優と同棲したら 波多野結衣">
    </div>
    <div class="col-md-3 info">
      <p><span class="header">識別碼:</span>
         <span style="color:#CC0000;">CEMD-869</span></p>
      <p><span class="header">發行日期:</span> 2026-07-25</p>
      <p><span class="header">長度:</span> 134分鐘</p>
      <p><span class="header">導演:</span><a>ケンタブリトニー</a></p>
      <p><span class="header">製作商:</span><a>セレブの友</a></p>
      <p class="header">類別:</p>
      <p>
        <span class="genre"><a>成熟的女人</a></span>
        <span class="genre"><a>高畫質</a></span>
      </p>
      <p class="star-show"><span class="header">演員</span>:</p>
    </div>
  </div>
  <div id="star-div">
    <a class="avatar-box"><span>波多野結衣</span></a>
  </div>
</div>
"""


def test_parse_real_detail_does_not_use_label_as_code() -> None:
    result = parse_detail_page(
        _page(REAL_DETAIL_HTML),
        "https://www.javbus.com/CEMD-869",
    )

    assert result["code"] == "CEMD-869"
    assert result["code"] != "識別碼:"
    assert result["release_date"] == "2026-07-25"
    assert result["duration"] == 134
    assert result["director"] == "ケンタブリトニー"
    assert result["maker"] == "セレブの友"
    assert result["tags"] == ["成熟的女人", "高畫質"]
    assert result["actors"] == ["波多野結衣"]
    assert result["cover_url"] == "https://www.javbus.com/pics/cover/cdor_b.jpg"


STAR_LIST_HEADER_HTML = """
<div class="alert alert-success alert-common">
  <p><b>波多野結衣 - 女優 - 影片</b>
     &nbsp;：&nbsp;當前顯示<b>已有磁力 2337</b>部</p>
</div>
"""


def test_parse_javbus_url_name_extracts_primary_name() -> None:
    assert parse_javbus_url_name(_page(STAR_LIST_HEADER_HTML)) == "波多野結衣"


def test_parse_detail_page_keeps_missing_cover_empty() -> None:
    html = """
    <div class="screencap"><img title="No Cover"></div>
    <div class="col-md-3 info">
      <p><span class="header">識別碼:</span> AAA-001</p>
    </div>
    """

    result = parse_detail_page(
        _page(html),
        "https://www.javbus.com/AAA-001",
    )

    assert result["cover_url"] == ""


REAL_LIST_PAGE_HTML = """
<html>
<body>
<div id="waterfall">
  <div class="item masonry-brick">
    <div class="avatar-box">
      <div class="photo-frame">
        <img src="/pics/actress/10uz_a.jpg" title="羽月乃蒼">
      </div>
      <div class="photo-info"><span class="pb10">羽月乃蒼</span></div>
    </div>
  </div>
  <div class="item masonry-brick">
    <a class="movie-box" href="https://www.javbus.com/TIKB-224">
      <div class="photo-frame">
        <img src="/pics/thumb/cedm.jpg"
             title="巨乳変態言いなりメイドがドMご奉仕でお漏らしイキ！ 羽月乃蒼">
      </div>
      <div class="photo-info">
        <span>
          巨乳変態言いなりメイドがドMご奉仕でお漏らしイキ！ 羽月乃蒼
          <div class="item-tag">
            <button class="btn btn-xs btn-primary">高清</button>
            <button class="btn btn-xs btn-success">昨日新種</button>
          </div>
          <date>TIKB-224</date> / <date>2026-07-18</date>
        </span>
      </div>
    </a>
  </div>
  <div class="item masonry-brick">
    <a class="movie-box" href="/IENF-451_2026-07-08">
      <div class="photo-frame">
        <img src="/pics/thumb/cf7r.jpg" title="マジ！？これ実習？">
      </div>
      <div class="photo-info">
        <span>
          マジ！？これ実習？
          <div class="item-tag"><button>高清</button></div>
          <date>IENF-451</date> / <date>2026-07-08</date>
        </span>
      </div>
    </a>
  </div>
</div>
<a id="next" href="/star/10uz/2">下一頁</a>
</body>
</html>
"""


def test_parse_real_list_page_extracts_metadata_without_tags() -> None:
    items, next_url = parse_list_page(
        _page(REAL_LIST_PAGE_HTML),
        "https://www.javbus.com/star/10uz",
    )

    assert items == [
        {
            "url": "https://www.javbus.com/TIKB-224",
            "title": "巨乳変態言いなりメイドがドMご奉仕でお漏らしイキ！ 羽月乃蒼",
            "code": "TIKB-224",
            "cover_url": "https://www.javbus.com/pics/thumb/cedm.jpg",
            "release_date": "2026-07-18",
        },
        {
            "url": "https://www.javbus.com/IENF-451_2026-07-08",
            "title": "マジ！？これ実習？",
            "code": "IENF-451",
            "cover_url": "https://www.javbus.com/pics/thumb/cf7r.jpg",
            "release_date": "2026-07-08",
        },
    ]
    assert next_url == "https://www.javbus.com/star/10uz/2"
    assert all("tags" not in item for item in items)


def test_parse_list_page_keeps_item_when_optional_metadata_is_missing() -> None:
    html = """
    <div class="item">
      <a class="movie-box" href="/ABCD-123">
        <div class="photo-frame"><img></div>
        <date>ABCD-123</date>
      </a>
    </div>
    """

    items, next_url = parse_list_page(
        _page(html),
        "https://www.javbus.com/star/example",
    )

    assert items == [{
        "url": "https://www.javbus.com/ABCD-123",
        "title": "",
        "code": "ABCD-123",
        "cover_url": "",
        "release_date": "",
    }]
    assert next_url is None


REAL_MAGNET_HTML = """
<tr>
  <td width="70%">
    <a href="magnet:?xt=urn:btih:HASH&dn=TIKB-224">
      TIKB-224
      <a class="btn btn-mini-new btn-primary disabled">高清</a>
    </a>
  </td>
  <td><a href="magnet:?xt=urn:btih:HASH&dn=TIKB-224">7.09GB</a></td>
  <td><a href="magnet:?xt=urn:btih:HASH&dn=TIKB-224">2026-07-21</a></td>
</tr>
"""


def test_parse_real_magnet_row_extracts_nested_values() -> None:
    magnets = parse_magnet_ajax(_page(REAL_MAGNET_HTML))

    assert magnets == [{
        "magnet": "magnet:?xt=urn:btih:HASH&dn=TIKB-224",
        "name": "TIKB-224",
        "size_text": "7.09GB",
        "file_text": "",
        "file_count": None,
        "tags": ["高清"],
        "has_chinese_sub": False,
        "date": "2026-07-21",
    }]
