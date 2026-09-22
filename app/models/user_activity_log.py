"""
Журнал действий пользователей (артисты и лейблы) для просмотра администратором.
"""

from datetime import datetime, timedelta, timezone

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


class UserActivityLog(db.Model):
    """Запись о действии пользователя в кабинете."""

    __tablename__ = 'user_activity_logs'
    __table_args__ = (
        db.Index('ix_user_activity_logs_user_created', 'user_id', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    method = db.Column(db.String(8), nullable=False)
    endpoint = db.Column(db.String(160), nullable=True, index=True)
    path = db.Column(db.String(512), nullable=False, default='')
    status_code = db.Column(db.Integer, nullable=True)
    summary = db.Column(db.String(512), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    # SML: привязка действия к sessionId устройства (nullable для старых записей)
    session_id = db.Column(db.String(64), nullable=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', backref=db.backref('activity_logs', lazy='dynamic'))

    @property
    def created_at_local(self):
        return _to_local_msk(self.created_at)

    @property
    def created_display(self):
        dt = self.created_at_local
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''
