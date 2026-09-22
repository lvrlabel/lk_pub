"""
Модели авторизации
"""

import secrets
from datetime import datetime, timedelta
from app import db


class AuthToken(db.Model):
    """Токены авторизации"""
    
    __tablename__ = 'auth_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    token = db.Column(db.String(256), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    user = db.relationship('User', backref='auth_tokens')
    
    @staticmethod
    def generate_token():
        """Генерация уникального токена"""
        return secrets.token_urlsafe(64)
    
    @staticmethod
    def create_for_user(user_id, expires_in_minutes=30):
        """Создать токен для пользователя"""
        token = AuthToken(
            user_id=user_id,
            token=AuthToken.generate_token(),
            expires_at=datetime.utcnow() + timedelta(minutes=expires_in_minutes)
        )
        return token
    
    @property
    def is_valid(self):
        """Проверка валидности токена"""
        return not self.is_used and datetime.utcnow() < self.expires_at
    
    @property
    def is_expired(self):
        """Проверка на просрочку"""
        return datetime.utcnow() >= self.expires_at
    
    def mark_as_used(self):
        """Пометить токен как использованный"""
        self.is_used = True
    
    def __repr__(self):
        return f'<AuthToken user={self.user_id}>'


class LoginCode(db.Model):
    """Код подтверждения входа (5 цифр), отправляется на SMS и/или email после ввода логина/пароля."""

    __tablename__ = 'login_codes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    code = db.Column(db.String(5), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('login_codes', lazy='dynamic'))

    @staticmethod
    def _generate_code():
        """Генерация 5-значного кода (строка из цифр)."""
        return ''.join(str(secrets.randbelow(10)) for _ in range(5))

    @staticmethod
    def create_for_user(user_id, expires_in_minutes=10):
        """
        Создать код для пользователя. Старые коды этого пользователя удаляются.
        Возвращает созданный объект LoginCode (с code в виде строки из 5 цифр).
        """
        LoginCode.query.filter_by(user_id=user_id).delete()
        code_str = LoginCode._generate_code()
        login_code = LoginCode(
            user_id=user_id,
            code=code_str,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_in_minutes),
        )
        db.session.add(login_code)
        return login_code

    @property
    def is_expired(self):
        return datetime.utcnow() >= self.expires_at

    @staticmethod
    def get_valid_for_user(user_id):
        """Получить актуальный (не просроченный) код для пользователя или None."""
        return LoginCode.query.filter_by(user_id=user_id).filter(
            LoginCode.expires_at > datetime.utcnow()
        ).order_by(LoginCode.created_at.desc()).first()

    @staticmethod
    def last_sent_at(user_id):
        """Время последней отправки кода пользователю (для rate limit)."""
        last = LoginCode.query.filter_by(user_id=user_id).order_by(
            LoginCode.created_at.desc()
        ).first()
        return last.created_at if last else None

    def __repr__(self):
        return f'<LoginCode user={self.user_id}>'


class ProfileUpdateCode(db.Model):
    """Код подтверждения изменения профиля (5 цифр), отправляется на email текущего аккаунта."""

    __tablename__ = 'profile_update_codes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    code = db.Column(db.String(5), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('profile_update_codes', lazy='dynamic'))

    @staticmethod
    def _generate_code():
        return ''.join(str(secrets.randbelow(10)) for _ in range(5))

    @staticmethod
    def create_for_user(user_id, expires_in_minutes=10):
        ProfileUpdateCode.query.filter_by(user_id=user_id).delete()
        code_str = ProfileUpdateCode._generate_code()
        code_obj = ProfileUpdateCode(
            user_id=user_id,
            code=code_str,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_in_minutes),
        )
        db.session.add(code_obj)
        return code_obj

    @property
    def is_expired(self):
        return datetime.utcnow() >= self.expires_at

    @staticmethod
    def get_valid_for_user(user_id):
        return ProfileUpdateCode.query.filter_by(user_id=user_id).filter(
            ProfileUpdateCode.expires_at > datetime.utcnow()
        ).order_by(ProfileUpdateCode.created_at.desc()).first()

    @staticmethod
    def last_sent_at(user_id):
        last = ProfileUpdateCode.query.filter_by(user_id=user_id).order_by(
            ProfileUpdateCode.created_at.desc()
        ).first()
        return last.created_at if last else None

    def __repr__(self):
        return f'<ProfileUpdateCode user={self.user_id}>'


class RegistrationRequest(db.Model):
    """Запросы на регистрацию"""
    
    __tablename__ = 'registration_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), nullable=False)
    artist_type = db.Column(db.String(50), nullable=False)  # artist, label
    artist_name = db.Column(db.String(256), nullable=False)
    start_year = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    # Статусы: pending, approved, rejected
    processed_at = db.Column(db.DateTime, nullable=True)
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    processor = db.relationship('User', foreign_keys=[processed_by])
    
    @staticmethod
    def generate_code():
        """Генерация уникального кода заявки"""
        return secrets.token_urlsafe(16)
    
    @property
    def status_display(self):
        """Отображаемый статус"""
        statuses = {
            'pending': 'На рассмотрении',
            'approved': 'Одобрено',
            'rejected': 'Отклонено'
        }
        return statuses.get(self.status, self.status)
    
    @property
    def status_class(self):
        """CSS класс для статуса"""
        classes = {
            'pending': 'status-pending',
            'approved': 'status-approved',
            'rejected': 'status-rejected'
        }
        return classes.get(self.status, '')
    
    @property
    def artist_type_display(self):
        """Отображаемый тип артиста"""
        types = {
            'artist': 'Артист',
            'label': 'Лейбл'
        }
        return types.get(self.artist_type, self.artist_type)
    
    def __repr__(self):
        return f'<RegistrationRequest {self.code}>'
