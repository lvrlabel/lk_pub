"""
Модель питчинга релиза
"""

from datetime import datetime
from app import db


class Pitch(db.Model):
    """Заявки на питчинг релиза"""

    __tablename__ = 'pitches'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=True, index=True)
    title = db.Column(db.String(256), nullable=False)
    artists = db.Column(db.String(512), nullable=False)
    genre = db.Column(db.String(100), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)
    # pending, in_review, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    user = db.relationship('User', backref='pitches')
    release = db.relationship('Release', backref='pitches')

    @property
    def status_display(self):
        statuses = {
            'pending': 'На рассмотрении',
            'in_review': 'В работе',
            'approved': 'Одобрено',
            'rejected': 'Отклонено',
        }
        return statuses.get(self.status, self.status)

    @property
    def status_class(self):
        classes = {
            'pending': 'status-pending',
            'in_review': 'status-review',
            'approved': 'status-approved',
            'rejected': 'status-rejected',
        }
        return classes.get(self.status, '')

    def __repr__(self):
        return f'<Pitch {self.id}: {self.title}>'
