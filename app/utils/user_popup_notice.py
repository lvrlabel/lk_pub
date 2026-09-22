"""
Всплывающие уведомления для пользователей: хранение в instance/user_popup_notice.json.
Показ на главной и в разделе релизов; аудитория и текст задаёт администратор.
"""

import json
import os
import uuid

from flask import current_app

DEFAULT_POPUP_ITEM = {
    'id': '',
    'enabled': False,
    'tone': 'red',
    'badge': 'Важно',
    'title': 'Уведомление',
    'lead': '',
    'points': [],
    'callout': '',
    'user_ids': [],
    'pages': ['dashboard', 'releases'],
}

_VALID_TONES = frozenset({'red', 'orange'})
_VALID_PAGES = frozenset({'dashboard', 'releases'})

DASHBOARD_ENDPOINT = 'dashboard.index'
RELEASES_ENDPOINT_PREFIX = 'releases.'


def _coerce_enabled(val):
    if val is True:
        return True
    if val is False or val is None:
        return False
    if isinstance(val, (int, float)):
        return int(val) != 0
    s = str(val).strip().lower()
    return s in ('1', 'true', 'yes', 'on')


def _popup_path():
    return os.path.join(current_app.instance_path, 'user_popup_notice.json')


def _normalize_points(val):
    if not isinstance(val, list):
        return []
    return [str(p).strip() for p in val if str(p).strip()]


def _normalize_user_ids(val):
    if not isinstance(val, list):
        return []
    out = []
    for item in val:
        try:
            uid = int(item)
        except (TypeError, ValueError):
            continue
        if uid > 0 and uid not in out:
            out.append(uid)
    return out


def _normalize_pages(val):
    if not isinstance(val, list):
        return ['dashboard', 'releases']
    out = []
    for item in val:
        page = str(item).strip().lower()
        if page in _VALID_PAGES and page not in out:
            out.append(page)
    return out or ['dashboard', 'releases']


def _normalize_item(raw):
    if not isinstance(raw, dict):
        return dict(DEFAULT_POPUP_ITEM)
    out = dict(DEFAULT_POPUP_ITEM)
    out.update(raw)
    popup_id = str(out.get('id') or '').strip()
    out['id'] = popup_id or uuid.uuid4().hex[:12]
    tone = str(out.get('tone') or 'red').strip().lower()
    out['tone'] = tone if tone in _VALID_TONES else 'red'
    out['enabled'] = _coerce_enabled(out.get('enabled'))
    out['badge'] = str(out.get('badge') or DEFAULT_POPUP_ITEM['badge']).strip() or DEFAULT_POPUP_ITEM['badge']
    out['title'] = str(out.get('title') or DEFAULT_POPUP_ITEM['title']).strip() or DEFAULT_POPUP_ITEM['title']
    out['lead'] = str(out.get('lead') or '').strip()
    out['callout'] = str(out.get('callout') or '').strip()
    out['points'] = _normalize_points(out.get('points'))
    out['user_ids'] = _normalize_user_ids(out.get('user_ids'))
    out['pages'] = _normalize_pages(out.get('pages'))
    out.pop('audience', None)
    return out


def load_user_popup_notices():
    """Словарь {'popups': […]} для формы редактирования."""
    path = _popup_path()
    if not os.path.isfile(path):
        return {'popups': [dict(DEFAULT_POPUP_ITEM)]}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        return {'popups': [dict(DEFAULT_POPUP_ITEM)]}

    if not isinstance(data, dict):
        return {'popups': [dict(DEFAULT_POPUP_ITEM)]}

    popups_raw = data.get('popups')
    if isinstance(popups_raw, list):
        if popups_raw:
            return {'popups': [_normalize_item(x) for x in popups_raw]}
        return {'popups': [dict(DEFAULT_POPUP_ITEM)]}

    return {'popups': [dict(DEFAULT_POPUP_ITEM)]}


def save_user_popup_notices(data):
    path = _popup_path()
    inst_dir = current_app.instance_path
    if inst_dir:
        os.makedirs(inst_dir, exist_ok=True)
    popups_raw = data.get('popups') if isinstance(data, dict) else []
    popups = [_normalize_item(x) for x in (popups_raw or [])]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'popups': popups}, f, ensure_ascii=False, indent=2)


def _item_has_visible_content(item):
    parts = [
        (item.get('badge') or '').strip(),
        (item.get('title') or '').strip(),
        (item.get('lead') or '').strip(),
        *(item.get('points') or []),
        (item.get('callout') or '').strip(),
    ]
    return any(parts)


def _user_matches_targets(user, user_ids):
    if not user_ids:
        return False
    user_id = getattr(user, 'id', None)
    return user_id is not None and user_id in user_ids


def page_scope_for_endpoint(endpoint):
    """Текущая «зона» страницы: dashboard | releases | None."""
    if not endpoint:
        return None
    if endpoint == DASHBOARD_ENDPOINT:
        return 'dashboard'
    if endpoint.startswith(RELEASES_ENDPOINT_PREFIX):
        return 'releases'
    return None


def popups_for_user(user, page_scope):
    """
    Активные всплывающие уведомления для пользователя на текущей странице.
    Клиент скрывает уже закрытые (localStorage по id).
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return []
    if page_scope not in _VALID_PAGES:
        return []

    data = load_user_popup_notices()
    popups = data.get('popups') or []
    out = []
    for raw in popups:
        if not isinstance(raw, dict):
            continue
        item = _normalize_item(raw)
        if not item.get('enabled'):
            continue
        if page_scope not in (item.get('pages') or []):
            continue
        if not _user_matches_targets(user, item.get('user_ids') or []):
            continue
        if not _item_has_visible_content(item):
            continue
        out.append(item)
    return out
