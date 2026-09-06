from pathlib import Path

from backend.app.modules.backup.config import BackupConfigService


def test_backup_config_api_round_trip(client, auth_headers, tmp_path: Path, monkeypatch):
    config_file = tmp_path / "backup.conf"
    monkeypatch.setattr(
        "backend.app.modules.backup.router.get_backup_config_service",
        lambda: BackupConfigService(config_file=config_file, project_root=tmp_path),
    )

    response = client.put("/api/backup/config", headers=auth_headers, json={
        "enabled": True,
        "backup_dir": str(tmp_path / "backups"),
        "schedule_type": "daily",
        "time_of_day": "04:15",
        "groups": ["movies"],
        "include_sensitive": False,
        "retention_count": 2,
    })

    assert response.status_code == 200
    assert response.json()["data"]["enabled"] is True
    assert response.json()["data"]["groups"] == ["movies"]


def test_backup_file_delete_rejects_traversal(client, auth_headers):
    response = client.delete("/api/backup/files/..%2Fescape.mfbackup", headers=auth_headers)

    assert response.status_code in {400, 404}
