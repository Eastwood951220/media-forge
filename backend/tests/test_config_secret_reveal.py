import pytest

from backend.app.core.dependencies import get_storage_config_service
from backend.app.main import app
from backend.app.modules.scraping.config import ScrapingConfigService
from backend.app.modules.scraping.schemas import ScrapingConfigUpdate
from backend.app.modules.storage.config.schemas import StorageConfigUpdate
from backend.app.modules.storage.config.service import StorageConfigService
from shared.runtime_config import RuntimeConfigPaths


def test_storage_reveal_requires_login_and_preserves_masked_config(client, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setenv('APP_CONFIG_DIR', str(tmp_path))
    service = StorageConfigService(paths=RuntimeConfigPaths.from_env())
    service.update_config(StorageConfigUpdate(api_token='saved-storage-secret'))
    app.dependency_overrides[get_storage_config_service] = lambda: service
    try:
        assert client.post('/api/storage/config/secret').status_code in (401, 403)
        response = client.post('/api/storage/config/secret', headers=auth_headers)
        assert response.status_code == 200
        assert response.json()['data'] == {'value': 'saved-storage-secret'}
        assert response.headers['cache-control'] == 'no-store'
        assert client.get('/api/storage/config', headers=auth_headers).json()['data']['api_token'] != 'saved-storage-secret'
    finally:
        app.dependency_overrides.pop(get_storage_config_service, None)


@pytest.mark.parametrize('field', ['api_key', 'metatube_token', 'jellyfin_api_key'])
def test_scraping_saved_secret_reveal(client, auth_headers, tmp_path, monkeypatch, field):
    service = ScrapingConfigService(config_file=tmp_path / 'scraping.conf')
    service.update_config(ScrapingConfigUpdate(**{field: 'saved-secret-value'}))
    monkeypatch.setattr('backend.app.modules.scraping.router.ScrapingConfigService', lambda: service)
    url = f'/api/scraping/config/secrets/{field}'
    assert client.post(url).status_code in (401, 403)
    response = client.post(url, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()['data'] == {'value': 'saved-secret-value'}
    assert response.headers['cache-control'] == 'no-store'
    assert client.post('/api/scraping/config/secrets/base_url', headers=auth_headers).status_code == 422
    assert service.get_public_config()[field] != 'saved-secret-value'
