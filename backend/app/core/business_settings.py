"""Bootstrap the settings table and import legacy files before starting workers."""
from pathlib import Path

from shared.database.models.application_setting import ApplicationSetting
from shared.runtime_config import PROJECT_ROOT, RuntimeConfigPaths
from shared.settings_store import SettingsStore, NAMESPACES


def initialize_business_settings(*, paths=None, project_root: Path | None = None, store=None):
    root = project_root or PROJECT_ROOT
    paths = paths or RuntimeConfigPaths.from_env()
    store = store or SettingsStore()
    with store.session_factory() as session:
        # Existing installations do not always run Alembic automatically. This
        # additive table readiness check is also safe before the matching revision.
        ApplicationSetting.__table__.create(session.get_bind(), checkfirst=True)
    from backend.app.modules.storage.config.service import StorageConfigService
    from backend.app.modules.scraping.config import ScrapingConfigService
    from backend.app.modules.backup.config import BackupConfigService
    from backend.app.modules.crawler.config.conf_reader import read_crawler_config_dict, crawler_conf_path
    from backend.app.modules.content.movies.filter_config import read_movie_filter_config
    from shared.settings_cookies import COOKIE_FILES, read_legacy_cookies
    from scraper.config.settings import COOKIE_DIR

    pending = {namespace for namespace in NAMESPACES if not store.legacy_imported(namespace)}
    values = {namespace: {} for namespace in pending}
    if 'storage' in pending and paths.storage_file.exists():
        values['storage'] = StorageConfigService(paths=paths).get_raw_config()
    scraping_file = paths.config_dir / 'scraping.conf'
    if 'scraping' in pending and scraping_file.exists():
        values['scraping'] = ScrapingConfigService(config_file=scraping_file).get_raw_config()
    backup_file = root / 'data/configs/backup.conf'
    if 'backup' in pending and backup_file.exists():
        values['backup'] = BackupConfigService(config_file=backup_file, project_root=root).get_config().model_dump()
    if 'crawler' in pending and crawler_conf_path(root).exists():
        values['crawler'] = read_crawler_config_dict(base_dir=root)
    filter_file = root / 'data/configs/movie_filter_config.json'
    if 'movie_filters' in pending and filter_file.exists():
        config = read_movie_filter_config(legacy_path=filter_file)
        values['movie_filters'] = {key: value for key, value in config.items() if key in {'filters', 'updated_at'} and value is not None}
    cookies = {}
    cookie_dir = root / 'data/cookies' if project_root is not None else COOKIE_DIR
    for filename, (key, _domain) in COOKIE_FILES.items():
        file = cookie_dir / filename
        if 'crawler_cookies' in pending and file.exists():
            cookies[key] = read_legacy_cookies(file)
    if cookies:
        values['crawler_cookies'] = cookies
    store.import_namespaces(values, mark_imported=True)
    return {namespace: len(data) for namespace, data in values.items()}
