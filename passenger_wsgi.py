# -*- coding: utf-8 -*-
"""WSGI для Phusion Passenger (Beget). Без захардкоженных путей к серверу."""
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))

# Если рядом с сайтом есть venv — переключаемся на него.
# Если venv нет — НЕ падаем, а просто продолжаем работать на том Python,
# который уже запустил Passenger (в отличие от старой версии файла).
for _cand in (
    os.path.join(_ROOT, 'venv', 'bin', 'python3'),
    os.path.join(_ROOT, 'venv', 'bin', 'python'),
):
    if os.path.isfile(_cand) and os.path.realpath(sys.executable) != os.path.realpath(_cand):
        os.execl(_cand, _cand, *sys.argv)

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

for _site in sorted(
    glob.glob(os.path.join(_ROOT, 'venv', 'lib', 'python*', 'site-packages')),
    reverse=True,
):
    if _site not in sys.path:
        sys.path.insert(0, _site)

try:
    import site
    _user_site = site.getusersitepackages()
    if _user_site and _user_site not in sys.path:
        sys.path.insert(0, _user_site)
    for _cand in (
        os.path.join(_ROOT, '.local', 'lib', 'python3.10', 'site-packages'),
        os.path.join(_ROOT, '.local', 'lib', 'python3.11', 'site-packages'),
        os.path.join(_ROOT, '.local', 'lib', 'python3.12', 'site-packages'),
        os.path.expanduser('~/.local/lib/python3.10/site-packages'),
        os.path.expanduser('~/.local/lib/python3.11/site-packages'),
        os.path.expanduser('~/.local/lib/python3.12/site-packages'),
    ):
        if os.path.isdir(_cand) and _cand not in sys.path:
            sys.path.insert(0, _cand)
except Exception:
    pass

from run import app as application
