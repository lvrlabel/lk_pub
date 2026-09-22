"""
Непрочитанные сообщения в персональном чате с менеджером.
"""
from datetime import datetime

from app import db
from app.models.ticket import Ticket, TicketMessage

# Должен совпадать с tickets.MANAGER_CHAT_PREFIX
MANAGER_CHAT_PREFIX = '[MANAGER_CHAT]'


def _is_manager_row(ticket):
    return bool(ticket and ticket.subject and ticket.subject.startswith(MANAGER_CHAT_PREFIX))


def unread_from_manager_count(ticket):
    """Сообщения от менеджера (админа), которые пользователь ещё не «дочитал»."""
    if not _is_manager_row(ticket):
        return 0
    q = ticket.messages.filter(TicketMessage.is_admin.is_(True))
    if ticket.manager_chat_read_by_user_at:
        q = q.filter(TicketMessage.created_at > ticket.manager_chat_read_by_user_at)
    return q.count()


def unread_from_user_count(ticket):
    """Сообщения от пользователя, которые назначенный менеджер ещё не открывал после них."""
    if not _is_manager_row(ticket):
        return 0
    q = ticket.messages.filter(TicketMessage.is_admin.is_(False))
    if ticket.manager_chat_read_by_admin_at:
        q = q.filter(TicketMessage.created_at > ticket.manager_chat_read_by_admin_at)
    return q.count()


def total_unread_for_viewer(user):
    """Суммарное число входящих непрочитанных для текущей роли."""
    if not user or not user.is_authenticated:
        return 0
    if user.is_admin:
        q = Ticket.query.filter(
            Ticket.subject.like(f'{MANAGER_CHAT_PREFIX}%'),
            Ticket.created_by_admin_id == user.id,
        )
        return sum(unread_from_user_count(t) for t in q.all())
    q = Ticket.query.filter(
        Ticket.subject.like(f'{MANAGER_CHAT_PREFIX}%'),
        Ticket.user_id == user.id,
    )
    return sum(unread_from_manager_count(t) for t in q.all())


def mark_chat_viewed(ticket, user):
    """Отметить просмотр открытого чата (вызывать до отдачи страницы)."""
    if not ticket or not user or not user.is_authenticated:
        return
    if not _is_manager_row(ticket):
        return
    now = datetime.utcnow()
    if user.is_admin:
        # Любой админ, открывший чат, отмечает сообщения пользователя прочитанными
        ticket.manager_chat_read_by_admin_at = now
        db.session.add(ticket)
        return
    if ticket.user_id == user.id:
        ticket.manager_chat_read_by_user_at = now
        db.session.add(ticket)


def is_message_read_by_peer(ticket, created_at, is_admin_message):
    """
    Сообщение прочитано собеседником?
    Сообщения админа — только если пользователь открывал чат ПОСЛЕ сообщения.
    Сообщения пользователя — только если админ/менеджер открывал чат ПОСЛЕ сообщения.
    """
    if not ticket or not created_at:
        return False
    # Важно не перепутать курсоры: свои сообщения никогда не читаются «самим собой»
    if is_admin_message:
        peer_at = ticket.manager_chat_read_by_user_at
    else:
        peer_at = ticket.manager_chat_read_by_admin_at
    if not peer_at:
        return False
    return peer_at >= created_at


def outgoing_read_map(ticket, viewer_is_admin):
    """
    Карта прочтения исходящих сообщений для текущего зрителя.
    {message_id: bool}
    """
    result = {}
    if not ticket:
        return result
    for msg in ticket.messages.order_by(TicketMessage.created_at.asc()).all():
        mine = bool(msg.is_admin) == bool(viewer_is_admin)
        if not mine:
            continue
        result[msg.id] = is_message_read_by_peer(ticket, msg.created_at, bool(msg.is_admin))
    return result
