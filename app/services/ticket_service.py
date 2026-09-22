"""
Операции над тикетами поддержки (создание админом, сообщения, закрытие).
"""

from datetime import datetime

from app import db
from app.models.notification import Notification
from app.models.ticket import Ticket, TicketMessage

STATUS_WAITING_USER = 'waiting_for_user'
STATUS_WAITING_ADMIN = 'waiting_for_admin'
STATUS_CLOSED = 'closed'

ACTIVE_STATUSES = (STATUS_WAITING_USER, STATUS_WAITING_ADMIN)


def create_admin_ticket(admin_id, user_id, subject, message, priority='normal'):
    """
    Тикет от администратора пользователю: ждём ответа пользователя.
    Уведомление в ЛК и письмо на почту (если настроено).
    """
    from flask import current_app

    ticket = Ticket(
        user_id=user_id,
        created_by_admin_id=admin_id,
        subject=subject,
        message=message,
        status=STATUS_WAITING_USER,
        initiator='admin',
        priority=priority or 'normal',
    )
    db.session.add(ticket)
    db.session.commit()

    # Первое сообщение в переписке (иначе после ответа пользователя оно пропадало из чата)
    db.session.add(
        TicketMessage(
            ticket_id=ticket.id,
            user_id=admin_id,
            message=message,
            is_admin=True,
        )
    )
    db.session.add(
        Notification(
            user_id=user_id,
            kind='ticket_admin_initiated',
            title='Сообщение от поддержки',
            message=f'Администратор написал вам по теме «{subject}».',
            ticket_id=ticket.id,
        )
    )
    db.session.commit()

    try:
        from app.utils.email import send_ticket_reply_email

        send_ticket_reply_email(ticket, message)
    except Exception as e:
        current_app.logger.warning('Ошибка email при создании тикета админом #%s: %s', ticket.id, e)

    _notify_ticket_created_telegram(ticket)
    return ticket


def notify_ticket_created_telegram(ticket):
    """Индивидуально уведомить автора тикета в Telegram о создании."""
    from flask import current_app

    try:
        from app.services.telegram_bot import send_ticket_created

        return bool(send_ticket_created(ticket))
    except Exception as e:
        current_app.logger.warning(
            'Telegram ticket created notify failed ticket_id=%s: %s',
            getattr(ticket, 'id', None),
            e,
        )
        return False


def _notify_ticket_created_telegram(ticket):
    return notify_ticket_created_telegram(ticket)


def _notify_ticket_status_telegram(ticket, actor_user_id=None):
    """Индивидуально уведомить автора тикета в Telegram о смене статуса."""
    from flask import current_app

    try:
        from app.services.telegram_bot import send_ticket_status

        send_ticket_status(ticket, actor_user_id=actor_user_id)
    except Exception as e:
        current_app.logger.warning(
            'Telegram ticket status notify failed ticket_id=%s: %s',
            getattr(ticket, 'id', None),
            e,
        )


def add_message(ticket_id, user_id, message, is_admin):
    """Добавить сообщение в тикет и обновить статус ожидания."""
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        return None

    prev_status = ticket.status
    row = TicketMessage(
        ticket_id=ticket_id,
        user_id=user_id,
        message=message,
        is_admin=is_admin,
    )
    db.session.add(row)
    if is_admin:
        ticket.status = STATUS_WAITING_USER
    else:
        ticket.status = STATUS_WAITING_ADMIN
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    if ticket.status != prev_status:
        _notify_ticket_status_telegram(ticket, actor_user_id=user_id)
    return row


def close_ticket(ticket_id, actor_user_id=None):
    ticket = Ticket.query.get(ticket_id)
    if not ticket:
        return None
    prev_status = ticket.status
    ticket.status = STATUS_CLOSED
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    if prev_status != STATUS_CLOSED:
        _notify_ticket_status_telegram(ticket, actor_user_id=actor_user_id)
    return ticket


def get_user_tickets(user_id):
    return (
        Ticket.query.filter_by(user_id=user_id)
        .order_by(Ticket.updated_at.desc())
        .all()
    )


def get_all_admin_tickets():
    return Ticket.query.order_by(Ticket.updated_at.desc()).all()
