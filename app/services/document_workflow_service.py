"""
Транзакционная логика документооборота: счёт + уведомление, оплата + подтверждение.
Откат при ошибках БД; сообщения для пользователя — на русском.
"""

from datetime import datetime

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.invoice import DocNotification, Invoice, PaymentConfirmation
from app.services.subscription_service import activate_subscription_from_invoice


def _fmt_amount(amount, currency):
    try:
        return f'{amount} {currency}'
    except Exception:
        return str(amount)


def create_invoice_with_notification(
    *,
    user_id,
    invoice_number,
    amount,
    currency,
    subject,
    description,
    payment_link,
    due_date,
    created_by_admin_id,
    plan_code=None,
):
    """
    Создаёт счёт (pending) и уведомление invoice_created в одной транзакции.
    Возвращает (invoice|None, error_message|None).
    """
    inv = Invoice(
        user_id=user_id,
        invoice_number=invoice_number,
        amount=amount,
        currency=currency,
        subject=subject,
        description=description or None,
        payment_link=payment_link,
        status=Invoice.STATUS_PENDING,
        due_date=due_date,
        created_by_admin_id=created_by_admin_id,
        plan_code=plan_code,
    )
    inv.refresh_overdue_status()
    msg_body = f'Счёт {invoice_number} на сумму {_fmt_amount(amount, currency)}. {subject}'
    if payment_link:
        msg_body += f' Ссылка на оплату указана в карточке счёта.'
    note = DocNotification(
        user_id=user_id,
        type=DocNotification.TYPE_INVOICE_CREATED,
        title=f'Новый счёт {invoice_number}',
        message=msg_body[:2000] if msg_body else None,
        is_read=False,
        related_invoice_id=None,
    )
    try:
        db.session.add(inv)
        db.session.flush()
        note.related_invoice_id = inv.id
        db.session.add(note)
        db.session.commit()
        return inv, None
    except IntegrityError as e:
        db.session.rollback()
        current_app.logger.warning('create_invoice IntegrityError: %s', e)
        if 'invoice_number' in str(e).lower() or 'unique' in str(e).lower():
            return None, 'Счёт с таким номером уже существует'
        return None, 'Не удалось сохранить счёт (конфликт данных)'
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('create_invoice: %s', e)
        return None, 'Произошла ошибка при создании счёта. Попробуйте позже.'


def mark_invoice_paid_manual(invoice_id):
    """
    Админ: отметить оплаченным без файла подтверждения.
    Возвращает (True, None) или (False, error).
    """
    inv = Invoice.query.get(invoice_id)
    if not inv:
        return False, 'Счёт не найден'
    if inv.status == Invoice.STATUS_PAID:
        return False, 'Счёт уже отмечен как оплаченный'
    if inv.status == Invoice.STATUS_CANCELLED:
        return False, 'Отменённый счёт нельзя отметить оплаченным'
    if inv.status not in (Invoice.STATUS_PENDING, Invoice.STATUS_OVERDUE):
        return False, 'Некорректный статус счёта'

    inv.status = Invoice.STATUS_PAID
    inv.paid_at = datetime.utcnow()
    activate_subscription_from_invoice(inv)
    note = DocNotification(
        user_id=inv.user_id,
        type=DocNotification.TYPE_PAYMENT_CONFIRMED,
        title=f'Оплата по счёту {inv.invoice_number} подтверждена',
        message='Счёт отмечен как оплаченный.',
        is_read=False,
        related_invoice_id=inv.id,
    )
    try:
        db.session.add(note)
        db.session.commit()
        return True, None
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('mark_invoice_paid_manual: %s', e)
        return False, 'Ошибка сохранения'


def cancel_invoice_admin(invoice_id):
    """Отмена счёта (только pending/overdue)."""
    inv = Invoice.query.get(invoice_id)
    if not inv:
        return False, 'Счёт не найден'
    if inv.status in (Invoice.STATUS_PAID, Invoice.STATUS_CANCELLED):
        return False, 'Нельзя отменить оплаченный или уже отменённый счёт'
    if inv.status not in (Invoice.STATUS_PENDING, Invoice.STATUS_OVERDUE):
        return False, 'Некорректный статус счёта'

    inv.status = Invoice.STATUS_CANCELLED
    try:
        db.session.commit()
        return True, None
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('cancel_invoice: %s', e)
        return False, 'Ошибка сохранения'


def add_payment_confirmation_and_pay(
    *,
    invoice_id,
    user_id,
    document_filename,
    confirmation_number=None,
    payment_date=None,
    amount=None,
    comment=None,
):
    """
    Прикрепить PDF к счёту и перевести счёт в paid + уведомление пользователю.
    document_filename — имя файла в uploads/documents/payment_confirmations (уже сохранён).
    """
    inv = Invoice.query.get(invoice_id)
    if not inv:
        return None, 'Счёт не найден'
    if inv.user_id != user_id:
        return None, 'Получатель счёта не совпадает с выбранным пользователем'
    if inv.status == Invoice.STATUS_CANCELLED:
        return None, 'Счёт отменён'
    if inv.status == Invoice.STATUS_PAID:
        return None, 'Счёт уже оплачен'
    if inv.status not in (Invoice.STATUS_PENDING, Invoice.STATUS_OVERDUE):
        return None, 'Некорректный статус счёта'
    if not document_filename:
        return None, 'Не указан файл подтверждения'

    pc = PaymentConfirmation(
        invoice_id=inv.id,
        user_id=user_id,
        confirmation_number=confirmation_number,
        payment_date=payment_date,
        amount=amount,
        document_file=document_filename,
        comment=comment,
    )
    inv.status = Invoice.STATUS_PAID
    inv.paid_at = datetime.utcnow()
    activate_subscription_from_invoice(inv)
    note = DocNotification(
        user_id=user_id,
        type=DocNotification.TYPE_PAYMENT_CONFIRMED,
        title=f'Подтверждение оплаты по счёту {inv.invoice_number}',
        message='Загружен документ подтверждения оплаты. Счёт закрыт.',
        is_read=False,
        related_invoice_id=inv.id,
    )
    try:
        db.session.add(pc)
        db.session.add(note)
        db.session.commit()
        return pc, None
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('add_payment_confirmation: %s', e)
        return None, 'Ошибка сохранения подтверждения'


def refresh_invoices_overdue(query):
    """Обновить статус overdue для выборки pending с истекшим сроком."""
    try:
        items = query.all()
    except Exception:
        return
    changed = False
    for inv in items:
        if inv.refresh_overdue_status():
            changed = True
    if changed:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
