"""Unified settings API; domain routes remain compatible adapters."""
from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Response
from pydantic import ValidationError
from backend.app.core.dependencies import CurrentUser
from shared.schemas.common import success
from shared.settings_store import SettingsStore, SECRET_KEYS

Namespace = Literal['crawler', 'storage', 'scraping', 'backup', 'movie_filters', 'crawler_cookies']
router = APIRouter(prefix='/api/settings', tags=['settings'])


def _schema(namespace):
    from backend.app.modules.crawler.config.schemas import ConfigUpdate, CookiesConfig
    from backend.app.modules.storage.config.schemas import StorageConfigUpdate
    from backend.app.modules.scraping.schemas import ScrapingConfigUpdate
    from backend.app.modules.backup.schemas import BackupConfigUpdate
    from backend.app.modules.content.movies.filter_config import MovieFilterConfigPayload
    return {'crawler': ConfigUpdate, 'storage': StorageConfigUpdate, 'scraping': ScrapingConfigUpdate,
            'backup': BackupConfigUpdate, 'movie_filters': MovieFilterConfigPayload, 'crawler_cookies': CookiesConfig}[namespace]


def read_namespace(namespace):
    if namespace == 'storage':
        from backend.app.modules.storage.config.service import StorageConfigService
        return StorageConfigService().get_config()
    if namespace == 'scraping':
        from backend.app.modules.scraping.config import ScrapingConfigService
        return ScrapingConfigService().get_public_config()
    if namespace == 'backup':
        from backend.app.modules.backup.config import BackupConfigService
        return BackupConfigService().get_config().model_dump()
    if namespace == 'crawler':
        from backend.app.modules.crawler.config.conf_reader import read_crawler_config_dict
        return read_crawler_config_dict()
    if namespace == 'movie_filters':
        from backend.app.modules.content.movies.filter_config import read_movie_filter_config
        return read_movie_filter_config()
    values = SettingsStore().read(namespace)
    return {key: {'configured': bool(values.get(key))} for key in SECRET_KEYS[namespace]}


@router.get('/{namespace}')
def get_settings(namespace: Namespace, _current_user: CurrentUser):
    return success(data=read_namespace(namespace))


@router.put('/{namespace}')
def update_settings(namespace: Namespace, body: dict[str, Any], _current_user: CurrentUser):
    schema = _schema(namespace)
    allowed = SECRET_KEYS[namespace] if namespace == 'crawler_cookies' else set(schema.model_fields)
    if set(body) - allowed:
        raise HTTPException(422, '包含不支持的配置项')
    try:
        if namespace == 'crawler_cookies':
            # Validate the entire request before writing any site.
            data = {key: schema(cookies=value).model_dump()['cookies'] for key, value in body.items()}
            SettingsStore().write(namespace, data)
        else:
            payload = schema(**body)
            if namespace == 'storage':
                from backend.app.modules.storage.config.router import update_storage_config
                from backend.app.modules.storage.config.service import StorageConfigService
                return update_storage_config(payload, _current_user, StorageConfigService())
            if namespace == 'scraping':
                from backend.app.modules.scraping.router import update_scraping_config
                return update_scraping_config(payload, _current_user)
            if namespace == 'backup':
                from backend.app.modules.backup.router import update_backup_config
                return update_backup_config(payload, _current_user)
            if namespace == 'crawler':
                from backend.app.modules.crawler.config.router import update_config
                return update_config(payload, _current_user)
            if namespace == 'movie_filters':
                from backend.app.modules.content.movies.router import update_filter_config
                return update_filter_config(payload, _current_user)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, '配置值校验失败') from exc
    return success(data=read_namespace(namespace))


@router.post('/{namespace}/secrets/{key}')
def reveal_secret(namespace: Namespace, key: str, response: Response, _current_user: CurrentUser):
    if key not in SECRET_KEYS.get(namespace, set()):
        raise HTTPException(404, '不支持的密钥配置项')
    response.headers['Cache-Control'] = 'no-store'
    return success(data={'value': SettingsStore().read(namespace).get(key, '' if namespace != 'crawler_cookies' else [])})
