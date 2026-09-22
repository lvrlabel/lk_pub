"""
Модели релизов, треков и платформ
"""

from datetime import datetime
from app import db


class Release(db.Model):
    """Музыкальные релизы"""
    
    __tablename__ = 'releases'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    cover = db.Column(db.String(256), nullable=True)
    title = db.Column(db.String(256), nullable=False)
    version = db.Column(db.String(100), nullable=True)
    artists = db.Column(db.String(512), nullable=False)
    type = db.Column(db.String(20), nullable=False, default='Single')  # Single, EP, Album
    genre = db.Column(db.String(100), nullable=False)
    release_date = db.Column(db.Date, nullable=False)
    yandex_presave = db.Column(db.Boolean, default=False)
    partner_code = db.Column(db.String(50), nullable=True)
    copyright = db.Column(db.String(256), nullable=True)
    upc = db.Column(db.String(20), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default='draft', index=True)
    # Статусы: draft, moderation, approved, rejected, deletion, revoked
    moderator_comment = db.Column(db.Text, nullable=True)
    platforms = db.Column(db.JSON, nullable=True)  # Список ID платформ
    # Территории, цены и прочие настройки дистрибуции (фаза 3 UI)
    dist_settings = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    tracks = db.relationship('Track', backref='release', lazy='dynamic',
                             cascade='all, delete-orphan')
    analytics = db.relationship('ReleaseAnalytics', backref='release', lazy='dynamic',
                                cascade='all, delete-orphan')
    smart_links = db.relationship('SmartLink', backref='release', lazy='dynamic')
    
    @property
    def cover_url(self):
        """URL обложки"""
        if self.cover:
            return f'/uploads/covers/{self.cover}'
        return '/static/img/default-cover.png'
    
    @property
    def tracks_count(self):
        """Количество треков"""
        return self.tracks.count()
    
    @property
    def status_display(self):
        """Отображаемый статус"""
        statuses = {
            'draft': 'Черновик',
            'moderation': 'На модерации',
            'approved': 'Одобрено',
            'rejected': 'Отклонено',
            'deletion': 'На удалении',
            'deleted': 'Удалён',
            'revoked': 'Отозвано администратором',
        }
        return statuses.get(self.status, self.status)
    
    @property
    def status_class(self):
        """CSS класс для статуса"""
        classes = {
            'draft': 'status-draft',
            'moderation': 'status-moderation',
            'approved': 'status-approved',
            'rejected': 'status-rejected',
            'deletion': 'status-deletion',
            'deleted': 'status-rejected',
            'revoked': 'status-rejected',
        }
        return classes.get(self.status, '')
    
    @property
    def type_display(self):
        """Отображаемый тип"""
        types = {
            'Single': 'Сингл',
            'EP': 'EP',
            'Album': 'Альбом'
        }
        return types.get(self.type, self.type)

    def platform_names_ordered(self):
        """Названия выбранных площадок в порядке, как при отправке."""
        raw = self.platforms
        if not raw or not isinstance(raw, list):
            return []
        ids = []
        for x in raw:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                continue
        if not ids:
            return []
        rows = Platform.query.filter(Platform.id.in_(ids)).all()
        by_id = {r.id: r.name for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    @property
    def extra_notes(self):
        """Описание / заметка из dist_settings."""
        ds = self.dist_settings
        if not isinstance(ds, dict):
            return ''
        return (ds.get('extra_notes') or '').strip()

    def can_edit(self):
        """Можно ли редактировать релиз"""
        return self.status in ['draft', 'rejected', 'revoked']
    
    def can_submit(self):
        """Можно ли отправить на модерацию"""
        return self.status in ['draft', 'rejected', 'revoked'] and self.cover and self.tracks_count > 0
    
    def can_delete(self):
        """Можно ли запросить удаление"""
        return self.status in ['draft', 'approved', 'rejected']

    @property
    def is_deleted(self):
        return self.status == 'deleted'
    
    def __repr__(self):
        return f'<Release {self.title}>'


class Track(db.Model):
    """Треки релизов"""
    
    __tablename__ = 'tracks'
    
    id = db.Column(db.Integer, primary_key=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=False, index=True)
    wav_file = db.Column(db.String(256), nullable=False)
    title = db.Column(db.String(256), nullable=False)
    version = db.Column(db.String(100), nullable=True)
    artists = db.Column(db.String(512), nullable=False)
    composers = db.Column(db.String(512), nullable=True)
    authors = db.Column(db.String(512), nullable=True)
    explicit = db.Column(db.Boolean, default=False)
    language = db.Column(db.String(50), nullable=True)
    isrc = db.Column(db.String(128), nullable=True)
    lyrics = db.Column(db.Text, nullable=True)
    track_order = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    @property
    def file_url(self):
        """URL файла трека"""
        return f'/uploads/tracks/{self.wav_file}'
    
    @property
    def display_title(self):
        """Полное название трека с версией"""
        if self.version:
            return f'{self.title} ({self.version})'
        return self.title
    
    def __repr__(self):
        return f'<Track {self.title}>'


class Platform(db.Model):
    """Платформы распространения"""
    
    __tablename__ = 'platforms'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(50), nullable=False)
    # Категории: streaming, social, video, database, store, radio, dj, international
    is_active = db.Column(db.Boolean, default=True)
    warning_message = db.Column(db.String(256), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    icon = db.Column(db.String(50), nullable=True)  # Иконка платформы
    
    @property
    def category_display(self):
        """Отображаемая категория"""
        categories = {
            'main': 'Основные магазины',
            'other': 'Остальные магазины',
            'streaming': 'Стриминговые сервисы',
            'social': 'Социальные сети',
            'video': 'Видео платформы',
            'database': 'Музыкальные базы',
            'store': 'Магазины',
            'radio': 'Радио',
            'dj': 'DJ платформы',
            'international': 'Международные',
        }
        return categories.get(self.category, self.category)

    @staticmethod
    def get_default_platforms():
        """Каталог площадок (основные + остальные) по референсу дистрибуции."""
        main = [
            'Amazon',
            'Deezer.com',
            'Facebook (music)',
            'Facebook content ID (music)',
            'iMixes',
            'iTunes Store / Apple Music',
            'Juno',
            'Lyricsfind',
            'MixUpload',
            'SoundCloud',
            'Spotify',
            'VK (OK BOOM)',
            'Yandex Music',
            'YouTube ID',
            'YouTube Music',
            'ZVUK',
        ]
        other = [
            '24/7 Entertainment',
            '7 Digital',
            'Ali / 阿里音乐',
            'Anghami Ltd',
            'Audible Magic',
            'AWA',
            'Beatport',
            'BookBeat',
            'Boomplay Music',
            'ClicknClear',
            'Digital Stores',
            'Divibibi Gmbh Audio',
            'DJ Monitor',
            'Douyin / 抖音',
            'Findaway',
            'Genius',
            'Gogopix',
            'Google Play',
            'Gracenote',
            'Highresaudio',
            'IDAGIO',
            'iHeart Radio',
            'iNaudio',
            'Instagram / Facebook',
            'JioSaavn',
            'KKBOX',
            'Kuack Media',
            'Kugou / 酷狗音乐',
            'Kuwo / 酷我音乐',
            'Line Music',
            'MediaNet-MusicNet',
            'Microsoft (Xbox)',
            'Migu Music / 咪咕音乐',
            'Mixcloud',
            'Mondia Media',
            'MoodAgent',
            'Music Island (MID)',
            'Napster',
            'NAVER VIBE',
            'NetEase Cloud Music / 网易云音乐',
            'Novelfm / 番茄畅听',
            'Pandora',
            'Peloton',
            'Phononet',
            'Pretzel',
            'Qishui Music / 汽水音乐',
            'Qobuz',
            'QQ Music',
            'Shazam',
            'Snapchat',
            'Soundmouse',
            'Tencent',
            'TESLA',
            'Tidal',
            'TikTok',
            'TIM Music',
            'Traxsource',
            'Trebel Music',
            'Vialma',
            'WeSing / 全民K歌',
            'Whatpeopleplay',
            'Яндекс Музыка',
            'VK Music',
            'SberZvuk',
        ]
        rows = []
        for i, name in enumerate(main, start=1):
            rows.append({'name': name, 'category': 'main', 'sort_order': i})
        for i, name in enumerate(other, start=1):
            rows.append({'name': name, 'category': 'other', 'sort_order': 100 + i})
        return rows
    
    def __repr__(self):
        return f'<Platform {self.name}>'
