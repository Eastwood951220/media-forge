import pytest
from shared.settings_store import SettingsStore


def test_partial_updates_and_idempotent_import(db_session):
    store = SettingsStore()
    store.write('storage', {'api_token': 'secret', 'request_timeout_seconds': 10})
    store.write('storage', {'request_timeout_seconds': 20})
    store.import_namespaces({'storage': {'api_token': 'old-file', 'connect_timeout_seconds': 5}})
    assert store.read('storage') == {'api_token': 'secret', 'request_timeout_seconds': 20, 'connect_timeout_seconds': 5}


def test_import_is_atomic():
    store = SettingsStore()
    with pytest.raises(ValueError):
        store.import_namespaces({'crawler': {'MAX_LIST_PAGES': 8}, 'invalid': {'value': 1}})
    assert store.read('crawler') == {}
