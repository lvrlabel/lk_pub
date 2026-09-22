"""
SML — явное управление сессиями устройств (sessionId).
Работает поверх Flask-Login: данные кабинета в БД, сессия — только доступ.
"""

from datetime import datetime, timedelta, timezone
import secrets

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

from app import db


def _to_local_msk(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        if ZoneInfo is not None:
            return dt.astimezone(ZoneInfo('Europe/Moscow'))
    except Exception:
        pass
    return dt.astimezone(timezone(timedelta(hours=3)))


class UserSession(db.Model):
    """Активная (или отозванная) сессия устройства пользователя."""

    __tablename__ = 'user_sessions'
    __table_args__ = (
        db.Index('ix_user_sessions_user_active', 'user_id', 'revoked_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    # Публичный идентификатор сессии (ротируется)
    session_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    device_label = db.Column(db.String(120), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)

    is_trusted = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    rotated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoke_reason = db.Column(db.String(64), nullable=True)

    # Цепочка ротаций: предыдущий session_id (для аудита)
    previous_session_id = db.Column(db.String(64), nullable=True)

    user = db.relationship('User', backref=db.backref('sessions', lazy='dynamic'))

    @staticmethod
    def generate_session_id():
        return secrets.token_urlsafe(32)

    @property
    def is_active(self):
        if self.revoked_at is not None:
            return False
        return datetime.utcnow() < self.expires_at

    @property
    def created_at_local(self):
        return _to_local_msk(self.created_at)

    @property
    def last_seen_at_local(self):
        return _to_local_msk(self.last_seen_at)

    @property
    def created_display(self):
        dt = self.created_at_local
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''

    @property
    def last_seen_display(self):
        dt = self.last_seen_at_local
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''

    def revoke(self, reason='manual'):
        if self.revoked_at is None:
            self.revoked_at = datetime.utcnow()
            self.revoke_reason = (reason or 'manual')[:64]

    def __repr__(self):
        return f'<UserSession {self.session_id[:8]}… user={self.user_id}>'


class SessionEvent(db.Model):
    """Аудит жизненного цикла сессии (вход, ротация, отзыв и т.д.)."""

    __tablename__ = 'session_events'
    __table_args__ = (
        db.Index('ix_session_events_user_created', 'user_id', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    session_pk = db.Column(db.Integer, db.ForeignKey('user_sessions.id'), nullable=True, index=True)
    session_id = db.Column(db.String(64), nullable=True, index=True)
    event_type = db.Column(db.String(32), nullable=False, index=True)
    detail = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', backref=db.backref('session_events', lazy='dynamic'))
    session = db.relationship('UserSession', backref=db.backref('events', lazy='dynamic'))

    @property
    def created_at_local(self):
        return _to_local_msk(self.created_at)

    @property
    def created_display(self):
        dt = self.created_at_local
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''
