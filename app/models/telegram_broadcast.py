"""Рассылки в Telegram-бот (текст без картинок)."""

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


class TelegramBroadcast(db.Model):
    """Отправленная новость в Telegram-бот."""

    __tablename__ = 'telegram_broadcasts'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(16), nullable=False, default='update')  # outage | update
    title = db.Column(db.String(256), nullable=False)
    text = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    recipients_ok = db.Column(db.Integer, nullable=False, default=0)
    recipients_failed = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    author = db.relationship('User', foreign_keys=[author_id])

    @property
    def kind_display(self):
        return 'О ЧП' if self.kind == 'outage' else 'Обновление'

    @property
    def kind_icon(self):
        return '🚨' if self.kind == 'outage' else '📢'

    @property
    def created_at_local(self):
        return _to_local_msk(self.created_at)

    @property
    def date_display(self):
        dt = self.created_at_local
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''

    @property
    def short_text(self):
        text = (self.text or '').strip().replace('\n', ' ')
        if len(text) > 120:
            return text[:117] + '…'
        return text

    def __repr__(self):
        return f'<TelegramBroadcast {self.title}>'


class TelegramSubscriber(db.Model):
    """Подписчик бота (/start)."""

    __tablename__ = 'telegram_subscribers'

    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.BigInteger, unique=True, nullable=False, index=True)
    username = db.Column(db.String(128), nullable=True)
    first_name = db.Column(db.String(128), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    unsubscribed_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f'<TelegramSubscriber {self.chat_id}>'
