"""
Модель договоров
"""

from datetime import datetime, timedelta
import secrets
from werkzeug.security import check_password_hash, generate_password_hash
from app import db


class Contract(db.Model):
    """Договоры"""
    
    __tablename__ = 'contracts'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), nullable=False)
    original_filename = db.Column(db.String(256), nullable=False)
    file_path = db.Column(db.String(256), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    sign_deadline = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    # Статусы: pending, pending_review, signed, expired, rejected
    rejection_reason = db.Column(db.Text, nullable=True)
    contract_body = db.Column(db.Text, nullable=True)
    contract_type = db.Column(db.String(20), nullable=False, default='file')
    signing_code_hash = db.Column(db.String(256), nullable=True)
    signing_code_expires_at = db.Column(db.DateTime, nullable=True)
    signing_code_sent_at = db.Column(db.DateTime, nullable=True)
    signed_ip = db.Column(db.String(64), nullable=True)
    signed_user_agent = db.Column(db.String(512), nullable=True)
    signed_filename = db.Column(db.String(256), nullable=True)
    signed_file_path = db.Column(db.String(256), nullable=True)
    signed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    admin = db.relationship('User', foreign_keys=[admin_id])
    
    @property
    def file_url(self):
        """URL файла договора"""
        return f'/uploads/contracts/original/{self.file_path}'
    
    @property
    def signed_file_url(self):
        """URL подписанного файла"""
        if self.signed_file_path:
            return f'/uploads/contracts/signed/{self.signed_file_path}'
        return None
    
    @property
    def status_display(self):
        """Отображаемый статус"""
        statuses = {
            'pending': 'Ожидает подписания',
            'pending_review': 'На проверке',
            'signed': 'Подписан',
            'expired': 'Просрочен',
            'rejected': 'Отклонён'
        }
        return statuses.get(self.status, self.status)
    
    @property
    def status_class(self):
        """CSS класс для статуса"""
        classes = {
            'pending': 'status-pending',
            'pending_review': 'status-pending',
            'signed': 'status-signed',
            'expired': 'status-expired',
            'rejected': 'status-rejected'
        }
        return classes.get(self.status, '')
    
    @property
    def is_expired(self):
        """Проверка на просрочку (только для ожидающих подписания)"""
        if self.sign_deadline and self.status == 'pending':
            return datetime.utcnow() > self.sign_deadline
        return False

    @property
    def can_user_upload_signed(self):
        """Пользователь может загрузить подписанный файл"""
        return self.status == 'pending' and not self.is_expired

    @property
    def can_admin_approve_or_reject(self):
        """Админ может одобрить или отклонить (договор на проверке или ожидает)"""
        return self.status in ('pending', 'pending_review')

    @property
    def days_until_deadline(self):
        """Дней до дедлайна"""
        if self.sign_deadline and self.status == 'pending':
            delta = self.sign_deadline - datetime.utcnow()
            return max(0, delta.days)
        return None
    
    @property
    def deadline_formatted(self):
        """Форматированный дедлайн"""
        if self.sign_deadline:
            return self.sign_deadline.strftime('%d.%m.%Y')
        return '-'
    
    def check_and_update_status(self):
        """Проверка и обновление статуса при просрочке"""
        if self.is_expired and self.status == 'pending':
            self.status = 'expired'
            return True
        return False

    @property
    def is_electronic(self):
        return self.contract_type == 'electronic'

    def issue_signing_code(self):
        code = ''.join(str(secrets.randbelow(10)) for _ in range(5))
        self.signing_code_hash = generate_password_hash(code)
        self.signing_code_expires_at = datetime.utcnow() + timedelta(minutes=10)
        self.signing_code_sent_at = datetime.utcnow()
        return code

    def check_signing_code(self, code):
        if not self.signing_code_hash or not self.signing_code_expires_at:
            return False
        if datetime.utcnow() >= self.signing_code_expires_at:
            return False
        return check_password_hash(self.signing_code_hash, (code or '').strip())
    
    def __repr__(self):
        return f'<Contract {self.title}>'
