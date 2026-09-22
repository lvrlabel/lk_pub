"""
SML (Session Management Level): выдача, проверка, ротация и отзыв sessionId.

Слой поверх Flask-Login: не заменяет cookie-аутентификацию, а даёт явный
контроль устройств, ротацию раз в N часов и привязку аудита к сессии.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from flask import current_app, g, request, session
from flask_login import logout_user

from app import db
from app.models.user_session import SessionEvent, UserSession

FLASK_SESSION_KEY = 'sml_session_id'


def _client_ip() -> str:
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[0].strip()[:45]
    return (request.remote_addr or '')[:45]


def _user_agent() -> str:
    return (request.headers.get('User-Agent') or '')[:512]


def _parse_device_label(ua: str) -> str:
    ua_l = (ua or '').lower()
    if not ua_l:
        return 'Неизвестное устройство'
    browser = 'Браузер'
    if 'edg/' in ua_l or 'edge/' in ua_l:
        browser = 'Edge'
    elif 'chrome/' in ua_l and 'chromium' not in ua_l:
        browser = 'Chrome'
    elif 'firefox/' in ua_l:
        browser = 'Firefox'
    elif 'safari/' in ua_l and 'chrome/' not in ua_l:
        browser = 'Safari'
    elif 'opera' in ua_l or 'opr/' in ua_l:
        browser = 'Opera'

    os_name = 'ПК'
    if 'iphone' in ua_l or 'ipad' in ua_l:
        os_name = 'iOS'
    elif 'android' in ua_l:
        os_name = 'Android'
    elif 'mac os' in ua_l or 'macintosh' in ua_l:
        os_name = 'macOS'
    elif 'windows' in ua_l:
        os_name = 'Windows'
    elif 'linux' in ua_l:
        os_name = 'Linux'

    return f'{browser} · {os_name}'


def _rotation_hours() -> int:
    return int(current_app.config.get('SML_SESSION_ROTATION_HOURS', 8) or 8)


def _max_age_days() -> int:
    return int(current_app.config.get('SML_SESSION_MAX_AGE_DAYS', 30) or 30)


def sml_enabled() -> bool:
    return bool(current_app.config.get('SML_ENABLED', True))


def get_bound_session_id() -> Optional[str]:
    sid = session.get(FLASK_SESSION_KEY)
    if sid:
        return str(sid)
    return None


def bind_session_id(session_id: str) -> None:
    session[FLASK_SESSION_KEY] = session_id
    session.modified = True


def clear_bound_session_id() -> None:
    session.pop(FLASK_SESSION_KEY, None)


def record_session_event(
    user_id: int,
    event_type: str,
    *,
    session_row: Optional[UserSession] = None,
    session_id: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    try:
        ev = SessionEvent(
            user_id=user_id,
            session_pk=session_row.id if session_row else None,
            session_id=(session_id or (session_row.session_id if session_row else None)),
            event_type=(event_type or '')[:32],
            detail=(detail or '')[:255] if detail else None,
            ip_address=_client_ip(),
        )
        db.session.add(ev)
        db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            current_app.logger.warning('SML: failed to record session event %s', event_type)
        except Exception:
            pass


def create_user_session(user, *, reason: str = 'login') -> UserSession:
    """Выдать sessionId после входа. То же устройство (IP+label) — переиспользуем."""
    now = datetime.utcnow()
    ua = _user_agent()
    label = _parse_device_label(ua)
    ip = _client_ip() or None

    existing = find_reusable_device_session(user.id, ip, label)
    if existing is not None:
        existing.last_seen_at = now
        existing.user_agent = ua or existing.user_agent
        existing.ip_address = ip or existing.ip_address
        existing.device_label = label or existing.device_label
        existing.expires_at = now + timedelta(days=_max_age_days())
        db.session.commit()
        bind_session_id(existing.session_id)
        g.sml_session = existing
        record_session_event(
            user.id,
            'reuse_device' if reason == 'login' else reason,
            session_row=existing,
            detail=existing.device_label,
        )
        return existing

    row = UserSession(
        session_id=UserSession.generate_session_id(),
        user_id=user.id,
        device_label=label,
        user_agent=ua or None,
        ip_address=ip,
        is_trusted=False,
        created_at=now,
        last_seen_at=now,
        rotated_at=now,
        expires_at=now + timedelta(days=_max_age_days()),
    )
    db.session.add(row)
    db.session.commit()
    bind_session_id(row.session_id)
    g.sml_session = row
    record_session_event(user.id, reason, session_row=row, detail=row.device_label)
    return row


def find_active_session(session_id: str, user_id: int) -> Optional[UserSession]:
    if not session_id:
        return None
    row = UserSession.query.filter_by(session_id=session_id, user_id=user_id).first()
    if not row or not row.is_active:
        return None
    return row


def device_fingerprint(ip_address: Optional[str], device_label: Optional[str]) -> tuple[str, str]:
    """Ключ «одно устройство»: IP + название (например macOS)."""
    return ((ip_address or '').strip(), (device_label or '').strip().lower())


def list_active_sessions(user_id: int) -> list[UserSession]:
    now = datetime.utcnow()
    return (
        UserSession.query.filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.last_seen_at.desc())
        .all()
    )


def list_active_sessions_for_ui(
    user_id: int,
    current_session_id: Optional[str] = None,
) -> list[UserSession]:
    """
    Активные сессии для профиля: не больше одной строки
    на пару (IP + название устройства). Предпочитаем текущую сессию.
    """
    rows = list_active_sessions(user_id)
    best: dict[tuple[str, str], UserSession] = {}
    for row in rows:
        key = device_fingerprint(row.ip_address, row.device_label)
        prev = best.get(key)
        if prev is None:
            best[key] = row
        elif current_session_id and row.session_id == current_session_id:
            best[key] = row
        # иначе оставляем prev — он новее (сортировка last_seen desc)
    return sorted(
        best.values(),
        key=lambda r: r.last_seen_at or r.created_at or datetime.min,
        reverse=True,
    )


def revoke_sessions_same_device(
    user_id: int,
    session_pk: int,
    *,
    reason: str = 'device_revoke',
) -> tuple[bool, Optional[UserSession]]:
    """
    Отозвать выбранную сессию и все её дубликаты (тот же IP + label).
    Возвращает (ok, отозванная_строка_для_проверки_текущей).
    """
    row = UserSession.query.filter_by(id=session_pk, user_id=user_id).first()
    if not row or row.revoked_at is not None:
        return False, None
    key = device_fingerprint(row.ip_address, row.device_label)
    now = datetime.utcnow()
    twins = UserSession.query.filter(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
    ).all()
    for twin in twins:
        if device_fingerprint(twin.ip_address, twin.device_label) == key:
            twin.revoke(reason=reason)
            record_session_event(user_id, 'revoke', session_row=twin, detail=reason)
    db.session.commit()
    return True, row


def find_reusable_device_session(
    user_id: int,
    ip_address: Optional[str],
    device_label: Optional[str],
) -> Optional[UserSession]:
    key = device_fingerprint(ip_address, device_label)
    if not key[0] and not key[1]:
        return None
    for row in list_active_sessions(user_id):
        if device_fingerprint(row.ip_address, row.device_label) == key:
            return row
    return None


def rotate_session_id(row: UserSession) -> UserSession:
    """Ротация sessionId (тот же device-row, новый токен)."""
    old = row.session_id
    row.previous_session_id = old
    row.session_id = UserSession.generate_session_id()
    row.rotated_at = datetime.utcnow()
    row.last_seen_at = row.rotated_at
    row.ip_address = _client_ip() or row.ip_address
    db.session.commit()
    bind_session_id(row.session_id)
    record_session_event(
        row.user_id,
        'rotate',
        session_row=row,
        detail=f'was {old[:12]}…',
    )
    return row


def touch_session(row: UserSession) -> None:
    row.last_seen_at = datetime.utcnow()
    row.ip_address = _client_ip() or row.ip_address
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def needs_rotation(row: UserSession) -> bool:
    hours = _rotation_hours()
    if hours <= 0:
        return False
    base = row.rotated_at or row.created_at
    if not base:
        return True
    return (datetime.utcnow() - base) >= timedelta(hours=hours)


def revoke_session_row(row: UserSession, *, reason: str = 'manual') -> None:
    row.revoke(reason=reason)
    db.session.commit()
    record_session_event(row.user_id, 'revoke', session_row=row, detail=reason)


def revoke_session_for_user(user_id: int, session_pk: int, *, reason: str = 'manual') -> bool:
    row = UserSession.query.filter_by(id=session_pk, user_id=user_id).first()
    if not row or row.revoked_at is not None:
        return False
    revoke_session_row(row, reason=reason)
    return True


def revoke_other_sessions(user_id: int, keep_session_id: Optional[str], *, reason: str = 'revoke_others') -> int:
    rows = list_active_sessions(user_id)
    count = 0
    for row in rows:
        if keep_session_id and row.session_id == keep_session_id:
            continue
        row.revoke(reason=reason)
        count += 1
        record_session_event(user_id, 'revoke', session_row=row, detail=reason)
    if count:
        db.session.commit()
    return count


def revoke_current_bound_session(*, reason: str = 'logout') -> None:
    sid = get_bound_session_id()
    clear_bound_session_id()
    if not sid:
        return
    row = UserSession.query.filter_by(session_id=sid).first()
    if row and row.revoked_at is None:
        revoke_session_row(row, reason=reason)


def set_trusted(user_id: int, session_pk: int, trusted: bool) -> bool:
    row = UserSession.query.filter_by(id=session_pk, user_id=user_id).first()
    if not row or not row.is_active:
        return False
    row.is_trusted = bool(trusted)
    db.session.commit()
    record_session_event(
        user_id,
        'trust' if trusted else 'untrust',
        session_row=row,
    )
    return True


def issue_session_after_login(user) -> Optional[UserSession]:
    """Вызвать сразу после login_user(...)."""
    if not sml_enabled():
        return None
    try:
        return create_user_session(user, reason='login')
    except Exception as e:
        try:
            current_app.logger.warning('SML: issue_session_after_login failed: %s', e)
        except Exception:
            pass
        return None


def current_sml_session() -> Optional[UserSession]:
    return getattr(g, 'sml_session', None)


def ensure_request_session(user) -> Optional[UserSession]:
    """
    before_request: проверить / выдать / ротировать sessionId.
    Возвращает активную сессию или None (если нужно разлогинить).
    """
    if not sml_enabled() or user is None:
        return None

    sid = get_bound_session_id()

    if sid:
        row = UserSession.query.filter_by(session_id=sid).first()
        if row is None or row.user_id != user.id or not row.is_active:
            # Явный sessionId есть, но сессия отозвана / чужая / истекла → выход
            clear_bound_session_id()
            return None
    else:
        # Миграция: Flask-Login есть, SML ещё нет — тихо выдаём сессию
        try:
            return create_user_session(user, reason='bind_existing')
        except Exception:
            return None

    if needs_rotation(row):
        try:
            row = rotate_session_id(row)
        except Exception:
            touch_session(row)
    else:
        # Не коммитим last_seen на каждый запрос — раз в ~2 минуты
        last = row.last_seen_at
        if not last or (datetime.utcnow() - last).total_seconds() >= 120:
            touch_session(row)

    g.sml_session = row
    return row


def register_sml_middleware(app):
    """Подключить проверку SML к приложению."""

    @app.before_request
    def _sml_before_request():
        if not app.config.get('SML_ENABLED', True):
            return None
        path = request.path or ''
        if path.startswith('/static') or path.startswith('/uploads'):
            return None
        try:
            from flask import flash, redirect, url_for
            from flask_login import current_user

            if not current_user.is_authenticated:
                g.sml_session = None
                return None

            had_sid = bool(get_bound_session_id())
            row = ensure_request_session(current_user)
            if row is None:
                clear_bound_session_id()
                logout_user()
                if had_sid:
                    flash('Сессия завершена на этом устройстве. Войдите снова.', 'warning')
                    return redirect(url_for('auth.login'))
                return None
        except Exception as e:
            try:
                app.logger.warning('SML before_request: %s', e)
            except Exception:
                pass
        return None
