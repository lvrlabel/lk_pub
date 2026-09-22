"""
Текст юридических уведомлений на главной: хранение в instance/dashboard_legal_notice.json.
Поддерживается несколько блоков; у каждого тон: red | orange.
"""

import json
import os

from flask import current_app

DEFAULT_NOTICE_ITEM = {
    'enabled': False,
    'tone': 'red',
    'badge': 'Обязательно к сведению',
    'title': 'Важно',
    'lead': '',
    'points': [],
    'callout': '',
}

_VALID_TONES = frozenset({'red', 'orange'})


def _coerce_enabled(val):
    """Из JSON или формы: включено ли уведомление."""
    if val is True:
        return True
    if val is False or val is None:
        return False
    if isinstance(val, (int, float)):
        return int(val) != 0
    s = str(val).strip().lower()
    return s in ('1', 'true', 'yes', 'on')


def _notice_path():
    return os.path.join(current_app.instance_path, 'dashboard_legal_notice.json')


def _normalize_points(val):
    if not isinstance(val, list):
        return []
    return [str(p).strip() for p in val if str(p).strip()]


def _normalize_item(raw):
    if not isinstance(raw, dict):
        return dict(DEFAULT_NOTICE_ITEM)
    out = dict(DEFAULT_NOTICE_ITEM)
    out.update(raw)
    tone = str(out.get('tone') or 'red').strip().lower()
    out['tone'] = tone if tone in _VALID_TONES else 'red'
    out['enabled'] = _coerce_enabled(out.get('enabled'))
    out['badge'] = str(out.get('badge') or DEFAULT_NOTICE_ITEM['badge']).strip() or DEFAULT_NOTICE_ITEM['badge']
    out['title'] = str(out.get('title') or DEFAULT_NOTICE_ITEM['title']).strip() or DEFAULT_NOTICE_ITEM['title']
    out['lead'] = str(out.get('lead') or '').strip()
    out['callout'] = str(out.get('callout') or '').strip()
    out['points'] = _normalize_points(out.get('points'))
    return out


def _legacy_flat_to_notices(data):
    """Старый формат: один объект с полями enabled, title, …"""
    item = dict(DEFAULT_NOTICE_ITEM)
    item['enabled'] = _coerce_enabled(data.get('enabled'))
    item['tone'] = 'red'
    if str(data.get('badge') or '').strip():
        item['badge'] = str(data.get('badge')).strip()
    if str(data.get('title') or '').strip():
        item['title'] = str(data.get('title')).strip()
    item['lead'] = str(data.get('lead') or '').strip()
    item['points'] = _normalize_points(data.get('points'))
    item['callout'] = str(data.get('callout') or '').strip()
    return [item]


def load_dashboard_legal_notice():
    """Словарь {'notices': […]} для формы редактирования."""
    path = _notice_path()
    if not os.path.isfile(path):
        return {'notices': [dict(DEFAULT_NOTICE_ITEM)]}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return {'notices': [dict(DEFAULT_NOTICE_ITEM)]}

    if not isinstance(data, dict):
        return {'notices': [dict(DEFAULT_NOTICE_ITEM)]}

    if isinstance(data.get('notices'), list):
        if data['notices']:
            notices = [_normalize_item(x) for x in data['notices']]
            return {'notices': notices}
        return {'notices': [dict(DEFAULT_NOTICE_ITEM)]}

    # Файл в старом плоском виду
    return {'notices': _legacy_flat_to_notices(data)}


def save_dashboard_legal_notice(data):
    """Сохранить JSON в instance."""
    path = _notice_path()
    inst_dir = current_app.instance_path
    if inst_dir:
        os.makedirs(inst_dir, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _item_has_visible_content(n):
    parts = [
        (n.get('badge') or '').strip(),
        (n.get('title') or '').strip(),
        (n.get('lead') or '').strip(),
        *(n.get('points') or []),
        (n.get('callout') or '').strip(),
    ]
    return any(parts)


def notices_for_template():
    """Список блоков для главной: только включённые и с непустым текстом."""
    data = load_dashboard_legal_notice()
    notices = data.get('notices') or []
    out = []
    for n in notices:
        if not isinstance(n, dict):
            continue
        nn = _normalize_item(n)
        if not nn.get('enabled'):
            continue
        if not _item_has_visible_content(nn):
            continue
        out.append(nn)
    return out


# Имя для обратной совместимости в routes (старый DEFAULT_NOTICE)
DEFAULT_NOTICE = dict(DEFAULT_NOTICE_ITEM)
