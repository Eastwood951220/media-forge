"""Database-backed business settings. No process cache and no file fallback."""
from typing import Any

from sqlalchemy import select
from shared.database.models.application_setting import ApplicationSetting
from shared.database.session import get_session_factory

SECRET_KEYS = {
    'storage': {'api_token'},
    'scraping': {'api_key', 'metatube_token', 'jellyfin_api_key'},
    'crawler_cookies': {'cookies', 'javbus_cookies', 'avjoho_cookies'},
}
NAMESPACES = frozenset({'crawler', 'storage', 'scraping', 'backup', 'movie_filters', 'crawler_cookies'})


class SettingsStore:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory or get_session_factory()

    def read(self, namespace: str) -> dict[str, Any]:
        with self.session_factory() as session:
            rows = session.scalars(select(ApplicationSetting).where(ApplicationSetting.namespace == namespace, ApplicationSetting.key != "__legacy_imported__")).all()
            return {row.key: row.value for row in rows}

    def legacy_imported(self, namespace: str) -> bool:
        with self.session_factory() as session:
            return session.scalar(select(ApplicationSetting.value).where(
                ApplicationSetting.namespace == namespace,
                ApplicationSetting.key == '__legacy_imported__',
            )) is True

    @staticmethod
    def _write(session, namespace: str, values: dict[str, Any], only_missing: bool):
        if namespace not in NAMESPACES:
            raise ValueError(f'Unknown settings namespace: {namespace}')
        dialect = session.get_bind().dialect.name
        if dialect == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert
        elif dialect == 'sqlite':
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise RuntimeError(f'Unsupported settings database: {dialect}')
        for key, value in values.items():
            statement = insert(ApplicationSetting).values(namespace=namespace, key=key, value=value,
                is_secret=key in SECRET_KEYS.get(namespace, set()))
            if only_missing:
                statement = statement.on_conflict_do_nothing(index_elements=['namespace', 'key'])
            else:
                from sqlalchemy import func
                statement = statement.on_conflict_do_update(index_elements=['namespace', 'key'],
                    set_={'value': statement.excluded.value, 'is_secret': statement.excluded.is_secret, 'updated_at': func.now()})
            session.execute(statement)

    def write(self, namespace: str, values: dict[str, Any], only_missing: bool = False) -> None:
        with self.session_factory.begin() as session:
            self._write(session, namespace, values, only_missing)

    def import_namespaces(self, values: dict[str, dict[str, Any]], *, mark_imported: bool = False) -> None:
        with self.session_factory.begin() as session:
            for namespace, data in values.items():
                self._write(session, namespace, data, only_missing=True)
                if mark_imported:
                    self._write(session, namespace, {"__legacy_imported__": True}, only_missing=True)
