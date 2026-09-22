"""
Модель пользователя
"""

from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    """Пользователи системы"""
    
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password = db.Column(db.String(256), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False, default='artist')  # admin, artist, label
    name = db.Column(db.String(120), nullable=False)
    avatar = db.Column(db.String(256), nullable=True)
    copyright = db.Column(db.String(256), nullable=True)
    partner_code = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(20), nullable=True)  # Телефон для SMS-кодов (формат 79XXXXXXXXX)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Текст причины блокировки (показывается пользователю после верного логина/пароля)
    block_reason = db.Column(db.Text, nullable=True)
    # Ограничение создания и отправки релизов (настраивает администратор)
    releases_restricted = db.Column(db.Boolean, default=False, nullable=False)
    releases_restriction_title = db.Column(db.String(200), nullable=True)
    releases_restriction_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Налоговая и платёжная информация (редактирует пользователь только через поддержку; админ — в карточке пользователя)
    tax_status = db.Column(db.String(32), nullable=True)
    tax_legal_name = db.Column(db.String(512), nullable=True)
    tax_inn = db.Column(db.String(12), nullable=True)
    tax_bank_account = db.Column(db.String(32), nullable=True)
    tax_bank_name = db.Column(db.String(256), nullable=True)
    tax_bank_bik = db.Column(db.String(9), nullable=True)

    telegram_username = db.Column(db.String(64), nullable=True)
    telegram_chat_id = db.Column(db.BigInteger, nullable=True, index=True)
    telegram_link_token = db.Column(db.String(48), unique=True, nullable=True, index=True)

    bonus_balance = db.Column(db.Integer, default=0, nullable=False)

    # Подписка (тариф Старт / Премиум)
    subscription_plan = db.Column(db.String(64), nullable=True)
    subscription_expires_at = db.Column(db.DateTime, nullable=True)
    subscription_reminder_sent_at = db.Column(db.DateTime, nullable=True)

    TAX_STATUS_CHOICES = (
        ('', 'Не указано'),
        ('self_employed', 'Самозанятый'),
        ('individual', 'Физическое лицо'),
        ('ip', 'Индивидуальный предприниматель (ИП)'),
        ('ooo', 'ООО'),
        ('zao', 'ЗАО'),
        ('other', 'Другое'),
    )
    
    # Связи
    releases = db.relationship('Release', backref='owner', lazy='dynamic')
    finances = db.relationship('Finance', backref='user', lazy='dynamic',
                               foreign_keys='Finance.user_id')
    tickets = db.relationship(
        'Ticket', foreign_keys='Ticket.user_id', backref='user', lazy='dynamic'
    )
    contracts = db.relationship('Contract', backref='user', lazy='dynamic',
                                foreign_keys='Contract.user_id')
    labels = db.relationship('Label', backref='user', lazy='dynamic')
    artists = db.relationship('Artist', backref='user', lazy='dynamic')
    smart_links = db.relationship('SmartLink', backref='user', lazy='dynamic')
    news = db.relationship('News', backref='author', lazy='dynamic')
    social_accounts = db.relationship('SocialAccount', backref='user', lazy='dynamic',
                                      cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Установить хеш пароля"""
        self.password = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """Проверить пароль"""
        return check_password_hash(self.password, password)

    @property
    def has_password(self):
        """Есть ли у пользователя парольный способ входа."""
        return bool((self.password or '').strip())
    
    @property
    def is_admin(self):
        """Проверка на администратора"""
        return self.role == 'admin'
    
    @property
    def is_label(self):
        """Проверка на лейбл"""
        return self.role == 'label'
    
    @property
    def is_artist(self):
        """Проверка на артиста"""
        return self.role == 'artist'
    
    @property
    def display_name(self):
        """Отображаемое имя"""
        return self.name or self.login
    
    @property
    def avatar_url(self):
        """URL аватара"""
        if self.avatar:
            return f'/uploads/avatars/{self.avatar}'
        return '/static/img/default-avatar.png'
    
    def get_default_copyright(self):
        """Получить копирайт по умолчанию"""
        if self.copyright:
            return self.copyright
        return f'© {datetime.now().year} {self.name}'

    @classmethod
    def tax_status_labels(cls):
        return dict(cls.TAX_STATUS_CHOICES)

    @property
    def tax_status_display(self):
        if not self.tax_status:
            return 'Не указано'
        return self.tax_status_labels().get(self.tax_status, self.tax_status)

    @property
    def is_releases_restricted(self):
        """Запрет на создание и отправку новых релизов (не для админов)."""
        return bool(self.releases_restricted) and self.role != 'admin'

    @property
    def subscription_active(self):
        if self.role == 'admin':
            return True
        if not (self.subscription_plan or '').strip():
            return False
        if not self.subscription_expires_at:
            return False
        return self.subscription_expires_at > datetime.utcnow()

    @property
    def subscription_status_label(self):
        if self.role == 'admin':
            return 'Администратор'
        plan = (self.subscription_plan or '').strip()
        if not plan:
            return 'Не оформлена'
        if not self.subscription_expires_at:
            return plan
        if self.subscription_expires_at <= datetime.utcnow():
            return f'{plan} (истекла)'
        return plan

    @property
    def subscription_status_kind(self):
        if self.role == 'admin' or self.subscription_active:
            return 'active'
        if self.subscription_plan:
            return 'expired'
        return 'unpaid'

    def releases_restriction_popup(self):
        """Данные для всплывающего уведомления об ограничении."""
        if not self.is_releases_restricted:
            return None
        message = (self.releases_restriction_message or '').strip()
        if not message:
            return None
        title = (self.releases_restriction_title or '').strip() or 'Отправка релизов ограничена'
        return {
            'id': f'releases-restriction-{self.id}',
            'tone': 'red',
            'badge': 'Ограничение',
            'title': title,
            'lead': message,
            'points': [],
            'callout': '',
        }

    @property
    def telegram_display(self):
        """@username для отображения."""
        raw = (self.telegram_username or '').strip().lstrip('@')
        return f'@{raw}' if raw else ''

    @property
    def phone_display(self):
        """Телефон для отображения (+7 …)."""
        raw = (self.phone or '').strip()
        if not raw:
            return ''
        digits = ''.join(c for c in raw if c.isdigit())
        if len(digits) == 11 and digits.startswith('7'):
            return f'+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}'
        if len(digits) == 10 and digits.startswith('9'):
            return f'+7 ({digits[0:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:10]}'
        return raw

    @property
    def telegram_notifications_connected(self):
        return self.telegram_chat_id is not None

    @property
    def bonus_balance_display(self):
        return int(self.bonus_balance or 0)

    def __repr__(self):
        return f'<User {self.login}>'
