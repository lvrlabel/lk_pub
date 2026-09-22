"""Подписка: активация после оплаты, ограничение при просрочке, напоминания."""

from datetime import datetime, timedelta

from flask import current_app

from app import db
from app.models.invoice import Invoice
from app.models.user import User
from app.services.subscription_plans import get_plan

SUBSCRIPTION_DAYS = 30
REMINDER_DAYS_BEFORE = 7

OVERDUE_RESTRICTION_TITLE = 'Выгрузка релизов приостановлена'
OVERDUE_RESTRICTION_MESSAGE = (
    'Срок оплаты счёта истёк. Выгрузка новых релизов приостановлена до оплаты подписки. '
    'Перейдите в раздел «Финансы → Счета», оплатите счёт и при необходимости загрузите подтверждение.'
)


def _plan_name_for_invoice(invoice):
    if invoice.plan_code:
        plan = get_plan(invoice.plan_code)
        if plan:
            return plan['name']
    subject = (invoice.subject or '').strip()
    if subject:
        return subject
    return 'Подписка'


def activate_subscription_from_invoice(invoice):
    """После оплаты счёта: подписка + снятие ограничения на релизы."""
    user = User.query.get(invoice.user_id) if invoice else None
    if not user or user.role == 'admin':
        return user

    plan_name = _plan_name_for_invoice(invoice)
    now = datetime.utcnow()
    base = user.subscription_expires_at if user.subscription_expires_at and user.subscription_expires_at > now else now
    user.subscription_plan = plan_name
    user.subscription_expires_at = base + timedelta(days=SUBSCRIPTION_DAYS)
    user.subscription_reminder_sent_at = None
    user.releases_restricted = False
    user.releases_restriction_title = None
    user.releases_restriction_message = None
    return user


def restrict_user_for_overdue_invoice(invoice):
    """Просроченный счёт — ограничить выгрузку релизов (один раз уведомить)."""
    user = User.query.get(invoice.user_id) if invoice else None
    if not user or user.role == 'admin':
        return False
    if invoice.overdue_notified_at:
        return False

    user.releases_restricted = True
    user.releases_restriction_title = OVERDUE_RESTRICTION_TITLE
    user.releases_restriction_message = OVERDUE_RESTRICTION_MESSAGE
    invoice.overdue_notified_at = datetime.utcnow()
    return True


def process_overdue_invoices():
    """Проверить просроченные счета и применить ограничения + email."""
    from app.utils.email import send_invoice_overdue_email
    from app.services.document_workflow_service import refresh_invoices_overdue

    q = Invoice.query.filter(Invoice.status.in_((Invoice.STATUS_PENDING, Invoice.STATUS_OVERDUE)))
    refresh_invoices_overdue(q)

    changed = 0
    for inv in Invoice.query.filter_by(status=Invoice.STATUS_OVERDUE).all():
        if restrict_user_for_overdue_invoice(inv):
            changed += 1
            try:
                send_invoice_overdue_email(inv)
            except Exception as e:
                current_app.logger.warning('overdue email failed inv=%s: %s', inv.id, e)
    if changed:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return changed


def process_subscription_reminders():
    """Напоминание за 7 дней до окончания подписки."""
    from app.utils.email import send_subscription_reminder_email

    now = datetime.utcnow()
    window_end = now + timedelta(days=REMINDER_DAYS_BEFORE)
    sent = 0
    users = User.query.filter(
        User.role != 'admin',
        User.subscription_plan.isnot(None),
        User.subscription_expires_at.isnot(None),
        User.subscription_expires_at > now,
        User.subscription_expires_at <= window_end,
    ).all()
    for user in users:
        last = user.subscription_reminder_sent_at
        if last and (now - last).days < 20:
            continue
        try:
            if send_subscription_reminder_email(user):
                user.subscription_reminder_sent_at = now
                sent += 1
        except Exception as e:
            current_app.logger.warning('subscription reminder failed user=%s: %s', user.id, e)
    if sent:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return sent
