"""
Обновления сервиса — журнал изменений и правок в кабинете.
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


class ServiceUpdate(db.Model):
    """Запись об обновлении или правке в кабинете."""

    __tablename__ = 'service_updates'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), unique=True, nullable=True, index=True)
    title = db.Column(db.String(256), nullable=False)
    content = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(16), nullable=False, default='normal')  # normal | urgent
    source = db.Column(db.String(16), nullable=False, default='manual')  # auto | manual
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author = db.relationship('User', foreign_keys=[author_id])
    reads = db.relationship(
        'ServiceUpdateRead',
        backref='update',
        lazy='dynamic',
        cascade='all, delete-orphan',
        foreign_keys='ServiceUpdateRead.update_id',
    )

    @property
    def is_urgent(self):
        return self.priority == 'urgent'

    @property
    def source_display(self):
        return 'Автоматически' if self.source == 'auto' else 'Администрация'

    @property
    def created_at_local(self):
        return _to_local_msk(self.created_at)

    @property
    def date_display(self):
        dt = self.created_at_local
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''

    @property
    def short_content(self):
        text = (self.content or '').strip().replace('\n', ' ')
        if len(text) > 140:
            return text[:137] + '…'
        return text

    def __repr__(self):
        return f'<ServiceUpdate {self.title}>'


class ServiceUpdateRead(db.Model):
    """Отметка, что пользователь прочитал обновление."""

    __tablename__ = 'service_update_reads'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'update_id', name='uq_service_update_reads_user_update'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    update_id = db.Column(db.Integer, db.ForeignKey('service_updates.id'), nullable=False, index=True)
    read_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('service_update_reads', lazy='dynamic'))
