from datetime import date, datetime
from pathlib import Path

from backend.app.modules.scraping.nfo import render_movie_nfo, write_movie_nfo
from shared.database.models.content import Movie


def _movie(**overrides) -> Movie:
    values = dict(
        code="ADN-784",
        source_name="ADN-784 あなた、許して…。 心まで盗まれて",
        release_date=date(2026, 7, 3),
        maker="アタッカーズ",
        series="あなた、許して…。",
        tags=["ドラマ", "不倫"],
        actors=["北野未奈"],
    )
    values.update(overrides)
    return Movie(**values)


def test_render_movie_nfo_matches_metatube_shape() -> None:
    text = render_movie_nfo(
        _movie(),
        cloud_folder="/media/北野未奈/ADN-784",
        source_site="JavBus",
        dateadded=datetime(2026, 10, 20, 12, 0, 0),
    )

    assert text.startswith('<?xml version="1.0" encoding="utf-8" standalone="yes"?>')
    assert "<title>ADN-784 あなた、許して…。 心まで盗まれて</title>" in text
    assert "<originaltitle>あなた、許して…。 心まで盗まれて</originaltitle>" in text
    assert "<year>2026</year>" in text
    assert "<mpaa>JP-18+</mpaa>" in text
    assert "<premiered>2026-07-03</premiered>" in text
    assert "<releasedate>2026-07-03</releasedate>" in text
    assert "<tagline>配信開始日 2026-07-03</tagline>" in text
    assert "<genre>ドラマ</genre>" in text
    assert "<studio>アタッカーズ</studio>" in text
    assert "<metatubeid>JavBus:ADN-784</metatubeid>" in text
    assert "<poster>/media/北野未奈/ADN-784/folder.jpg</poster>" in text
    assert "<fanart>/media/北野未奈/ADN-784/backdrop.jpg</fanart>" in text
    assert "<name>あなた、許して…。</name>" in text


def test_render_movie_nfo_omits_metatubeid_without_source() -> None:
    text = render_movie_nfo(_movie(), cloud_folder="/media/ADN-784")
    assert "<metatubeid>" not in text


def test_render_movie_nfo_escapes_xml() -> None:
    text = render_movie_nfo(
        _movie(code="ADN-784", source_name='ADN-784 A & B <C>'),
        cloud_folder="/media/ADN-784",
    )
    assert "A &amp; B &lt;C&gt;" in text


def test_write_movie_nfo_is_atomic_and_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "movie.nfo"
    target.write_text("old", encoding="utf-8")

    write_movie_nfo(tmp_path, _movie(), cloud_folder="/media/ADN-784")

    assert "ADN-784" in target.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.tmp"))
