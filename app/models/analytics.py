"""
Модели аналитики
"""

from datetime import datetime
from app import db


class ReleaseAnalytics(db.Model):
    """Аналитика релизов"""
    
    __tablename__ = 'release_analytics'
    
    id = db.Column(db.Integer, primary_key=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=False, index=True)
    month = db.Column(db.Integer, nullable=True)  # 1-12
    week = db.Column(db.Integer, nullable=True)   # 1-52
    year = db.Column(db.Integer, nullable=False)
    streams = db.Column(db.Integer, default=0)
    downloads = db.Column(db.Integer, default=0)
    revenue = db.Column(db.Float, default=0.0)  # В рублях
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    device_analytics = db.relationship('DeviceAnalytics', backref='release_analytics',
                                       lazy='dynamic', cascade='all, delete-orphan')
    platform_analytics = db.relationship('PlatformAnalytics', backref='release_analytics',
                                         lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def period_display(self):
        """Отображение периода"""
        if self.month is not None and 1 <= self.month <= 12:
            months = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                     'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
            return f'{months[self.month - 1]} {self.year}'
        elif self.week:
            return f'Неделя {self.week}, {self.year}'
        return f'{self.year}'
    
    @property
    def period_type(self):
        """Тип периода"""
        if self.month:
            return 'monthly'
        elif self.week:
            return 'weekly'
        return 'yearly'
    
    def __repr__(self):
        return f'<ReleaseAnalytics release={self.release_id} {self.period_display}>'


class DeviceAnalytics(db.Model):
    """Аналитика по устройствам"""
    
    __tablename__ = 'device_analytics'
    
    id = db.Column(db.Integer, primary_key=True)
    release_analytics_id = db.Column(db.Integer, db.ForeignKey('release_analytics.id'),
                                     nullable=False, index=True)
    device_type = db.Column(db.String(50), nullable=False)
    # Типы: Mobile, Desktop, Tablet, Smart TV
    streams = db.Column(db.Integer, default=0)
    downloads = db.Column(db.Integer, default=0)
    
    @staticmethod
    def get_device_types():
        """Получить типы устройств"""
        return ['Mobile', 'Desktop', 'Tablet', 'Smart TV']
    
    def __repr__(self):
        return f'<DeviceAnalytics {self.device_type}>'


class PlatformAnalytics(db.Model):
    """Аналитика по платформам"""
    
    __tablename__ = 'platform_analytics'
    
    id = db.Column(db.Integer, primary_key=True)
    release_analytics_id = db.Column(db.Integer, db.ForeignKey('release_analytics.id'),
                                     nullable=False, index=True)
    platform_name = db.Column(db.String(100), nullable=False)
    streams = db.Column(db.Integer, default=0)
    downloads = db.Column(db.Integer, default=0)
    revenue = db.Column(db.Float, default=0.0)
    
    @staticmethod
    def get_main_platforms():
        """Получить основные платформы для аналитики"""
        return ['Spotify', 'Apple Music', 'YouTube Music', 'VK Music', 'Яндекс Музыка']
    
    def __repr__(self):
        return f'<PlatformAnalytics {self.platform_name}>'


class PlatformDailyListen(db.Model):
    """
    Прослушивания по площадкам по дням — для графика типа «Прослушиваний»
    (несколько линий/площадей по оси дат).
    """

    __tablename__ = 'platform_daily_listens'
    __table_args__ = (
        db.UniqueConstraint('release_id', 'stat_date', 'platform_name', name='uq_daily_release_platform_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=False, index=True)
    stat_date = db.Column(db.Date, nullable=False, index=True)
    platform_name = db.Column(db.String(120), nullable=False)
    listens = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @staticmethod
    def default_platforms():
        """Площадки как на типовых дашбордах (можно дополнять вручную)."""
        return [
            'Яндекс.Музыка', 'YouTube', 'Spotify', 'Instagram', 'Facebook', 'TikTok',
            'Deezer', 'Boomplay', 'Одноклассники', 'Apple Music', 'Pandora',
            'SoundCloud', 'Snapchat', 'Zvuk (СберЗвук)', 'VK Музыка', 'YouTube Music',
        ]
