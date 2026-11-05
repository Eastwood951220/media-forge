import io
import json
from zipfile import ZipFile

import pytest

from backend.app.modules.backup.config import BackupConfigService
from backend.app.modules.backup.exporters import export_config_files
from backend.app.modules.backup.restorers import restore_config
from backend.app.modules.backup.schemas import BackupConfigUpdate


class MemorySettings:
    values = {}

    def read(self, namespace):
        return dict(self.values.get(namespace, {}))

    def write(self, namespace, values, **kwargs):
        self.values.setdefault(namespace, {}).update(values)


@pytest.fixture
def memory_settings(monkeypatch):
    MemorySettings.values = {}
    monkeypatch.setattr('backend.app.modules.backup.config.SettingsStore', MemorySettings)
    return MemorySettings


def test_default_backup_config_uses_settings_database(memory_settings):
    service = BackupConfigService()
    result = service.update_config(BackupConfigUpdate(enabled=True, retention_count=4))
    assert result.enabled is True
    assert BackupConfigService().get_config().retention_count == 4
    assert memory_settings.values['backup']['retention_count'] == 4


def test_backup_export_includes_all_config_groups_and_filters_secrets(monkeypatch):
    monkeypatch.setattr('backend.app.modules.backup.exporters.read_crawler_config_dict', lambda: {'MAX_LIST_PAGES': 12})
    monkeypatch.setattr('backend.app.modules.backup.exporters.read_movie_filter_config', lambda: {'filters': {'title': {'visible': False}}})
    monkeypatch.setattr('backend.app.modules.backup.exporters.StorageConfigService', lambda: type('Service', (), {'get_raw_config': lambda self: {'api_token': 'storage-secret', 'grpc_host': 'host'}})())
    monkeypatch.setattr('backend.app.modules.backup.exporters.ScrapingConfigService', lambda: type('Service', (), {'get_raw_config': lambda self: {'api_key': 'scrape-secret', 'metatube_token': 'meta-secret', 'jellyfin_api_key': 'jelly-secret', 'metatube_url': 'https://meta'}})())
    monkeypatch.setattr('backend.app.modules.backup.exporters.BackupConfigService', lambda: type('Service', (), {'get_config': lambda self: type('Config', (), {'model_dump': lambda self: {'enabled': True}})()})())
    monkeypatch.setattr('backend.app.modules.backup.exporters.read_cookies', lambda **kwargs: [{'name': 'session', 'value': 'cookie-secret'}])
    for sensitive in (False, True):
        output = io.BytesIO()
        with ZipFile(output, 'w') as archive:
            export_config_files(archive, sensitive)
        with ZipFile(output) as archive:
            assert {'config/crawler_config.json', 'config/movie_filter_config.json', 'config/storage_config.json', 'config/scraping_config.json', 'config/backup_config.json'} <= set(archive.namelist())
            content = b''.join(archive.read(name) for name in archive.namelist())
            for secret in ('storage-secret', 'scrape-secret', 'meta-secret', 'jelly-secret', 'cookie-secret'):
                assert (secret.encode() in content) is sensitive
            assert ('config/javdb_cookies.json' in archive.namelist()) is sensitive


def test_restore_legacy_storage_archive_preserves_omitted_token(monkeypatch):
    written = []
    monkeypatch.setattr('backend.app.modules.storage.config.service.StorageConfigService', lambda: type('Service', (), {'update_config': lambda self, data: written.append(data)})())
    output = io.BytesIO()
    with ZipFile(output, 'w') as archive:
        archive.writestr('config/storage_config.json', json.dumps({'grpc_host': 'legacy-host', 'api_token': 'must-not-restore'}))
    with ZipFile(output) as archive:
        result = restore_config(archive, include_sensitive_in_archive=False)
    assert result.errors == 0
    assert result.updated == 1
    assert written == [{'grpc_host': 'legacy-host'}]


def test_configuration_archive_roundtrip_uses_database_and_preserves_omitted_secrets(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from shared.settings_store import SettingsStore
    from shared.settings_cookies import read_cookies, write_cookies
    from backend.app.modules.scraping.config import ScrapingConfigService
    from backend.app.modules.scraping.schemas import ScrapingConfigUpdate
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.storage.config.schemas import StorageConfigUpdate

    factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr('shared.settings_store.get_session_factory', lambda: factory)
    store = SettingsStore()
    StorageConfigService().update_config(StorageConfigUpdate(api_token='original-storage', grpc_host='archive-host:9798'))
    ScrapingConfigService().update_config(ScrapingConfigUpdate(api_key='original-key', metatube_token='original-meta', jellyfin_api_key='original-jelly', trigger_delay_seconds=45))
    BackupConfigService().update_config(BackupConfigUpdate(retention_count=4))
    write_cookies([{'name': 'session', 'value': 'original-cookie', 'domain': 'javdb.com', 'path': '/'}])

    output = io.BytesIO()
    with ZipFile(output, 'w') as archive:
        export_config_files(archive, include_sensitive=False)
    store.write('storage', {'api_token': 'new-storage', 'grpc_host': 'changed-host:9798'})
    store.write('scraping', {'api_key': 'new-key', 'metatube_token': 'new-meta', 'jellyfin_api_key': 'new-jelly', 'trigger_delay_seconds': 60})
    store.write('backup', {'retention_count': 10})
    with ZipFile(output) as archive:
        stats = restore_config(archive, include_sensitive_in_archive=False)
    assert stats.errors == 0
    assert stats.updated == 5
    assert store.read('storage')['api_token'] == 'new-storage'
    assert store.read('storage')['grpc_host'] == 'archive-host:9798'
    assert {key: store.read('scraping')[key] for key in ('api_key', 'metatube_token', 'jellyfin_api_key')} == {
        'api_key': 'new-key', 'metatube_token': 'new-meta', 'jellyfin_api_key': 'new-jelly',
    }
    assert store.read('scraping')['trigger_delay_seconds'] == 45
    assert store.read('backup')['retention_count'] == 4
    assert read_cookies()[0]['value'] == 'original-cookie'


def test_sensitive_archive_restores_all_site_cookie_settings(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from shared.settings_cookies import COOKIE_FILES, read_cookies, write_cookies

    factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr('shared.settings_store.get_session_factory', lambda: factory)
    for filename, (_key, domain) in COOKIE_FILES.items():
        write_cookies([{'name': 'session', 'value': filename, 'domain': domain, 'path': '/'}], filename=filename)
    output = io.BytesIO()
    with ZipFile(output, 'w') as archive:
        export_config_files(archive, include_sensitive=True)
    for filename in COOKIE_FILES:
        write_cookies([], filename=filename)
    with ZipFile(output) as archive:
        stats = restore_config(archive, include_sensitive_in_archive=True)
    assert stats.errors == 0
    assert stats.updated == 8
    for filename in COOKIE_FILES:
        assert read_cookies(filename=filename)[0]['value'] == filename


def test_restore_refreshes_schedulers_only_after_changed_configs_are_saved(db_session, monkeypatch, tmp_path):
    from unittest.mock import Mock
    from sqlalchemy.orm import sessionmaker
    from backend.app.modules.backup.format import write_manifest
    from backend.app.modules.backup.service import BackupService
    from backend.app.modules.backup.schemas import BackupRestoreRequest
    from shared.settings_store import SettingsStore

    factory = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr('shared.settings_store.get_session_factory', lambda: factory)
    store = SettingsStore()
    calls = []
    backup_refresh = Mock(side_effect=lambda: calls.append(('backup', store.read('backup')['retention_count'])))
    jellyfin_refresh = Mock(side_effect=lambda: calls.append(('jellyfin', store.read('scraping')['jellyfin_watch_sync_time_of_day'])))
    monkeypatch.setattr('backend.app.modules.backup.scheduler.backup_scheduler.refresh', backup_refresh)
    monkeypatch.setattr('backend.app.modules.jellyfin.scheduler.jellyfin_watch_scheduler.configure', jellyfin_refresh)
    path = tmp_path / 'config.mfbackup'
    with ZipFile(path, 'w') as archive:
        write_manifest(archive, {'format': 'media-forge-backup', 'version': 1, 'groups': ['config'], 'include_sensitive': False, 'row_counts': {}})
        archive.writestr('config/backup_config.json', json.dumps({'retention_count': 4}))
        archive.writestr('config/scraping_config.json', json.dumps({'jellyfin_watch_sync_time_of_day': '05:00'}))
    result = BackupService(db_session).restore_from_file(path, BackupRestoreRequest(groups=['config']), owner_id=None)
    assert result['config']['errors'] == 0
    assert calls == [('backup', 4), ('jellyfin', '05:00')]
    calls.clear()
    BackupService(db_session).restore_from_file(path, BackupRestoreRequest(groups=['config']), owner_id=None)
    assert calls == []


def test_failed_config_restore_does_not_refresh_scheduler(db_session, monkeypatch, tmp_path):
    from unittest.mock import Mock
    from sqlalchemy.orm import sessionmaker
    from backend.app.modules.backup.format import write_manifest
    from backend.app.modules.backup.service import BackupService
    from backend.app.modules.backup.schemas import BackupRestoreRequest

    monkeypatch.setattr('shared.settings_store.get_session_factory', lambda: sessionmaker(bind=db_session.get_bind()))
    backup_refresh = Mock()
    jellyfin_refresh = Mock()
    monkeypatch.setattr('backend.app.modules.backup.scheduler.backup_scheduler.refresh', backup_refresh)
    monkeypatch.setattr('backend.app.modules.jellyfin.scheduler.jellyfin_watch_scheduler.configure', jellyfin_refresh)
    path = tmp_path / 'invalid-config.mfbackup'
    with ZipFile(path, 'w') as archive:
        write_manifest(archive, {'format': 'media-forge-backup', 'version': 1, 'groups': ['config'], 'include_sensitive': False, 'row_counts': {}})
        archive.writestr('config/backup_config.json', json.dumps({'retention_count': 0}))
        archive.writestr('config/scraping_config.json', json.dumps({'jellyfin_watch_sync_time_of_day': '99:00'}))
    result = BackupService(db_session).restore_from_file(path, BackupRestoreRequest(groups=['config']), owner_id=None)
    assert result['config']['errors'] == 2
    backup_refresh.assert_not_called()
    jellyfin_refresh.assert_not_called()
