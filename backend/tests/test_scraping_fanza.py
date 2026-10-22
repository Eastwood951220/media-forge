import json

import httpx

from backend.app.modules.scraping.fanza import FanzaAdapter


def _search_page(products: list[dict]) -> str:
    payload = json.dumps(["$", {"backendResponse": {"contents": {"data": products}}}])
    push = json.dumps([1, "1c:" + payload])
    return f"<html><script>self.__next_f.push({push})</script></html>"


def test_fanza_digital_maps_exact_number_and_distinct_image_candidates() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "www.dmm.co.jp":
            return httpx.Response(200, text=_search_page([
                {"content_id": "mida00819", "detail_url": "https://video.dmm.co.jp/av/content/?id=mida00819"},
            ]))
        assert request.url.host == "api.video.dmm.co.jp"
        return httpx.Response(200, json={"data": {"ppvContent": {
            "id": "mida00819", "makerContentId": "MIDA-819", "title": "Film",
            "description": "summary", "deliveryStartDate": "2025-06-01T00:00:00Z",
            "packageImage": {"largeUrl": "https://img/cover.jpg", "mediumUrl": "https://img/cover-small.jpg"},
            "sampleImages": [{"largeImageUrl": "https://img/preview-1.jpg"}, {"largeImageUrl": "https://img/preview-2.jpg"}],
            "maker": {"name": "Maker"}, "series": {"name": "Series"},
            "actresses": [{"name": "Actor"}], "genres": [{"name": "Genre"}],
        }}})

    result = FanzaAdapter(transport=httpx.MockTransport(handle)).fetch_by_code("MIDA-819")

    assert result is not None
    assert result.site_key == "FANZA"
    assert result.cover_url == "https://img/cover.jpg"
    assert result.preview_urls == ["https://img/preview-1.jpg", "https://img/preview-2.jpg"]
    assert result.premiered == "2025-06-01"
    assert result.studio == "Maker"
    assert result.actors == ["Actor"]
    assert "age_check_done=1" in requests[0].headers["cookie"]
    assert requests[1].headers["fanza-device"] == "BROWSER"


def test_fanza_rejects_lookalike_product_without_detail_request() -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=_search_page([
            {"content_id": "mida00818", "detail_url": "https://video.dmm.co.jp/av/content/?id=mida00818"},
        ]))

    assert FanzaAdapter(transport=httpx.MockTransport(handle)).fetch_by_code("MIDA-819") is None
    assert all("api.video.dmm.co.jp" not in call for call in calls)


def test_fanza_dvd_maps_html_metadata_and_previews() -> None:
    dvd = "https://www.dmm.co.jp/mono/dvd/-/detail/=/cid=mida819/"
    page = '''<html><script type="application/ld+json">{"sku":"mida819","name":"DVD Film","image":"https://img/ps.jpg"}</script>
    <a name="package-image" href="https://img/pl.jpg"></a>
    <table><tr><td>メーカー：</td><td>DVD Maker</td></tr><tr><td>発売日：</td><td>2025/06/02</td></tr></table>
    <div id="sample-image-block"><a name="sample-image"><img data-lazy="https://img/js-1.jpg"></a></div></html>'''

    def handle(request: httpx.Request) -> httpx.Response:
        if "searchstr=" in str(request.url):
            return httpx.Response(200, text=_search_page([{"content_id": "mida819", "detail_url": dvd}]))
        assert str(request.url) == dvd
        return httpx.Response(200, text=page)

    result = FanzaAdapter(transport=httpx.MockTransport(handle)).fetch_by_code("MIDA-819")

    assert result is not None
    assert result.title == "DVD Film"
    assert result.studio == "DVD Maker"
    assert result.premiered == "2025-06-02"
    assert result.cover_url == "https://img/pl.jpg"
    assert result.preview_urls == ["https://img/jp-1.jpg"]


def test_fanza_blocked_or_malformed_source_returns_none() -> None:
    for body in ("<html>not-available-in-your-region</html>", "<html>no payload</html>"):
        adapter = FanzaAdapter(transport=httpx.MockTransport(lambda _request: httpx.Response(200, text=body)))
        assert adapter.fetch_by_code("MIDA-819") is None
