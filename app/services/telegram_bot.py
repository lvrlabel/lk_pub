"""Telegram Bot API — рассылка текстовых новостей подписчикам."""

from __future__ import annotations

import html
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from flask import current_app, url_for

from app import db
from app.models.telegram_broadcast import TelegramBroadcast, TelegramSubscriber

logger = logging.getLogger(__name__)

KIND_LABELS = {
    'outage': ('🚨', 'О ЧП'),
    'update': ('📢', 'Обновление'),
}


def is_configured() -> bool:
    return bool(current_app.config.get('TELEGRAM_BOT_TOKEN'))


def bot_username() -> str:
    name = (current_app.config.get('TELEGRAM_BOT_USERNAME') or 'toolls_music_bot').lstrip('@')
    return name


def webhook_path() -> str:
    secret = current_app.config.get('TELEGRAM_WEBHOOK_SECRET') or ''
    return f'/telegram/webhook/{secret}' if secret else '/telegram/webhook'


def webhook_url(external: bool = True) -> str | None:
    secret = current_app.config.get('TELEGRAM_WEBHOOK_SECRET')
    try:
        if secret:
            return url_for('telegram_news.webhook', secret=secret, _external=external)
        return url_for('telegram_news.webhook', _external=external)
    except Exception:
        return None


def _api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = current_app.config.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise RuntimeError('TELEGRAM_BOT_TOKEN не задан в .env')

    url = f'https://api.telegram.org/bot{token}/{method}'
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        logger.warning('Telegram API HTTP %s: %s', exc.code, detail)
        raise RuntimeError(f'Telegram API: {detail}') from exc
    except urllib.error.URLError as exc:
        logger.warning('Telegram API network error: %s', exc)
        raise RuntimeError('Не удалось связаться с Telegram') from exc

    if not data.get('ok'):
        desc = data.get('description') or 'unknown error'
        raise RuntimeError(f'Telegram: {desc}')
    return data


def format_message(kind: str, title: str, text: str) -> str:
    icon, default_title = KIND_LABELS.get(kind, KIND_LABELS['update'])
    heading = (title or default_title).strip()
    body = (text or '').strip()
    safe_heading = html.escape(heading)
    safe_body = html.escape(body)
    bot = html.escape(f'@{bot_username()}')
    return (
        f'<b>TOOLLS</b> · Music Distribution\n'
        f'————————————\n'
        f'{icon} <b>{safe_heading}</b>\n\n'
        f'{safe_body}\n'
        f'————————————\n'
        f'<i>{bot}</i>'
    )


def _tg_card(title: str, body_lines: list[str]) -> str:
    """Единая карточка уведомления Telegram в стиле Toolls Graphite."""
    bot = html.escape(f'@{bot_username()}')
    parts = [
        '<b>TOOLLS</b> · Music Distribution',
        '————————————',
        title,
        '',
        *body_lines,
        '————————————',
        f'<i>{bot}</i>',
    ]
    return '\n'.join(parts)


def send_to_chat(chat_id: int, html_text: str) -> None:
    _api('sendMessage', {
        'chat_id': chat_id,
        'text': html_text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    })


def _clear_dead_chat_link(user, chat_id: int, exc: Exception) -> None:
    err = str(exc).lower()
    if 'blocked' in err or 'deactivated' in err or 'chat not found' in err:
        user.telegram_chat_id = None
        unsubscribe(int(chat_id))
        db.session.add(user)
        db.session.commit()


def send_login_code(user, code: str) -> bool:
    """Отправить код входа в Telegram только владельцу привязанного аккаунта."""
    chat_id = getattr(user, 'telegram_chat_id', None)
    if not user or chat_id is None:
        return False
    if not is_configured():
        logger.warning('Telegram bot not configured, skip login code for user_id=%s', getattr(user, 'id', None))
        return False

    safe_code = html.escape(str(code))
    display_name = user.display_name if hasattr(user, 'display_name') else (user.name or user.login)
    safe_name = html.escape(display_name or 'пользователь')
    text = _tg_card(
        '🔐 <b>Код для входа</b>',
        [
            f'Здравствуйте, {safe_name}!',
            '',
            f'Код: <code>{safe_code}</code>',
            '',
            'Действует 10 минут. Никому не сообщайте.',
        ],
    )
    try:
        send_to_chat(int(chat_id), text)
        logger.info('Login code sent via Telegram user_id=%s chat_id=%s', user.id, chat_id)
        return True
    except Exception as exc:
        logger.warning('Failed to send login code via Telegram user_id=%s: %s', user.id, exc)
        _clear_dead_chat_link(user, int(chat_id), exc)
        return False


def send_ticket_created(ticket) -> bool:
    """Индивидуально уведомить автора, что тикет создан."""
    if not ticket:
        return False

    user = getattr(ticket, 'user', None)
    if user is None:
        from app.models.user import User
        user = User.query.get(ticket.user_id)
    if not user:
        return False

    chat_id = getattr(user, 'telegram_chat_id', None)
    if chat_id is None or not is_configured():
        return False

    safe_subject = html.escape((ticket.subject or 'Без темы').strip() or 'Без темы')
    safe_status = html.escape(getattr(ticket, 'status_display', None) or ticket.status)
    safe_id = html.escape(getattr(ticket, 'display_id', None) or f'#{ticket.id}')
    initiator = getattr(ticket, 'initiator', 'user') or 'user'
    if initiator == 'admin':
        lead = 'Поддержка создала обращение по вашей теме.'
    else:
        lead = 'Ваш тикет принят в работу.'

    text = _tg_card(
        '🎫 <b>Тикет создан</b>',
        [
            html.escape(lead),
            '',
            f'<b>{safe_id}</b> — {safe_subject}',
            f'Статус: <b>{safe_status}</b>',
        ],
    )
    try:
        send_to_chat(int(chat_id), text)
        logger.info(
            'Ticket created sent via Telegram ticket_id=%s user_id=%s',
            ticket.id,
            user.id,
        )
        return True
    except Exception as exc:
        logger.warning(
            'Failed to send ticket created via Telegram ticket_id=%s user_id=%s: %s',
            ticket.id,
            user.id,
            exc,
        )
        _clear_dead_chat_link(user, int(chat_id), exc)
        return False


def send_ticket_status(ticket, *, actor_user_id: int | None = None) -> bool:
    """
    Индивидуально уведомить автора тикета о смене статуса.
    Не шлём, если статус меняет сам автор (например, сам закрыл тикет).
    """
    if not ticket:
        return False
    if actor_user_id is not None and int(actor_user_id) == int(ticket.user_id):
        return False

    user = getattr(ticket, 'user', None)
    if user is None:
        from app.models.user import User
        user = User.query.get(ticket.user_id)
    if not user:
        return False

    chat_id = getattr(user, 'telegram_chat_id', None)
    if chat_id is None or not is_configured():
        return False

    safe_subject = html.escape((ticket.subject or 'Без темы').strip() or 'Без темы')
    safe_status = html.escape(getattr(ticket, 'status_display', None) or ticket.status)
    safe_id = html.escape(getattr(ticket, 'display_id', None) or f'#{ticket.id}')
    text = _tg_card(
        '🎫 <b>Статус тикета обновлён</b>',
        [
            f'<b>{safe_id}</b> — {safe_subject}',
            f'Новый статус: <b>{safe_status}</b>',
        ],
    )
    try:
        send_to_chat(int(chat_id), text)
        logger.info(
            'Ticket status sent via Telegram ticket_id=%s user_id=%s status=%s',
            ticket.id,
            user.id,
            ticket.status,
        )
        return True
    except Exception as exc:
        logger.warning(
            'Failed to send ticket status via Telegram ticket_id=%s user_id=%s: %s',
            ticket.id,
            user.id,
            exc,
        )
        _clear_dead_chat_link(user, int(chat_id), exc)
        return False


def send_invoice_created(invoice) -> bool:
    """Уведомить пользователя о новом счёте в Telegram."""
    if not invoice:
        return False

    user = getattr(invoice, 'user', None)
    if user is None:
        from app.models.user import User
        user = User.query.get(invoice.user_id)
    if not user:
        return False

    chat_id = getattr(user, 'telegram_chat_id', None)
    if chat_id is None or not is_configured():
        return False

    invoices_url = url_for('documents.hub_invoices', _external=True)
    due = invoice.due_date.strftime('%d.%m.%Y') if invoice.due_date else 'не указан'
    safe_name = html.escape(user.display_name or 'пользователь')
    safe_number = html.escape(invoice.invoice_number)
    safe_subject = html.escape((invoice.subject or '').strip() or '—')
    safe_amount = html.escape(f'{invoice.amount} {invoice.currency}')
    safe_due = html.escape(due)
    safe_invoices_url = html.escape(invoices_url)

    pay_line = ''
    if invoice.payment_link:
        safe_pay_url = html.escape(invoice.payment_link)
        pay_line = f'<a href="{safe_pay_url}">Оплатить счёт</a>'

    lines = [
        f'Здравствуйте, {safe_name}!',
        '',
        f'Счёт <b>{safe_number}</b>',
        f'Тема: {safe_subject}',
        f'Сумма: <b>{safe_amount}</b>',
        f'Срок: {safe_due}',
    ]
    if pay_line:
        lines.extend(['', pay_line])
    lines.extend(['', f'<a href="{safe_invoices_url}">Финансы → Счета</a>'])

    text = _tg_card('🧾 <b>Новый счёт</b>', lines)
    try:
        send_to_chat(int(chat_id), text)
        logger.info(
            'Invoice created sent via Telegram invoice_id=%s user_id=%s',
            invoice.id,
            user.id,
        )
        return True
    except Exception as exc:
        logger.warning(
            'Failed to send invoice created via Telegram invoice_id=%s user_id=%s: %s',
            invoice.id,
            user.id,
            exc,
        )
        _clear_dead_chat_link(user, int(chat_id), exc)
        return False


def active_subscribers():
    return TelegramSubscriber.query.filter_by(is_active=True).order_by(TelegramSubscriber.id).all()


def subscribers_count() -> int:
    return TelegramSubscriber.query.filter_by(is_active=True).count()


def profile_linked_users():
    """Пользователи Toolls с привязанным Telegram (chat_id из профиля)."""
    from app.models.user import User

    return (
        User.query
        .filter(User.telegram_chat_id.isnot(None))
        .order_by(User.id)
        .all()
    )


def profile_linked_count() -> int:
    from app.models.user import User

    return User.query.filter(User.telegram_chat_id.isnot(None)).count()


def _clear_user_telegram_link(chat_id: int) -> None:
    from app.models.user import User

    user = User.query.filter_by(telegram_chat_id=int(chat_id)).first()
    if user:
        user.telegram_chat_id = None
        db.session.commit()


def subscribe(chat_id: int, username: str | None = None, first_name: str | None = None) -> TelegramSubscriber:
    row = TelegramSubscriber.query.filter_by(chat_id=chat_id).first()
    if row:
        row.is_active = True
        row.unsubscribed_at = None
        if username:
            row.username = username
        if first_name:
            row.first_name = first_name
    else:
        row = TelegramSubscriber(
            chat_id=chat_id,
            username=username,
            first_name=first_name,
            is_active=True,
        )
        db.session.add(row)
    db.session.commit()
    return row


def unsubscribe(chat_id: int) -> None:
    row = TelegramSubscriber.query.filter_by(chat_id=chat_id).first()
    if not row:
        return
    row.is_active = False
    row.unsubscribed_at = datetime.utcnow()
    db.session.commit()


def broadcast_news(kind: str, title: str, text: str, author_id: int | None) -> TelegramBroadcast:
    html_text = format_message(kind, title, text)
    recipients = profile_linked_users()
    ok = 0
    failed = 0

    for user in recipients:
        chat_id = int(user.telegram_chat_id)
        try:
            send_to_chat(chat_id, html_text)
            ok += 1
        except Exception as exc:
            failed += 1
            logger.warning(
                'Telegram send failed user_id=%s chat_id=%s: %s',
                user.id,
                chat_id,
                exc,
            )
            err = str(exc).lower()
            if 'blocked' in err or 'deactivated' in err or 'chat not found' in err:
                user.telegram_chat_id = None
                unsubscribe(chat_id)
                db.session.add(user)

    record = TelegramBroadcast(
        kind=kind,
        title=title.strip() or KIND_LABELS.get(kind, KIND_LABELS['update'])[1],
        text=text.strip(),
        author_id=author_id,
        recipients_ok=ok,
        recipients_failed=failed,
    )
    db.session.add(record)
    db.session.commit()
    return record


def set_webhook(external_url: str) -> None:
    _api('setWebhook', {'url': external_url, 'allowed_updates': ['message']})


def handle_webhook_update(update: dict[str, Any]) -> None:
    message = update.get('message') or update.get('edited_message')
    if not message:
        return

    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    if chat_id is None:
        return

    text = (message.get('text') or '').strip()
    username = (chat.get('username') or '') or None
    first_name = (chat.get('first_name') or '') or None

    if text.startswith('/start'):
        payload = ''
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            payload = parts[1].strip()

        if payload.startswith('link_'):
            link_token = payload[5:].strip()
            if link_token:
                from app.models.user import User
                user = User.query.filter_by(telegram_link_token=link_token).first()
                if user:
                    user.telegram_chat_id = int(chat_id)
                    if username:
                        user.telegram_username = username
                    db.session.commit()
                    subscribe(int(chat_id), username=username, first_name=first_name)
                    send_to_chat(
                        int(chat_id),
                        (
                            '✅ Telegram привязан к вашему аккаунту Toolls Music Distribution.\n\n'
                            'Сюда будут приходить:\n'
                            '• коды для входа в кабинет\n'
                            '• создание и статусы ваших тикетов\n'
                            '• новые счета на оплату подписки\n'
                            '• сообщения о ЧП и обновлениях сервиса\n\n'
                            'Отписаться: /stop'
                        ),
                    )
                    return

        subscribe(int(chat_id), username=username, first_name=first_name)
        send_to_chat(
            int(chat_id),
            (
                'Чтобы получать уведомления Toolls Music Distribution, привяжите Telegram в профиле личного кабинета '
                '(«Профиль» → «Привязать»).\n\n'
                'После привязки сюда приходят коды входа, статусы ваших тикетов и сообщения о ЧП.'
            ),
        )
        return

    if text.startswith('/stop'):
        unsubscribe(int(chat_id))
        _clear_user_telegram_link(int(chat_id))
        send_to_chat(int(chat_id), 'Вы отписались от уведомлений. Снова подписаться: /start')
        return

    send_to_chat(
        int(chat_id),
        (
            'Бот Toolls Music Distribution:\n'
            '• коды входа — только вам\n'
            '• статусы ваших тикетов — только вам\n'
            '• новости о ЧП — всем с привязанным Telegram\n\n'
            'Привязка: личный кабинет → Профиль → «Привязать».\n\n'
            'Команды:\n/stop — отписаться'
        ),
    )
