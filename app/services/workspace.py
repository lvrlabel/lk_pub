"""Сервис личного рабочего пространства артиста."""

from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Optional

from flask import g

from app import db
from app.models.workspace import (
    BLOCK_TINTS,
    DEFAULT_WORKSPACE_BLOCKS,
    DEFAULT_WORKSPACE_THEME,
    THEME_GRADIENTS,
    WorkspaceCalendarEvent,
    WorkspaceIdea,
    WorkspaceLayout,
    WorkspaceNote,
    WorkspaceReleasePlan,
    WorkspaceTask,
)
from app.models.release import Release


def _sid() -> Optional[str]:
    row = getattr(g, 'sml_session', None)
    if row is not None and getattr(row, 'session_id', None):
        return str(row.session_id)
    try:
        from flask import session
        return session.get('sml_session_id')
    except Exception:
        return None


def touch_layout_session(user_id: int) -> None:
    layout = WorkspaceLayout.for_user(user_id)
    layout.last_session_id = _sid()
    layout.updated_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_layout_blocks(user_id: int) -> list[dict]:
    layout = WorkspaceLayout.for_user(user_id)
    blocks = layout.get_blocks()
    known = {b['id'] for b in DEFAULT_WORKSPACE_BLOCKS}
    existing_ids = {b.get('id') for b in blocks}
    for default in DEFAULT_WORKSPACE_BLOCKS:
        if default['id'] not in existing_ids:
            blocks.append(dict(default))
    blocks = [b for b in blocks if b.get('id') in known]
    for b in blocks:
        if b.get('tint') not in BLOCK_TINTS:
            b['tint'] = 'default'
        tint = BLOCK_TINTS.get(b.get('tint') or 'default', BLOCK_TINTS['default'])
        b['tint_color'] = tint.get('color')
    blocks.sort(key=lambda b: int(b.get('order', 99)))
    return blocks


def get_workspace_theme(user_id: int) -> dict:
    layout = WorkspaceLayout.for_user(user_id)
    theme = layout.get_theme()
    grad_key = theme.get('gradient') or 'none'
    if grad_key not in THEME_GRADIENTS:
        grad_key = 'none'
        theme['gradient'] = grad_key
    theme['gradient_css'] = THEME_GRADIENTS[grad_key]['css']
    theme['cover_url'] = layout.cover_url
    accent = (theme.get('accent') or DEFAULT_WORKSPACE_THEME['accent']).strip()
    if not accent.startswith('#') or len(accent) not in (4, 7):
        accent = DEFAULT_WORKSPACE_THEME['accent']
    theme['accent'] = accent
    return theme


def save_layout_settings(
    user_id: int,
    *,
    visible_ids: set[str],
    order_ids: list[str],
    tints: dict[str, str],
    accent: str,
    gradient: str,
    cover_filename: Optional[str] = None,
    clear_cover: bool = False,
) -> None:
    layout = WorkspaceLayout.for_user(user_id)
    existing = {b.get('id'): b for b in layout.get_blocks()}
    by_id = {b['id']: dict(b) for b in DEFAULT_WORKSPACE_BLOCKS}
    result = []
    for i, bid in enumerate(order_ids):
        if bid not in by_id:
            continue
        item = dict(by_id[bid])
        prev = existing.get(bid) or {}
        item['visible'] = bid in visible_ids
        item['order'] = i
        tint = tints.get(bid) or prev.get('tint') or 'default'
        item['tint'] = tint if tint in BLOCK_TINTS else 'default'
        result.append(item)
    for bid, item in by_id.items():
        if bid not in {r['id'] for r in result}:
            copy = dict(item)
            prev = existing.get(bid) or {}
            copy['visible'] = bid in visible_ids
            copy['order'] = len(result)
            tint = tints.get(bid) or prev.get('tint') or 'default'
            copy['tint'] = tint if tint in BLOCK_TINTS else 'default'
            result.append(copy)
    layout.set_blocks(result)

    theme = layout.get_theme()
    accent = (accent or '').strip()
    if accent.startswith('#') and len(accent) in (4, 7):
        theme['accent'] = accent
    if gradient in THEME_GRADIENTS:
        theme['gradient'] = gradient
    if clear_cover:
        theme['cover'] = None
    elif cover_filename:
        theme['cover'] = cover_filename
    layout.set_theme(theme)
    layout.last_session_id = _sid()
    db.session.commit()


def overview_payload(user) -> dict:
    """Данные для блоков пространства и виджетов на главной."""
    uid = user.id
    touch_layout_session(uid)

    open_tasks = (
        WorkspaceTask.query.filter_by(user_id=uid, is_done=False)
        .order_by(WorkspaceTask.due_at.asc(), WorkspaceTask.sort_order.asc(), WorkspaceTask.id.desc())
        .limit(8)
        .all()
    )
    ideas = (
        WorkspaceIdea.query.filter(
            WorkspaceIdea.user_id == uid,
            WorkspaceIdea.status.in_(('inbox', 'active')),
        )
        .order_by(WorkspaceIdea.updated_at.desc())
        .limit(6)
        .all()
    )
    plans = (
        WorkspaceReleasePlan.query.filter(
            WorkspaceReleasePlan.user_id == uid,
            WorkspaceReleasePlan.status != 'done',
        )
        .order_by(WorkspaceReleasePlan.target_date.asc(), WorkspaceReleasePlan.id.desc())
        .limit(6)
        .all()
    )
    notes = (
        WorkspaceNote.query.filter_by(user_id=uid)
        .order_by(WorkspaceNote.is_pinned.desc(), WorkspaceNote.updated_at.desc())
        .limit(5)
        .all()
    )

    today = date.today()
    week_end = today + timedelta(days=14)
    events = (
        WorkspaceCalendarEvent.query.filter(
            WorkspaceCalendarEvent.user_id == uid,
            WorkspaceCalendarEvent.starts_at >= datetime.combine(today, datetime.min.time()),
            WorkspaceCalendarEvent.starts_at < datetime.combine(week_end, datetime.min.time()),
        )
        .order_by(WorkspaceCalendarEvent.starts_at.asc())
        .limit(10)
        .all()
    )

    next_release = None
    if getattr(user, 'is_admin', False):
        next_release = (
            Release.query.filter(Release.status.in_(('draft', 'moderation', 'approved')))
            .order_by(Release.release_date.asc(), Release.id.desc())
            .first()
        )
    else:
        next_release = (
            Release.query.filter_by(user_id=uid)
            .filter(Release.status.in_(('draft', 'moderation', 'approved')))
            .order_by(Release.release_date.asc(), Release.id.desc())
            .first()
        )
        if next_release is None:
            next_release = (
                Release.query.filter_by(user_id=uid)
                .order_by(Release.id.desc())
                .first()
            )

    blocks = get_layout_blocks(uid)
    theme = get_workspace_theme(uid)
    return {
        'blocks': blocks,
        'visible_blocks': [b for b in blocks if b.get('visible')],
        'theme': theme,
        'open_tasks': open_tasks,
        'ideas': ideas,
        'plans': plans,
        'notes': notes,
        'events': events,
        'next_release': next_release,
        'counts': {
            'tasks': WorkspaceTask.query.filter_by(user_id=uid, is_done=False).count(),
            'ideas': WorkspaceIdea.query.filter(
                WorkspaceIdea.user_id == uid,
                WorkspaceIdea.status.in_(('inbox', 'active')),
            ).count(),
            'plans': WorkspaceReleasePlan.query.filter(
                WorkspaceReleasePlan.user_id == uid,
                WorkspaceReleasePlan.status != 'done',
            ).count(),
            'notes': WorkspaceNote.query.filter_by(user_id=uid).count(),
        },
    }


def parse_date(value: str) -> Optional[date]:
    value = (value or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def parse_datetime_date(value: str, all_day: bool = True) -> Optional[datetime]:
    d = parse_date(value)
    if not d:
        return None
    return datetime.combine(d, datetime.min.time())
