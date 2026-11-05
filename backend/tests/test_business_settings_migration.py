import json
from shared.runtime_config import RuntimeConfigPaths
from shared.settings_store import SettingsStore
from backend.app.core.business_settings import initialize_business_settings


def test_import_legacy_files_once_and_preserve_database_changes(tmp_path, monkeypatch):
    config_dir = tmp_path / 'data/configs'
    config_dir.mkdir(parents=True)
    monkeypatch.setenv('APP_CONFIG_DIR', str(config_dir))
    (config_dir / 'storage.conf').write_text('api_token=original-token\nrequest_timeout_seconds=80\n')
    (config_dir / 'scraping.conf').write_text('base_url=http://example.com\napi_key=saved-key\n')
    (config_dir / 'crawler.conf').write_text('REQUEST_TIMEOUT=45\n')
    (config_dir / 'movie_filter_config.json').write_text(json.dumps({'filters': {'keyword': {'visible': False, 'order': 3, 'defaultValue': 'abc'}}}))
    cookie_dir = tmp_path / 'data/cookies'
    cookie_dir.mkdir(parents=True)
    (cookie_dir / 'javdb_cookies.json').write_text('{"session": "secret"}')
    store = SettingsStore()
    initialize_business_settings(paths=RuntimeConfigPaths.from_env(), project_root=tmp_path, store=store)
    assert store.read('storage')['api_token'] == 'original-token'
    assert store.read('crawler')['REQUEST_TIMEOUT'] == 45
    assert store.read('movie_filters')['filters']['keyword']['defaultValue'] == 'abc'
    assert store.read('crawler_cookies')['cookies'][0]['value'] == 'secret'
    store.write('storage', {'api_token': 'new-token'})
    (config_dir / 'movie_filter_config.json').write_text('invalid stale file')
    initialize_business_settings(paths=RuntimeConfigPaths.from_env(), project_root=tmp_path, store=store)
    assert store.read('storage')['api_token'] == 'new-token'
    assert (config_dir / 'storage.conf').read_text().startswith('api_token=original-token')


def test_unified_api_masks_secrets_and_validates_fields(client, auth_headers):
    assert client.get('/api/settings/storage').status_code in (401, 403)
    result = client.put('/api/settings/storage', json={'api_token': 'unified-secret'}, headers=auth_headers)
    assert result.status_code == 200
    assert 'unified-secret' not in result.text
    result = client.post('/api/settings/storage/secrets/api_token', headers=auth_headers)
    assert result.json()['data']['value'] == 'unified-secret'
    assert result.headers['cache-control'] == 'no-store'
    assert client.put('/api/settings/storage', json={'unknown': 4}, headers=auth_headers).status_code == 422
    assert client.put('/api/settings/storage', json={'request_timeout_seconds': -1}, headers=auth_headers).status_code == 422
    assert client.post('/api/settings/storage/secrets/grpc_host', headers=auth_headers).status_code == 404


def test_failed_import_does_not_commit_any_namespace(tmp_path, monkeypatch):
    import pytest
    config_dir = tmp_path / 'data/configs'
    config_dir.mkdir(parents=True)
    monkeypatch.setenv('APP_CONFIG_DIR', str(config_dir))
    (config_dir / 'storage.conf').write_text('api_token=original-token\n')
    (config_dir / 'movie_filter_config.json').write_text('invalid JSON')
    store = SettingsStore()
    with pytest.raises(ValueError):
        initialize_business_settings(paths=RuntimeConfigPaths.from_env(), project_root=tmp_path, store=store)
    assert store.read('storage') == {}
    assert not store.legacy_imported('storage')


def test_bootstrap_adds_settings_table_to_existing_database(tmp_path, monkeypatch):
    from shared.database.models.application_setting import ApplicationSetting
    from sqlalchemy import inspect
    config_dir = tmp_path / 'data/configs'
    config_dir.mkdir(parents=True)
    monkeypatch.setenv('APP_CONFIG_DIR', str(config_dir))
    store = SettingsStore()
    with store.session_factory() as session:
        engine = session.get_bind()
    ApplicationSetting.__table__.drop(engine)
    initialize_business_settings(paths=RuntimeConfigPaths.from_env(), project_root=tmp_path, store=store)
    assert inspect(engine).has_table('application_settings')
    assert store.legacy_imported('storage')


def test_unified_updates_are_visible_through_legacy_apis(client, auth_headers, monkeypatch):
    from backend.app.modules.backup.scheduler import backup_scheduler
    from backend.app.modules.jellyfin.scheduler import jellyfin_watch_scheduler
    monkeypatch.setattr(backup_scheduler, 'refresh', lambda: None)
    monkeypatch.setattr(jellyfin_watch_scheduler, 'configure', lambda: None)
    cases = [
        ('crawler', {'REQUEST_TIMEOUT': 52}, '/api/crawler/config', 'REQUEST_TIMEOUT', 52),
        ('storage', {'grpc_host': 'localhost:1234'}, '/api/storage/config', 'grpc_host', 'localhost:1234'),
        ('scraping', {'base_url': 'http://example.com/'}, '/api/scraping/config', 'base_url', 'http://example.com'),
        ('backup', {'retention_count': 7}, '/api/backup/config', 'retention_count', 7),
        ('movie_filters', {'filters': {'code': {'visible': False, 'order': 3, 'defaultValue': 'ABC'}}}, '/api/content/movies/filter-config', 'filters', {'code': {'visible': False, 'order': 3, 'defaultValue': 'ABC'}}),
        ('crawler_cookies', {'cookies': [{'name': 'session', 'value': 'cookie-secret', 'domain': 'javdb.com'}]}, '/api/crawler/config/cookies', 'cookies', None),
    ]
    for namespace, payload, old_url, key, expected in cases:
        response = client.put(f'/api/settings/{namespace}', json=payload, headers=auth_headers)
        assert response.status_code == 200, response.text
        legacy = client.get(old_url, headers=auth_headers)
        assert legacy.status_code == 200, legacy.text
        if expected is not None:
            assert legacy.json()['data'][key] == expected
        else:
            assert legacy.json()['data'][key][0]['value'] == 'cookie-secret'
            assert 'cookie-secret' not in response.text
