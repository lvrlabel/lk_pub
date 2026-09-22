"""
Модель заявок на загрузку видео (доп. услуга)
"""

from datetime import datetime
from app import db


class VideoRequest(db.Model):
    """Заявка на доп. услугу: загрузка видеоклипа или доставка текста"""

    __tablename__ = 'video_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    track_id = db.Column(db.Integer, db.ForeignKey('tracks.id'), nullable=False, index=True)
    service_type = db.Column(db.String(20), nullable=False, default='video', index=True)  # video | lyrics
    video_url = db.Column(db.String(1024), nullable=True)
    lyrics_text = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Integer, nullable=False, default=1000)  # рублей
    status = db.Column(db.String(30), nullable=False, default='pending_payment', index=True)
    # pending_payment, paid, processed, closed
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    admin_comment = db.Column(db.Text, nullable=True)

    user = db.relationship('User', backref='video_requests')
    track = db.relationship('Track', backref='video_requests')

    @property
    def status_display(self):
        statuses = {
            'pending_payment': 'Ожидает оплаты',
            'paid': 'Оплачено',
            'processed': 'Обработано',
            'closed': 'Закрыто',
        }
        return statuses.get(self.status, self.status)

    @property
    def status_class(self):
        classes = {
            'pending_payment': 'status-pending',
            'paid': 'status-approved',
            'processed': 'status-approved',
            'closed': 'status-rejected',
        }
        return classes.get(self.status, '')

    @property
    def service_type_display(self):
        return 'Загрузка видео' if self.service_type == 'video' else 'Доставка текста'

    def __repr__(self):
        return f'<VideoRequest {self.id} {self.service_type} track_id={self.track_id}>'
