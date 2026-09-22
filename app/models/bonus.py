"""
Бонусная программа: история начислений и списаний.
"""

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

from app import db


def _to_local_msk(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        if ZoneInfo is not None:
            return dt.astimezone(ZoneInfo('Europe/Moscow'))
    except Exception:
        pass
    return dt.astimezone(timezone(timedelta(hours=3)))


class BonusTransaction(db.Model):
    """Запись о начислении или списании бонусных баллов."""

    __tablename__ = 'bonus_transactions'
    __table_args__ = (
        db.Index('ix_bonus_transactions_user_created', 'user_id', 'created_at'),
    )

    TYPE_CREDIT = 'credit'
    TYPE_DEBIT = 'debit'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    amount = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(16), nullable=False)
    comment = db.Column(db.String(512), nullable=True)
    service_key = db.Column(db.String(32), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship(
        'User',
        foreign_keys=[user_id],
        backref=db.backref('bonus_transactions', lazy='dynamic', order_by='BonusTransaction.created_at.desc()'),
    )
    created_by = db.relationship('User', foreign_keys=[created_by_id])

    @property
    def is_credit(self):
        return self.transaction_type == self.TYPE_CREDIT

    @property
    def signed_amount(self):
        return abs(int(self.amount or 0))

    @property
    def amount_display(self):
        value = self.signed_amount
        prefix = '+' if self.is_credit else '−'
        return f'{prefix}{value}'

    @property
    def created_at_local(self):
        return _to_local_msk(self.created_at)

    @property
    def created_display(self):
        dt = self.created_at_local
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''

    def service_title(self, catalog):
        if not self.service_key:
            return None
        item = catalog.get(self.service_key) or {}
        return item.get('title') or self.service_key

    def __repr__(self):
        return f'<BonusTransaction user={self.user_id} {self.transaction_type} {self.amount}>'
