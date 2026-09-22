"""
Модели лейблов и артистов
"""

from datetime import datetime
from app import db


class Label(db.Model):
    """Лейблы"""
    
    __tablename__ = 'labels'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(256), nullable=False)
    copyright = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def releases_count(self):
        """Количество релизов с этим копирайтом"""
        from app.models.release import Release
        return Release.query.filter_by(copyright=self.copyright).count()
    
    def __repr__(self):
        return f'<Label {self.name}>'


class Artist(db.Model):
    """Артисты пользователя"""
    
    __tablename__ = 'artists'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='Исполнитель')
    # Роли: Исполнитель, Композитор, Автор
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    @staticmethod
    def get_roles():
        """Получить доступные роли"""
        return ['Исполнитель', 'Композитор', 'Автор']
    
    def __repr__(self):
        return f'<Artist {self.name}>'
