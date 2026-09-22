"""
Модель уведомлений
"""

from datetime import datetime
from app import db


class Notification(db.Model):
    """Уведомления пользователей"""

    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    # Тип: ticket_created, ticket_reply, ticket_closed, ticket_admin_initiated, release_submitted, ...
    kind = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(256), nullable=False)
    message = db.Column(db.Text, nullable=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=True, index=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=True, index=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Связи
    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic'))
    ticket = db.relationship('Ticket', backref=db.backref('notifications', lazy='dynamic'))
    release = db.relationship('Release', backref=db.backref('notifications', lazy='dynamic'))

    def __repr__(self):
        return f'<Notification {self.id} {self.kind}>'
