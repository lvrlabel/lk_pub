"""Локальные SSH/SFTP-данные Beget из .env (на сервер не заливаются)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / '.env'
SKIP_UPLOAD_PREFIXES = ('BEGET_SSH_',)


def load_dotenv(path: Path | None = None, overwrite: bool = False) -> None:
    env_path = path or ENV_FILE
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (overwrite or key not in os.environ):
            os.environ[key] = value


def sftp_settings() -> tuple[str, int, str, str]:
    load_dotenv(overwrite=True)
    host = os.environ.get('BEGET_SSH_HOST', 'suppoyyo.beget.tech')
    port = int(os.environ.get('BEGET_SSH_PORT', '22'))
    user = os.environ.get('BEGET_SSH_USER', '')
    password = os.environ.get('BEGET_SSH_PASS', '')
    return host, port, user, password


def env_bytes_without_ssh_secrets(path: Path | None = None) -> bytes:
    """Содержимое .env без собственных SSH-данных деплоя (их не нужно хранить на хостинге)."""
    env_path = path or ENV_FILE
    lines: list[str] = []
    for raw in env_path.read_text(encoding='utf-8').splitlines():
        stripped = raw.strip()
        if any(stripped.startswith(prefix) for prefix in SKIP_UPLOAD_PREFIXES):
            continue
        lines.append(raw)
    return ('\n'.join(lines) + '\n').encode('utf-8')
