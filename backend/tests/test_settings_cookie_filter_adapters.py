import json

import pytest

from backend.app.modules.content.movies.filter_config import read_movie_filter_config, write_movie_filter_config
from scraper.cookies.cookie_manager import CookieManager
from shared.settings_cookies import read_cookies, read_legacy_cookies, write_cookies


def test_movie_query_configuration_reads_latest_database_values(tmp_path):
    filters = {
        'actors': {'visible': False, 'order': 7, 'defaultValue': ['演员一', '演员二']},
        'sortBy': {'visible': True, 'order': 1, 'defaultValue': 'rating:-1'},
    }
    saved = write_movie_filter_config(filters)
    assert read_movie_filter_config()['filters'] == filters
    assert read_movie_filter_config()['updated_at'] == saved['updated_at']
    write_movie_filter_config({'code': {'visible': True, 'order': 0}})
    assert read_movie_filter_config()['filters'] == {'code': {'visible': True, 'order': 0}}


def test_scraper_and_backend_share_cookies_without_cross_site_leakage(tmp_path):
    write_cookies([{'name': 'session', 'value': 'javdb-secret', 'domain': 'javdb.com'}])
    CookieManager('javbus_cookies.json').save({'session': 'javbus-secret'})
    assert CookieManager('javdb_cookies.json').load() == {'session': 'javdb-secret'}
    assert CookieManager('javbus_cookies.json').load() == {'session': 'javbus-secret'}
    assert CookieManager('avjoho_cookies.json').load() == {}
    assert read_cookies()[0]['value'] == 'javdb-secret'


def test_explicit_legacy_cookie_import_preserves_browser_attributes(tmp_path):
    path = tmp_path / 'javdb_cookies.json'
    rows = [{'name': 'session', 'value': 'secret', 'domain': '.javdb.com', 'httpOnly': True, 'secure': True}]
    path.write_text(json.dumps(rows), encoding='utf-8')
    write_cookies(read_legacy_cookies(path))
    assert CookieManager('javdb_cookies.json').load_browser_cookies() == rows


def test_database_error_does_not_fall_back_to_a_cookie_file(monkeypatch, tmp_path):
    path = tmp_path / 'javdb_cookies.json'
    path.write_text('{"session":"stale-value"}', encoding='utf-8')
    monkeypatch.setattr('scraper.cookies.cookie_manager.COOKIE_DIR', tmp_path)

    class UnavailableStore:
        def read(self, namespace):
            raise RuntimeError('database unavailable')

    with pytest.raises(RuntimeError, match='database unavailable'):
        CookieManager('javdb_cookies.json', store=UnavailableStore()).load()


def test_legacy_movie_query_configuration_adapter_is_explicit(tmp_path):
    path = tmp_path / 'movie_filter_config.json'
    path.write_text(json.dumps({'filters': {'actors': {'visible': False, 'order': 4, 'defaultValue': 'A'}}}), encoding='utf-8')
    assert read_movie_filter_config(legacy_path=path)['filters']['actors']['order'] == 4
    assert read_movie_filter_config()['filters'] == {}


def test_invalid_legacy_configuration_is_not_silently_imported_as_empty(tmp_path):
    filters = tmp_path / 'movie_filter_config.json'
    filters.write_text('{"filters": []}', encoding='utf-8')
    with pytest.raises(ValueError, match='Invalid legacy movie filter'):
        read_movie_filter_config(legacy_path=filters)
    cookies = tmp_path / 'javdb_cookies.json'
    cookies.write_text('"not cookie data"', encoding='utf-8')
    with pytest.raises(ValueError, match='Invalid legacy cookie'):
        read_legacy_cookies(cookies)
