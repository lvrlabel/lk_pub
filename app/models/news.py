"""
Модель новостей
"""

from datetime import datetime
from app import db


class News(db.Model):
    """Новости"""
    
    __tablename__ = 'news'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    content = db.Column(db.Text, nullable=False)
    cover_image = db.Column(db.String(256), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def cover_url(self):
        """URL обложки"""
        if self.cover_image:
            return f'/uploads/news_covers/{self.cover_image}'
        return '/static/img/default-news-cover.png'
    
    @property
    def short_content(self):
        """Краткое содержание (70 символов)"""
        if len(self.content) > 70:
            return self.content[:70] + '...'
        return self.content
    
    @property
    def date_formatted(self):
        """Форматированная дата"""
        return self.created_at.strftime('%d.%m.%Y')
    
    def __repr__(self):
        return f'<News {self.title}>'
