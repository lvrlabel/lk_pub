"""
Модели финансов
"""

from datetime import datetime
from app import db


class Finance(db.Model):
    """Финансовые отчеты"""
    
    __tablename__ = 'finances'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    quarter = db.Column(db.Integer, nullable=False)  # 1-4
    year = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    file_path = db.Column(db.String(256), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Связи
    uploader = db.relationship('User', foreign_keys=[uploaded_by])
    approval = db.relationship('FinanceApproval', backref='finance', uselist=False,
                               cascade='all, delete-orphan')
    platform_lines = db.relationship(
        'FinancePlatformLine',
        back_populates='finance',
        order_by='FinancePlatformLine.sort_order',
        cascade='all, delete-orphan',
    )
    
    @property
    def quarter_display(self):
        """Отображение квартала"""
        quarters = ['I', 'II', 'III', 'IV']
        return f'{quarters[self.quarter - 1]} квартал {self.year}'
    
    @property
    def file_url(self):
        """URL файла отчета"""
        if self.file_path:
            return f'/uploads/finances/{self.file_path}'
        return None
    
    @property
    def amount_formatted(self):
        """Форматированная сумма"""
        return f'{self.amount:,.2f} ₽'.replace(',', ' ')
    
    @property
    def has_approval_request(self):
        """Есть ли запрос на согласование"""
        return self.approval is not None

    @property
    def has_platform_breakdown(self):
        return bool(self.platform_lines)

    @property
    def net_from_platform_lines(self):
        """Сумма (роялти − штрафы) по строкам площадок"""
        return sum(line.net_amount for line in self.platform_lines)

    def __repr__(self):
        return f'<Finance Q{self.quarter}/{self.year} user={self.user_id}>'


class FinanceApproval(db.Model):
    """Согласование выплат"""
    
    __tablename__ = 'finance_approvals'
    
    id = db.Column(db.Integer, primary_key=True)
    finance_id = db.Column(db.Integer, db.ForeignKey('finances.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    contact_info = db.Column(db.String(256), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    card_number = db.Column(db.String(20), nullable=True)
    account_number = db.Column(db.String(30), nullable=True)
    admin_comment = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')
    # Статусы: pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processed_at = db.Column(db.DateTime, nullable=True)
    
    # Связи
    user = db.relationship('User', foreign_keys=[user_id])
    
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
    def masked_card(self):
        """Маскированный номер карты"""
        if self.card_number and len(self.card_number) >= 4:
            return f'**** **** **** {self.card_number[-4:]}'
        return None
    
    @property
    def amount_formatted(self):
        """Форматированная сумма"""
        return f'{self.amount:,.2f} ₽'.replace(',', ' ')
    
    def __repr__(self):
        return f'<FinanceApproval {self.id} status={self.status}>'


class FinancePlatformLine(db.Model):
    """Строка отчёта: начисления и штрафы по одной площадке (заполняет только админ)."""

    __tablename__ = 'finance_platform_lines'

    id = db.Column(db.Integer, primary_key=True)
    finance_id = db.Column(
        db.Integer,
        db.ForeignKey('finances.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    platform_name = db.Column(db.String(128), nullable=False)
    royalty_amount = db.Column(db.Float, nullable=False, default=0.0)
    penalty_amount = db.Column(db.Float, nullable=False, default=0.0)

    finance = db.relationship('Finance', back_populates='platform_lines')

    @property
    def net_amount(self):
        return float(self.royalty_amount or 0) - float(self.penalty_amount or 0)

    def __repr__(self):
        return f'<FinancePlatformLine {self.platform_name} net={self.net_amount}>'
