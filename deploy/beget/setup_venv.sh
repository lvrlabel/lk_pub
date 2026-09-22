#!/usr/bin/env bash
# Запускать из корня сайта на сервере: bash deploy/beget/setup_venv.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
echo "Каталог: $(pwd)"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
PY="$(readlink -f venv/bin/python 2>/dev/null || realpath venv/bin/python)"
echo ""
echo "Добавьте в .htaccess строку (или замените PassengerPython):"
echo "PassengerPython $PY"
