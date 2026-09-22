"""
Социальные аккаунты пользователей (OAuth привязки)
"""

from datetime import datetime
from app import db


class SocialAccount(db.Model):
    """Привязанный соц-аккаунт пользователя."""

    __tablename__ = 'social_accounts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    provider = db.Column(db.String(20), nullable=False, index=True)  # yandex
    provider_user_id = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('provider', 'provider_user_id', name='uq_social_provider_user'),
        db.UniqueConstraint('user_id', 'provider', name='uq_social_user_provider'),
    )

    @property
    def provider_display(self):
        names = {
            'yandex': 'Яндекс',
        }
        return names.get(self.provider, self.provider)

    def __repr__(self):
        return f'<SocialAccount {self.provider}:{self.provider_user_id}>'
