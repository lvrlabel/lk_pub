"""
История событий релиза (модерация и связанные действия).
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


EVENT_LABELS = {
    'submitted': 'Отправлен на модерацию',
    'admin_viewed': 'Открыт модератором',
    'approved': 'Одобрен',
    'rejected': 'Отклонён',
    'revoked': 'Отозван администратором',
    'deletion_requested': 'Запрошено удаление',
    'deletion_confirmed': 'Удаление подтверждено',
    'deletion_cancelled': 'Удаление отменено',
}

EVENT_ICONS = {
    'submitted': 'send',
    'admin_viewed': 'visibility',
    'approved': 'check_circle',
    'rejected': 'cancel',
    'revoked': 'block',
    'deletion_requested': 'delete_outline',
    'deletion_confirmed': 'delete_forever',
    'deletion_cancelled': 'undo',
}


class ReleaseEvent(db.Model):
    """Запись в журнале событий релиза."""

    __tablename__ = 'release_events'
    __table_args__ = (
        db.Index('ix_release_events_release_created', 'release_id', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    event_type = db.Column(db.String(32), nullable=False, index=True)
    comment = db.Column(db.Text, nullable=True)
    extra = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    release = db.relationship('Release', backref=db.backref('events', lazy='dynamic', order_by='ReleaseEvent.created_at'))
    actor = db.relationship('User', foreign_keys=[actor_user_id])

    @property
    def created_at_local(self):
        return _to_local_msk(self.created_at)

    @property
    def created_display(self):
        dt = self.created_at_local
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''

    @property
    def label(self):
        return EVENT_LABELS.get(self.event_type, self.event_type)

    @property
    def actor_display_name(self):
        if self.actor:
            return self.actor.display_name
        return None

    @property
    def label_for_viewer(self):
        """Подпись события с учётом роли (админ видит автора действия)."""
        base = self.label
        if not self.actor_display_name:
            return base
        if self.event_type == 'admin_viewed':
            return f'{base}: {self.actor_display_name}'
        if self.event_type in ('approved', 'rejected', 'revoked', 'deletion_confirmed', 'deletion_cancelled'):
            return f'{base} ({self.actor_display_name})'
        return base

    @property
    def icon(self):
        return EVENT_ICONS.get(self.event_type, 'info')

    @property
    def tone(self):
        if self.event_type in ('approved', 'deletion_cancelled'):
            return 'success'
        if self.event_type in ('rejected', 'revoked', 'deletion_confirmed'):
            return 'danger'
        if self.event_type == 'admin_viewed':
            return 'info'
        return 'neutral'
