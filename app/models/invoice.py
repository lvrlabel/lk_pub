"""
Документооборот: счета, подтверждения оплаты, уведомления по счетам.

Уведомления хранятся в таблице doc_notifications, чтобы не пересекаться
с общей таблицей notifications (тикеты, релизы).
"""

from datetime import date, datetime

from app import db


class Invoice(db.Model):
    """Счёт на оплату (выставляет администратор)."""

    __tablename__ = 'invoices'

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_CANCELLED = 'cancelled'
    STATUS_OVERDUE = 'overdue'

    STATUSES = (STATUS_PENDING, STATUS_PAID, STATUS_CANCELLED, STATUS_OVERDUE)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    invoice_number = db.Column(db.String(64), nullable=False, unique=True, index=True)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='RUB')
    subject = db.Column(db.String(512), nullable=False)
    description = db.Column(db.Text, nullable=True)
    payment_link = db.Column(db.String(2048), nullable=True)
    yookassa_invoice_id = db.Column(db.String(128), nullable=True, unique=True, index=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING, index=True)
    due_date = db.Column(db.Date, nullable=True)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    paid_at = db.Column(db.DateTime, nullable=True)
    plan_code = db.Column(db.String(32), nullable=True, index=True)
    overdue_notified_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship(
        'User', foreign_keys=[user_id], backref=db.backref('invoices', lazy='dynamic')
    )
    created_by = db.relationship('User', foreign_keys=[created_by_admin_id])

    def refresh_overdue_status(self):
        """
        Если срок истёк и счёт ещё ожидает оплаты — статус overdue.
        Не трогает paid/cancelled.
        """
        if self.status not in (self.STATUS_PENDING, self.STATUS_OVERDUE):
            return False
        if not self.due_date:
            return False
        if self.due_date < date.today() and self.status == self.STATUS_PENDING:
            self.status = self.STATUS_OVERDUE
            return True
        return False

    @property
    def is_active_unpaid(self):
        return self.status in (self.STATUS_PENDING, self.STATUS_OVERDUE)

    @property
    def status_label(self):
        labels = {
            self.STATUS_PENDING: 'Ожидает оплаты',
            self.STATUS_OVERDUE: 'Просрочен',
            self.STATUS_PAID: 'Оплачен',
            self.STATUS_CANCELLED: 'Отменён',
        }
        return labels.get(self.status, self.status)

    def __repr__(self):
        return f'<Invoice {self.invoice_number}>'


class PaymentConfirmation(db.Model):
    """Подтверждение оплаты (PDF), привязка к счёту."""

    __tablename__ = 'payment_confirmations'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    confirmation_number = db.Column(db.String(128), nullable=True)
    payment_date = db.Column(db.Date, nullable=True)
    amount = db.Column(db.Numeric(14, 2), nullable=True)
    document_file = db.Column(db.String(512), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    invoice = db.relationship(
        'Invoice', backref=db.backref('payment_confirmations', lazy='dynamic')
    )
    user = db.relationship(
        'User', foreign_keys=[user_id], backref=db.backref('payment_confirmations', lazy='dynamic')
    )

    def __repr__(self):
        return f'<PaymentConfirmation {self.id} inv={self.invoice_id}>'


class DocNotification(db.Model):
    """
    Уведомления в разделе «Документооборот» (отдельно от Notification).
    Таблица: doc_notifications.
    """

    __tablename__ = 'doc_notifications'

    TYPE_INVOICE_CREATED = 'invoice_created'
    TYPE_INVOICE_REMINDER = 'invoice_reminder'
    TYPE_PAYMENT_CONFIRMED = 'payment_confirmed'

    TYPES = (TYPE_INVOICE_CREATED, TYPE_INVOICE_REMINDER, TYPE_PAYMENT_CONFIRMED)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    type = db.Column(db.String(32), nullable=False, index=True)
    title = db.Column(db.String(256), nullable=False)
    message = db.Column(db.Text, nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    related_invoice_id = db.Column(
        db.Integer, db.ForeignKey('invoices.id'), nullable=True, index=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship(
        'User', backref=db.backref('doc_notifications', lazy='dynamic')
    )
    related_invoice = db.relationship(
        'Invoice', backref=db.backref('doc_notifications', lazy='dynamic')
    )

    @property
    def type_label(self):
        labels = {
            self.TYPE_INVOICE_CREATED: 'Новый счёт',
            self.TYPE_INVOICE_REMINDER: 'Напоминание',
            self.TYPE_PAYMENT_CONFIRMED: 'Оплата подтверждена',
        }
        return labels.get(self.type, self.type)

    def __repr__(self):
        return f'<DocNotification {self.id} {self.type}>'
