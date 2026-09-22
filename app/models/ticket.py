"""
Модели тикетов поддержки
"""

from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None
from app import db


def _to_local_msk(dt):
    """Преобразовать UTC datetime в локальное время (Europe/Moscow)."""
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


_MONTHS_GENITIVE = (
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
)


def _msk_today():
    now = datetime.now(timezone.utc)
    local = _to_local_msk(now)
    return local.date() if local else now.date()


def human_date_label_msk(dt):
    """Человекочитаемая дата для разделителя в чате: Сегодня, Вчера, 1 сентября."""
    local = _to_local_msk(dt)
    if not local:
        return ''
    day = local.date()
    today = _msk_today()
    if day == today:
        return 'Сегодня'
    if day == today - timedelta(days=1):
        return 'Вчера'
    label = f'{day.day} {_MONTHS_GENITIVE[day.month - 1]}'
    if day.year != today.year:
        label = f'{label} {day.year}'
    return label


class Ticket(db.Model):
    """Тикеты поддержки"""

    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    subject = db.Column(db.String(256), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(
        db.String(32),
        nullable=False,
        default='waiting_for_admin',
    )
    initiator = db.Column(db.String(10), nullable=False, default='user')
    priority = db.Column(db.String(20), nullable=False, default='normal')
    category = db.Column(db.String(32), nullable=False, default='general')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Персональный чат: когда участник последний раз открывал переписку (для счётчика непрочитанных)
    manager_chat_read_by_user_at = db.Column(db.DateTime, nullable=True)
    manager_chat_read_by_admin_at = db.Column(db.DateTime, nullable=True)

    messages = db.relationship(
        'TicketMessage',
        backref='ticket',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='TicketMessage.created_at',
    )

    @property
    def category_display(self):
        categories = {
            'general': 'Общие вопросы',
            'finance': 'Финансы',
            'releases': 'Релизы',
            'uploads': 'Загрузка файлов',
            'auth': 'Вход и авторизация',
            'other': 'Другое',
        }
        return categories.get(self.category, self.category)
    creator_admin = db.relationship(
        'User',
        foreign_keys=[created_by_admin_id],
        backref=db.backref('admin_initiated_tickets', lazy='dynamic'),
    )

    @property
    def display_id(self):
        """Отображаемый номер тикета (генерируется автоматически)."""
        if not self.id:
            return 'TKT-NEW'
        dt = self.created_at_local or self.created_at
        date_part = dt.strftime('%y%m%d') if dt else '000000'
        return f'TKT-{date_part}-{self.id:05d}'

    @property
    def status_display(self):
        """Отображаемый статус"""
        statuses = {
            'waiting_for_user': 'Есть ответ',
            'waiting_for_admin': 'На рассмотрении',
            'closed': 'Закрыт',
            'open': 'На рассмотрении',
        }
        return statuses.get(self.status, self.status)

    @property
    def status_class(self):
        """CSS класс для статуса"""
        if self.status == 'closed':
            return 'status-closed'
        if self.status == 'waiting_for_user':
            return 'status-waiting-user'
        if self.status == 'waiting_for_admin':
            return 'status-waiting-admin'
        return 'status-waiting-admin'

    @property
    def messages_count(self):
        """Количество сообщений"""
        return self.messages.count()

    @property
    def last_message(self):
        """Последнее сообщение"""
        return self.messages.order_by(TicketMessage.created_at.desc()).first()

    @property
    def is_open(self):
        """Тикет не закрыт"""
        return self.status != 'closed'

    @property
    def created_at_local(self):
        return _to_local_msk(self.created_at)

    @property
    def updated_at_local(self):
        return _to_local_msk(self.updated_at)

    @property
    def created_at_formatted(self):
        dt = self.created_at_local
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''

    @property
    def date_key(self):
        dt = self.created_at_local
        return dt.strftime('%Y-%m-%d') if dt else ''

    @property
    def date_label(self):
        return human_date_label_msk(self.created_at)

    @property
    def chat_time_formatted(self):
        dt = self.created_at_local
        return dt.strftime('%H:%M') if dt else ''

    @property
    def created_date_formatted(self):
        dt = self.created_at_local
        return dt.strftime('%Y-%m-%d') if dt else ''

    @property
    def creator_display_name(self):
        """Кто инициировал обращение."""
        if self.initiator == 'admin':
            if self.creator_admin:
                return self.creator_admin.display_name
            return 'Поддержка'
        if self.user:
            return self.user.display_name
        return '—'

    @property
    def closed_at_local(self):
        if self.status != 'closed':
            return None
        return _to_local_msk(self.updated_at)

    @property
    def closed_date_formatted(self):
        dt = self.closed_at_local
        return dt.strftime('%Y-%m-%d') if dt else ''

    def __repr__(self):
        return f'<Ticket {self.id}: {self.subject}>'


class TicketMessage(db.Model):
    """Сообщения в тикетах"""

    __tablename__ = 'ticket_messages'

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    author = db.relationship('User', foreign_keys=[user_id])
    attachments = db.relationship('Attachment', backref='message', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def is_from_admin(self):
        """Синоним поля is_admin (ответ администратора)."""
        return self.is_admin

    @is_from_admin.setter
    def is_from_admin(self, value):
        self.is_admin = bool(value)

    @property
    def time_formatted(self):
        """Форматированное время"""
        dt = _to_local_msk(self.created_at)
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''

    @property
    def date_key(self):
        dt = _to_local_msk(self.created_at)
        return dt.strftime('%Y-%m-%d') if dt else ''

    @property
    def date_label(self):
        return human_date_label_msk(self.created_at)

    @property
    def chat_time_formatted(self):
        dt = _to_local_msk(self.created_at)
        return dt.strftime('%H:%M') if dt else ''

    def __repr__(self):
        return f'<TicketMessage {self.id}>'


class Attachment(db.Model):
    """Вложения к сообщениям тикетов (файлы, фото, видео)"""

    __tablename__ = 'ticket_attachments'

    id = db.Column(db.Integer, primary_key=True)
    ticket_message_id = db.Column(db.Integer, db.ForeignKey('ticket_messages.id'), nullable=False, index=True)
    filename = db.Column(db.String(256), nullable=False)  # оригинальное имя
    stored_filename = db.Column(db.String(256), nullable=False)  # уникальное имя в файловой системе
    file_size = db.Column(db.Integer, nullable=False)  # размер в байтах
    mime_type = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def url(self):
        """URL для доступа к файлу"""
        return f'/uploads/ticket_attachments/{self.stored_filename}'

    @property
    def formatted_size(self):
        """Форматированный размер файла"""
        if self.file_size < 1024:
            return f'{self.file_size} B'
        elif self.file_size < 1024 * 1024:
            return f'{self.file_size / 1024:.1f} KB'
        elif self.file_size < 1024 * 1024 * 1024:
            return f'{self.file_size / (1024 * 1024):.1f} MB'
        else:
            return f'{self.file_size / (1024 * 1024 * 1024):.1f} GB'

    @property
    def is_audio(self):
        if self.mime_type and self.mime_type.startswith('audio/'):
            return True
        if not self.filename or '.' not in self.filename:
            return False
        ext = self.filename.rsplit('.', 1)[1].lower()
        return ext in {'mp3', 'wav', 'ogg', 'flac', 'webm', 'm4a', 'aac', 'weba', 'opus'}

    @property
    def is_image(self):
        if self.mime_type and self.mime_type.startswith('image/'):
            return True
        if not self.filename or '.' not in self.filename:
            return False
        ext = self.filename.rsplit('.', 1)[1].lower()
        return ext in {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'}

    def __repr__(self):
        return f'<Attachment {self.id}: {self.filename}>'
