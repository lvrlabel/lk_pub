"""
Модели смарт-ссылок
"""

import secrets
from datetime import datetime
from app import db


class SmartLink(db.Model):
    """Смарт-ссылки"""
    
    __tablename__ = 'smart_links'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=False)
    link_code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    custom_name = db.Column(db.String(256), nullable=True)
    platform_links = db.Column(db.JSON, nullable=True)
    # Формат: {"spotify": "url", "apple_music": "url", ...}
    theme = db.Column(db.String(10), nullable=False, default='dark')  # light, dark
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    visits = db.relationship('LinkVisit', backref='smart_link', lazy='dynamic',
                             cascade='all, delete-orphan')
    clicks = db.relationship('LinkClick', backref='smart_link', lazy='dynamic',
                             cascade='all, delete-orphan')
    
    @staticmethod
    def generate_link_code():
        """Генерация уникального кода ссылки"""
        return secrets.token_urlsafe(16)
    
    @property
    def full_url(self):
        """Полный URL ссылки"""
        from flask import current_app
        base_url = current_app.config.get('SMART_LINK_BASE_URL', 'https://lk.toolls-muisic-distribution.ru/link')
        return f'{base_url}/{self.link_code}'
    
    @property
    def visits_count(self):
        """Количество посещений"""
        return self.visits.count()
    
    @property
    def clicks_count(self):
        """Количество кликов"""
        return self.clicks.count()
    
    @property
    def display_name(self):
        """Отображаемое название"""
        if self.custom_name:
            return self.custom_name
        return self.release.title if self.release else 'Без названия'
    
    def get_platform_links_list(self):
        """Получить список платформ со ссылками"""
        if not self.platform_links:
            return []
        
        platforms_order = [
            ('spotify', 'Spotify'),
            ('apple_music', 'Apple Music'),
            ('yandex_music', 'Яндекс Музыка'),
            ('vk_music', 'VK Музыка'),
            ('youtube_music', 'YouTube Music'),
            ('deezer', 'Deezer'),
            ('zvooq', 'Zvooq'),
            ('wink', 'Wink'),
        ]
        
        result = []
        for key, name in platforms_order:
            if key in self.platform_links and self.platform_links[key]:
                result.append({
                    'key': key,
                    'name': name,
                    'url': self.platform_links[key]
                })
        return result
    
    def __repr__(self):
        return f'<SmartLink {self.link_code}>'


class LinkVisit(db.Model):
    """Посещения смарт-ссылок"""
    
    __tablename__ = 'link_visits'
    
    id = db.Column(db.Integer, primary_key=True)
    link_code = db.Column(db.String(32), db.ForeignKey('smart_links.link_code'),
                          nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
    visited_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<LinkVisit {self.id}>'


class LinkClick(db.Model):
    """Клики по платформам в смарт-ссылках"""
    
    __tablename__ = 'link_clicks'
    
    id = db.Column(db.Integer, primary_key=True)
    link_code = db.Column(db.String(32), db.ForeignKey('smart_links.link_code'),
                          nullable=False, index=True)
    platform = db.Column(db.String(50), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    clicked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<LinkClick {self.platform}>'
