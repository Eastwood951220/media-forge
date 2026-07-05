from __future__ import annotations

from pathlib import Path

from shared.runtime_config import PROJECT_ROOT


def read_incremental_threshold_from_conf(base_dir: Path | None = None) -> int:
    root = base_dir or PROJECT_ROOT
    conf_path = root / "data" / "configs" / "crawler.conf"
    if not conf_path.exists():
        return 0
    for line in conf_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == "INCREMENTAL_EXIST_THRESHOLD":
            try:
                return int(value.strip())
            except (TypeError, ValueError):
                return 0
    return 0
