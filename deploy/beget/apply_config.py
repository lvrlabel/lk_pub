#!/usr/bin/env python3
"""
Деплой .env на Beget по SFTP (порт 22) + сигнал перезапуска Passenger.

Загружает .env (без деплойных SSH-секретов BEGET_SSH_*) в public_html сайта
и создаёт tmp/restart.txt, чтобы Passenger перечитал конфигурацию.

Использование:
    pip install paramiko
    python deploy/beget/apply_config.py

Путь на сервере по умолчанию — public_html/.env (корень сайта на Beget).
Если структура другая, переопределите через --remote-dir.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("Нужен пакет paramiko: pip install paramiko", file=sys.stderr)
    raise SystemExit(1)

from beget_env import env_bytes_without_ssh_secrets, sftp_settings

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / '.env'


def _ensure_dir(sftp: "paramiko.SFTPClient", remote_dir: str) -> None:
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        sftp.mkdir(remote_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--remote-dir",
        default="public_html",
        help="Каталог сайта на Beget, где лежит .env (по умолчанию public_html)",
    )
    parser.add_argument(
        "--skip-restart",
        action="store_true",
        help="Не создавать tmp/restart.txt (не перезапускать Passenger)",
    )
    args = parser.parse_args()

    host, port, user, password = sftp_settings()
    if not user or not password:
        print("Не заданы BEGET_SSH_USER / BEGET_SSH_PASS (проверьте .env).", file=sys.stderr)
        return 1
    if not ENV_FILE.is_file():
        print(f"Не найден локальный файл: {ENV_FILE}", file=sys.stderr)
        return 1

    print(f"Подключение к {host}:{port} как {user}...")
    transport = paramiko.Transport((host, port))
    try:
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            remote_env = f"{args.remote_dir}/.env"
            print(f"Загрузка .env -> {remote_env}")
            content = env_bytes_without_ssh_secrets(ENV_FILE)
            with sftp.open(remote_env, "wb") as f:
                f.write(content)
            print("  готово.")

            if not args.skip_restart:
                tmp_dir = f"{args.remote_dir}/tmp"
                _ensure_dir(sftp, tmp_dir)
                restart_path = f"{tmp_dir}/restart.txt"
                with sftp.open(restart_path, "wb") as f:
                    f.write(b"restart\n")
                print(f"  перезапуск Passenger: {restart_path}")
        finally:
            sftp.close()
    finally:
        transport.close()

    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
