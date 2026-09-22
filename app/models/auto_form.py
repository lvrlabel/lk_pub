"""
Модель автоматических форм
"""

from datetime import datetime
from app import db


class AutoFormRequest(db.Model):
    """Запросы из автоматической формы"""
    
    __tablename__ = 'auto_form_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    request_type = db.Column(db.String(50), nullable=False, index=True)
    # Типы: transfer_release, youtube_note, vk_restore, other
    
    # Данные для transfer_release
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=True)
    platform = db.Column(db.String(50), nullable=True)  # vk, spotify, yandex, other
    wrong_card_url = db.Column(db.String(512), nullable=True)
    correct_card_url = db.Column(db.String(512), nullable=True)
    
    # Данные для youtube_note
    artist_name = db.Column(db.String(256), nullable=True)
    channel_url = db.Column(db.String(512), nullable=True)
    topic_urls = db.Column(db.Text, nullable=True)  # Многострочный текст
    
    # Данные для vk_restore
    previous_distributor = db.Column(db.String(256), nullable=True)
    upc_codes = db.Column(db.Text, nullable=True)  # Многострочный текст
    
    # Общие поля
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    # pending, processed, closed
    admin_comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    user = db.relationship('User', backref='auto_form_requests')
    release = db.relationship('Release', backref='auto_form_requests')
    messages = db.relationship('AutoFormMessage', backref='request', lazy='dynamic',
                               cascade='all, delete-orphan', order_by='AutoFormMessage.created_at')
    
    @property
    def display_id(self):
        """Номер запроса для отображения: AF-00001"""
        return f'AF-{self.id:05d}'
    
    @property
    def request_type_display(self):
        """Отображаемый тип запроса"""
        types = {
            'transfer_release': 'Перенести релиз на другую карточку',
            'youtube_note': 'Получить "Нотку" в YouTube',
            'vk_restore': 'Восстановить прослушивания/плейлист в VK',
            'cabinet_wish': 'Пожелание по личному кабинету',
            'other': 'Другое'
        }
        return types.get(self.request_type, self.request_type)
    
    @property
    def status_display(self):
        """Отображаемый статус"""
        statuses = {
            'pending': 'На рассмотрении',
            'processed': 'Обработано',
            'closed': 'Закрыто'
        }
        return statuses.get(self.status, self.status)

    @property
    def status_class(self):
        classes = {
            'pending': 'status-pending',
            'processed': 'status-approved',
            'closed': 'status-rejected',
        }
        return classes.get(self.status, '')

    def __repr__(self):
        return f'<AutoFormRequest {self.id}: {self.request_type}>'


class AutoFormMessage(db.Model):
    """Сообщения в запросе автоформы (ответы админа — как чат с пользователем)."""
    
    __tablename__ = 'auto_form_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('auto_form_requests.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    author = db.relationship('User', foreign_keys=[user_id])
