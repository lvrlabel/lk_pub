"""
Утилиты для отправки email
"""

import logging
from flask import url_for, current_app, render_template
from flask_mail import Mail, Message

logger = logging.getLogger(__name__)

mail = Mail()


def _smtp_sender_email():
    """
    Адрес From для исходящей почты.
    На Reg.ru и ряде хостингов SMTP требует, чтобы From совпадал с MAIL_USERNAME.
    """
    mail_username = (current_app.config.get('MAIL_USERNAME') or '').strip()
    default_sender = (current_app.config.get('MAIL_DEFAULT_SENDER') or '').strip()
    if mail_username and '@' in mail_username:
        return mail_username
    return default_sender or mail_username or ''


def init_mail(app):
    """Инициализация Flask-Mail"""
    mail.init_app(app)


def get_ticket_executor_emails():
    """
    Получить список email исполнителей тикетов.
    Если задан SUPPORT_EMAIL — берём его (можно несколько через запятую).
    Иначе — email всех админов.
    """
    support = current_app.config.get('SUPPORT_EMAIL') or ''
    if support:
        return [e.strip() for e in support.split(',') if e.strip()]
    from app.models.user import User
    admins = User.query.filter_by(role='admin', is_active=True).all()
    return [u.email for u in admins if u.email]


def send_ticket_accepted_email(ticket):
    """
    Отправить исполнителям email о принятии тикета в работу.
    В письме: номер тикета, тема, автор, ссылка на тикет.
    """
    recipients = get_ticket_executor_emails()
    if not recipients:
        logger.warning('Нет адресов для отправки уведомления о тикете #%s', ticket.id)
        return False

    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен (MAIL_SERVER). Пропуск отправки тикета #%s', ticket.id)
        return False

    sender = _smtp_sender_email()
    if not sender:
        logger.warning('Не задан отправитель (MAIL_USERNAME / MAIL_DEFAULT_SENDER). Пропуск тикета #%s', ticket.id)
        return False

    try:
        ticket_url = url_for('tickets.view', id=ticket.id, _external=True)
        author_name = ticket.user.display_name if ticket.user else 'Неизвестный'
        subject = f'[{ticket.display_id}] Принят в работу: {ticket.subject}'

        body = f"""Тикет {ticket.display_id} принят в работу.

Тема: {ticket.subject}
Автор: {author_name}

Ссылка на тикет: {ticket_url}

---
Личный кабинет Toolls Music Distribution
"""

        msg = Message(
            subject=subject,
            body=body,
            recipients=recipients,
            sender=sender
        )
        mail.send(msg)
        logger.info('Отправлено уведомление о тикете #%s на %s', ticket.id, recipients)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки email о тикете #%s: %s', ticket.id, e)
        return False


def send_ticket_confirmation_to_author(ticket):
    """
    Отправить автору тикета (артисту) подтверждение на email из профиля.
    Письмо с номером тикета и ссылкой. HTML-шаблон в стиле писем по релизам.
    """
    if not ticket.user or not ticket.user.email:
        logger.warning('У автора тикета #%s нет email', ticket.id)
        return False

    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен (MAIL_SERVER). Пропуск подтверждения тикета #%s', ticket.id)
        return False

    sender = _smtp_sender_email()
    if not sender:
        logger.warning('Не задан отправитель (MAIL_USERNAME / MAIL_DEFAULT_SENDER). Пропуск подтверждения #%s', ticket.id)
        return False

    try:
        ticket_url = url_for('tickets.view', id=ticket.id, _external=True)
        dashboard_url = url_for('dashboard.index', _external=True)
        logo_url = url_for('static', filename='img/logo-light.svg', _external=True)
        subject = f'[{ticket.display_id}] Ваше обращение принято в работу'

        body = f"""Здравствуйте!

Ваш тикет {ticket.display_id} принят в работу.

Тема: {ticket.subject}

Ссылка на тикет: {ticket_url}

Мы ответим в ближайшее время.

---
Личный кабинет Toolls Music Distribution
"""

        html_body = render_template('emails/ticket_confirmation.html',
            ticket_url=ticket_url,
            dashboard_url=dashboard_url,
            logo_url=logo_url,
            ticket_id=ticket.display_id,
            subject=ticket.subject,
            author_name=ticket.user.display_name if ticket.user else None
        )

        msg = Message(
            subject=subject,
            body=body,
            html=html_body,
            recipients=[ticket.user.email],
            sender=sender
        )
        mail.send(msg)
        logger.info('Отправлено подтверждение тикета #%s автору %s', ticket.id, ticket.user.email)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки подтверждения тикета #%s: %s', ticket.id, e)
        return False


def send_ticket_reply_email(ticket, reply_message):
    """
    Отправить автору тикета email о новом ответе (когда ответил админ).
    HTML-шаблон в стиле писем по релизам.
    """
    if not ticket.user or not ticket.user.email:
        logger.warning('У автора тикета #%s нет email', ticket.id)
        return False
    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен. Пропуск уведомления об ответе #%s', ticket.id)
        return False
    sender = _smtp_sender_email()
    if not sender:
        logger.warning('Не задан отправитель (MAIL_USERNAME / MAIL_DEFAULT_SENDER)')
        return False
    try:
        ticket_url = url_for('tickets.view', id=ticket.id, _external=True)
        dashboard_url = url_for('dashboard.index', _external=True)
        logo_url = url_for('static', filename='img/logo-light.svg', _external=True)
        reply_preview = (reply_message[:500] + '...') if len(reply_message) > 500 else reply_message
        subject = f'[{ticket.display_id}] Запрос от поддержки'
        msg_preview_plain = (reply_message[:300] + '...') if len(reply_message) > 300 else reply_message
        msg_preview_plain = msg_preview_plain.replace('\r', '').replace('\n', ' ')
        greet_name = ticket.user.display_name if ticket.user and ticket.user.display_name else None
        salutation = f'Добрый день, {greet_name}!' if greet_name else 'Добрый день!'
        body = f"""Запрос от поддержки

{salutation}

Вам пишет поддержка. Ниже — сообщение по обращению {ticket.display_id}.

Тема: {ticket.subject}

Сообщение:
{msg_preview_plain}

Ссылка на обращение: {ticket_url}

---
Личный кабинет Toolls Music Distribution
"""
        html_body = render_template('emails/ticket_reply.html',
            ticket_url=ticket_url,
            dashboard_url=dashboard_url,
            logo_url=logo_url,
            ticket_id=ticket.display_id,
            subject=ticket.subject,
            author_name=ticket.user.display_name if ticket.user else None,
            reply_preview=reply_preview
        )
        msg = Message(
            subject=subject,
            body=body,
            html=html_body,
            recipients=[ticket.user.email],
            sender=sender
        )
        mail.send(msg)
        logger.info('Отправлено уведомление об ответе в тикете #%s автору %s', ticket.id, ticket.user.email)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки уведомления об ответе #%s: %s', ticket.id, e)
        return False


def send_ticket_closed_email(ticket):
    """
    Отправить автору тикета email о закрытии тикета.
    HTML-шаблон в стиле писем по релизам.
    """
    if not ticket.user or not ticket.user.email:
        logger.warning('У автора тикета #%s нет email', ticket.id)
        return False
    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен. Пропуск уведомления о закрытии #%s', ticket.id)
        return False
    sender = _smtp_sender_email()
    if not sender:
        logger.warning('Не задан отправитель (MAIL_USERNAME / MAIL_DEFAULT_SENDER)')
        return False
    try:
        ticket_url = url_for('tickets.view', id=ticket.id, _external=True)
        dashboard_url = url_for('dashboard.index', _external=True)
        logo_url = url_for('static', filename='img/logo-light.svg', _external=True)
        subject = f'[{ticket.display_id}] Закрыт: {ticket.subject}'
        body = f"""Здравствуйте!

Ваш тикет {ticket.display_id} закрыт.

Тема: {ticket.subject}

Ссылка на тикет: {ticket_url}

Спасибо за обращение!

---
Личный кабинет Toolls Music Distribution
"""
        html_body = render_template('emails/ticket_closed.html',
            ticket_url=ticket_url,
            dashboard_url=dashboard_url,
            logo_url=logo_url,
            ticket_id=ticket.display_id,
            subject=ticket.subject,
            author_name=ticket.user.display_name if ticket.user else None
        )
        msg = Message(
            subject=subject,
            body=body,
            html=html_body,
            recipients=[ticket.user.email],
            sender=sender
        )
        mail.send(msg)
        logger.info('Отправлено уведомление о закрытии тикета #%s автору %s', ticket.id, ticket.user.email)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки уведомления о закрытии #%s: %s', ticket.id, e)
        return False


def send_login_code_email(user, code, recipient_override=None):
    """
    Отправить пользователю письмо с кодом подтверждения входа (4 цифры).
    user — объект User, code — строка из 4 цифр.
    recipient_override — если задан, письмо уходит на этот email (для администратора).
    Возвращает (True, None) при успехе или (False, сообщение_об_ошибке).
    """
    to_email = recipient_override or (getattr(user, 'email', None) if user else None)
    if not user or not to_email:
        logger.warning('У пользователя (id=%s) нет email для отправки кода входа', getattr(user, 'id', None))
        return False, 'В аккаунте не указан email.'
    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен (MAIL_SERVER). Пропуск отправки кода входа.')
        return False, 'Почта не настроена: в .env не задан MAIL_SERVER.'
    mail_username = (current_app.config.get('MAIL_USERNAME') or '').strip()
    sender = (current_app.config.get('MAIL_DEFAULT_SENDER') or '').strip() or mail_username
    if not sender:
        logger.warning('MAIL_DEFAULT_SENDER не задан. Пропуск отправки кода входа.')
        return False, 'Почта не настроена: в .env не задан MAIL_DEFAULT_SENDER.'
    # SMTP: From должен совпадать с логином — используем только email, без имени
    if mail_username and '@' in mail_username:
        sender = mail_username
    try:
        login_url = url_for('auth.login', _external=True)
        dashboard_url = url_for('dashboard.index', _external=True)
        logo_url = url_for('static', filename='img/logo-light.svg', _external=True)
        subject = '[TOOLLS] Код для входа в личный кабинет'
        display_name = user.display_name if hasattr(user, 'display_name') else (user.name or user.login)
        text_body = (
            f'Здравствуйте, {display_name}!\n\n'
            f'Код для входа в личный кабинет Toolls Music Distribution: {code}\n\n'
            f'Код действителен 10 минут. Никому не сообщайте его.\n\n'
            f'Страница входа: {login_url}\n'
        )
        html_body = render_template(
            'emails/login_code.html',
            code=code,
            author_name=display_name,
            login_url=login_url,
            dashboard_url=dashboard_url,
            logo_url=logo_url,
        )
        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=text_body,
            html=html_body,
            sender=sender,
        )
        mail.send(msg)
        logger.info('Отправлен код входа пользователю id=%s (%s)', user.id, to_email)
        return True, None
    except Exception as e:
        logger.exception('Ошибка отправки email с кодом входа: %s', e)
        # Чтобы ошибка была видна в консоли, даже если логи не настроены
        import sys
        print('[EMAIL] Ошибка отправки кода входа:', e, file=sys.stderr)
        err_msg = str(e)
        if not err_msg:
            err_msg = 'Ошибка SMTP (проверьте MAIL_SERVER, порт, логин и пароль в .env).'
        elif '535' in err_msg or 'authentication' in err_msg.lower() or 'Incorrect authentication' in err_msg:
            err_msg = (
                'Неверный логин или пароль SMTP. Проверьте MAIL_USERNAME и MAIL_PASSWORD в .env. '
                'Укажите полный email как логин (например noreply@ваш-домен.ru).'
            )
        return False, err_msg


def send_profile_update_code_email(user, code):
    """
    Отправить код подтверждения изменения профиля на текущий email пользователя.
    Возвращает (True, None) или (False, error_message).
    """
    if not user or not getattr(user, 'email', None):
        logger.warning('У пользователя (id=%s) нет email для кода изменения профиля', getattr(user, 'id', None))
        return False, 'В аккаунте не указан email.'
    if not current_app.config.get('MAIL_SERVER'):
        return False, 'Почта не настроена: в .env не задан MAIL_SERVER.'
    sender = _smtp_sender_email()
    if not sender:
        return False, 'Почта не настроена: не задан MAIL_USERNAME/MAIL_DEFAULT_SENDER.'
    try:
        profile_url = url_for('profile.edit', _external=True)
        subject = 'Код подтверждения изменения профиля'
        body = f"""Здравствуйте!

Код подтверждения изменения профиля: {code}

Код действует 10 минут.
Если это были не вы — проигнорируйте письмо.

Ссылка на профиль: {profile_url}

---
Личный кабинет Toolls Music Distribution
"""
        msg = Message(
            subject=subject,
            body=body,
            recipients=[user.email],
            sender=sender,
        )
        mail.send(msg)
        logger.info('Отправлен код подтверждения профиля пользователю id=%s', user.id)
        return True, None
    except Exception as e:
        logger.exception('Ошибка отправки кода изменения профиля: %s', e)
        return False, str(e) or 'Ошибка SMTP'


def _send_contract_email(contract, subject, body_plain):
    """Отправить письмо пользователю договора. contract должен иметь .user с .email."""
    if not contract or not getattr(contract, 'user', None) or not contract.user.email:
        logger.warning('У договора #%s нет пользователя с email для уведомления', getattr(contract, 'id', None))
        return False
    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен. Пропуск уведомления по договору #%s', contract.id)
        return False
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    if not sender:
        return False
    try:
        msg = Message(
            subject=subject,
            body=body_plain,
            recipients=[contract.user.email],
            sender=sender,
        )
        mail.send(msg)
        logger.info('Отправлено уведомление по договору #%s на %s', contract.id, contract.user.email)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки email по договору #%s: %s', contract.id, e)
        return False


def send_contract_uploaded_email(contract):
    """Уведомление пользователю: в ЛК загружен договор на подписание (название, срок)."""
    deadline = contract.deadline_formatted if hasattr(contract, 'deadline_formatted') else '-'
    body = f"""Здравствуйте!

В ваш личный кабинет загружен договор на подписание.

Название: {contract.title}
Срок подписания: {deadline}

Войдите в личный кабинет и скачайте договор. После подписания загрузите подписанный PDF.

—
Toolls Music Distribution
"""
    return _send_contract_email(contract, f'Договор «{contract.title}» — требуется подписание', body)


def send_contract_signing_code_email(contract, code):
    """Отправить одноразовый код электронной подписи договора."""
    body = f"""Здравствуйте, {contract.user.display_name}!

Код для подписания договора «{contract.title}»: {code}

Код действует 10 минут. Никому не сообщайте его.

Личный кабинет Toolls Music Distribution
"""
    return _send_contract_email(contract, f'Код подписания договора «{contract.title}»', body)


def send_contract_submitted_for_review_email(contract):
    """Уведомление пользователю: вы отправили договор на проверку, свяжемся в течение 3 рабочих дней."""
    body = f"""Здравствуйте!

Вы успешно отправили договор «{contract.title}» на проверку.

Мы свяжемся с вами в течение 3 рабочих дней.

—
Toolls Music Distribution
"""
    return _send_contract_email(contract, f'Договор «{contract.title}» отправлен на проверку', body)


def send_contract_approved_email(contract):
    """Уведомление пользователю: договор одобрен, можно загружать релизы."""
    body = f"""Здравствуйте!

Договор «{contract.title}» одобрен.

Вы можете загружать релизы в личном кабинете.

—
Toolls Music Distribution
"""
    return _send_contract_email(contract, f'Договор «{contract.title}» одобрен', body)


def send_contract_rejected_email(contract):
    """Уведомление пользователю: договор отклонён, указана причина."""
    reason = (contract.rejection_reason or 'Причина не указана.').strip()
    body = f"""Здравствуйте!

Договор «{contract.title}» отклонён.

Причина: {reason}

Пожалуйста, загрузите исправленный подписанный договор или свяжитесь с нами.

—
Toolls Music Distribution
"""
    return _send_contract_email(contract, f'Договор «{contract.title}» отклонён', body)


def is_email_configured():
    """Проверить, настроена ли почта (MAIL_SERVER)"""
    return bool(current_app.config.get('MAIL_SERVER'))


def send_test_email(recipient):
    """
    Отправить тестовое письмо. Для проверки настройки SMTP.
    Возвращает (success: bool, message: str).
    """
    if not is_email_configured():
        return False, 'MAIL_SERVER не задан в .env'
    if not recipient or '@' not in recipient:
        return False, 'Укажите корректный email'
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    if not sender:
        return False, 'MAIL_DEFAULT_SENDER не задан в .env'
    try:
        msg = Message(
            subject='[TOOLLS] Тест почты',
            body='Это тестовое письмо. Почта настроена корректно.',
            recipients=[recipient.strip()],
            sender=sender
        )
        mail.send(msg)
        logger.info('Тестовое письмо отправлено на %s', recipient)
        return True, 'Письмо отправлено'
    except Exception as e:
        logger.exception('Ошибка тестовой отправки: %s', e)
        return False, str(e)


def send_auto_form_request_email(request):
    """
    Отправить администратору email о новом запросе из автоматической формы.
    """
    recipients = get_ticket_executor_emails()
    if not recipients:
        logger.warning('Нет адресов для отправки уведомления о запросе #%s', request.id)
        return False

    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен (MAIL_SERVER). Пропуск отправки запроса #%s', request.id)
        return False

    try:
        author_name = request.user.display_name if request.user else 'Неизвестный'
        subject = f'[Автоформа] Новый запрос: {request.request_type_display}'

        # Формируем тело письма в зависимости от типа запроса
        body_parts = [
            f'Новый запрос из автоматической формы {request.display_id} (#{request.id})',
            f'Тип запроса: {request.request_type_display}',
            f'Автор: {author_name}',
            f'Email: {request.user.email if request.user else "Не указан"}',
            ''
        ]

        if request.request_type == 'transfer_release':
            if request.release:
                body_parts.append(f'Релиз: {request.release.title}')
            if request.platform:
                platform_names = {
                    'vk': 'ВК',
                    'spotify': 'Spotify',
                    'yandex': 'Яндекс Музыка',
                    'other': 'Другое'
                }
                body_parts.append(f'Площадка: {platform_names.get(request.platform, request.platform)}')
            if request.wrong_card_url:
                body_parts.append(f'Ссылка на неправильную карточку: {request.wrong_card_url}')
            if request.correct_card_url:
                body_parts.append(f'Ссылка на правильную карточку: {request.correct_card_url}')

        elif request.request_type == 'youtube_note':
            if request.channel_url:
                body_parts.append(f'Ссылка на канал: {request.channel_url}')
            if request.topic_urls:
                body_parts.append(f'Ссылки на темы (Topic):\n{request.topic_urls}')

        elif request.request_type == 'vk_restore':
            if request.previous_distributor:
                body_parts.append(f'Прошлый дистрибьютор: {request.previous_distributor}')
            if request.upc_codes:
                body_parts.append(f'UPC-коды:\n{request.upc_codes}')

        body_parts.extend([
            '',
            '---',
            'Личный кабинет Toolls Music Distribution'
        ])

        body = '\n'.join(body_parts)

        msg = Message(
            subject=subject,
            body=body,
            recipients=recipients,
            sender=current_app.config.get('MAIL_DEFAULT_SENDER')
        )
        mail.send(msg)
        logger.info('Отправлено уведомление о запросе #%s на %s', request.id, recipients)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки email о запросе #%s: %s', request.id, e)
        return False


def send_auto_form_user_confirmation_email(req, days=7, kind=None):
    """
    Отправить пользователю подтверждение приёма заявки автоформы.
    kind: transfer_release -> «принята заявка на перенос», срок до 7 дней;
    youtube_note -> «принята заявка на получение Нотки на YouTube», срок до 14 дней;
    vk_restore -> «принята заявка», срок до 14 дней.
    """
    if not req.user or not getattr(req.user, 'email', None) or not req.user.email:
        logger.warning('У пользователя запроса #%s нет email', req.id)
        return False
    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен. Пропуск подтверждения запроса #%s', req.id)
        return False
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    if not sender:
        return False
    kind = kind or req.request_type
    if kind == 'transfer_release':
        subject = f'[TOOLLS] Принята заявка на перенос релиза ({req.display_id})'
        body_text = (
            f'Здравствуйте!\n\n'
            f'Ваша заявка {req.display_id} на перенос релиза в другую карточку принята.\n'
            f'Примерный срок обработки: до {days} дней.\n\n'
            '---\nЛичный кабинет Toolls Music Distribution'
        )
    elif kind == 'youtube_note':
        subject = f'[TOOLLS] Принята заявка на получение «Нотки» на YouTube ({req.display_id})'
        body_text = (
            f'Здравствуйте!\n\n'
            f'Ваша заявка {req.display_id} на получение «Нотки» на YouTube-канал принята.\n'
            f'Примерный срок: до {days} дней.\n\n'
            '---\nЛичный кабинет Toolls Music Distribution'
        )
    elif kind == 'vk_restore':
        subject = f'[TOOLLS] Принята заявка на восстановление в VK ({req.display_id})'
        body_text = (
            f'Здравствуйте!\n\n'
            f'Ваша заявка {req.display_id} на восстановление прослушиваний/плейлиста в VK принята.\n'
            f'Примерный срок: до {days} дней.\n\n'
            '---\nЛичный кабинет Toolls Music Distribution'
        )
    else:
        subject = f'[TOOLLS] Заявка принята ({req.display_id})'
        body_text = f'Ваша заявка {req.display_id} принята. Срок до {days} дней.\n\n---\nToolls Music Distribution'

    try:
        msg = Message(
            subject=subject,
            body=body_text,
            recipients=[req.user.email],
            sender=sender
        )
        mail.send(msg)
        logger.info('Отправлено подтверждение заявки #%s на %s', req.id, req.user.email)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки подтверждения заявки #%s: %s', req.id, e)
        return False


def send_auto_form_reply_to_user(req, message_text):
    """Отправить пользователю email об ответе админа по заявке автоформы (как в чате)."""
    if not req.user or not getattr(req.user, 'email', None) or not req.user.email:
        logger.warning('У пользователя запроса #%s нет email', req.id)
        return False
    if not current_app.config.get('MAIL_SERVER'):
        return False
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    if not sender:
        return False
    try:
        admin_requests_url = url_for('tools.auto_form_requests_admin', _external=True)
        subject = f'[{req.display_id}] Новый ответ по вашей заявке'
        preview = (message_text[:300] + '...') if len(message_text) > 300 else message_text
        body = (
            f'Здравствуйте!\n\n'
            f'По вашей заявке {req.display_id} ({req.request_type_display}) поступил новый ответ от поддержки.\n\n'
            f'Ответ:\n{preview}\n\n'
            f'Обратитесь в личный кабинет для просмотра переписки.\n'
            f'---\nЛичный кабинет Toolls Music Distribution'
        )
        msg = Message(
            subject=subject,
            body=body,
            recipients=[req.user.email],
            sender=sender
        )
        mail.send(msg)
        logger.info('Отправлено уведомление об ответе по заявке #%s на %s', req.id, req.user.email)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки уведомления об ответе #%s: %s', req.id, e)
        return False


def send_auto_form_user_reply_to_admin(req, message_text):
    """Уведомить админов о том, что пользователь написал сообщение в заявке автоформы."""
    recipients = get_ticket_executor_emails()
    if not recipients:
        logger.warning('Нет адресов для уведомления о сообщении пользователя в заявке #%s', req.id)
        return False
    if not current_app.config.get('MAIL_SERVER'):
        return False
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    if not sender:
        return False
    try:
        detail_url = url_for('tools.auto_form_request_detail', id=req.id, _external=True)
        author_name = req.user.display_name if req.user else 'Пользователь'
        subject = f'[Автоформа] Ответ пользователя в заявке {req.display_id}'
        preview = (message_text[:400] + '...') if len(message_text) > 400 else message_text
        body = (
            f'Пользователь ответил в заявке {req.display_id} ({req.request_type_display}).\n\n'
            f'Автор: {author_name}\n'
            f'Email: {getattr(req.user, "email", "") or "—"}\n\n'
            f'Сообщение:\n{preview}\n\n'
            f'Открыть заявку: {detail_url}\n'
            f'---\nЛичный кабинет Toolls Music Distribution'
        )
        msg = Message(
            subject=subject,
            body=body,
            recipients=recipients,
            sender=sender
        )
        mail.send(msg)
        logger.info('Отправлено уведомление админам о сообщении пользователя в заявке #%s', req.id)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки уведомления админам о сообщении пользователя #%s: %s', req.id, e)
        return False


def _get_release_owner_email(release):
    """Получить email владельца релиза (напрямую по user_id, чтобы не зависеть от lazy load после commit)."""
    from app.models.user import User
    user = User.query.get(release.user_id)
    return user.email if user else None


def _send_release_email(release, subject, template_name, **template_vars):
    """
    Общая отправка письма артисту по релизу.
    Письмо уходит на email из профиля владельца релиза.
    Как у тикетов: только body (без html) для совместимости со SMTP.
    """
    recipient_email = _get_release_owner_email(release)
    if not recipient_email or not recipient_email.strip():
        logger.warning('У владельца релиза #%s (user_id=%s) нет email', release.id, release.user_id)
        return False
    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен (MAIL_SERVER). Пропуск отправки релиза #%s', release.id)
        return False
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    if not sender:
        logger.warning('MAIL_DEFAULT_SENDER не задан')
        return False
    try:
        release_url = url_for('releases.view', id=release.id, _external=True)
        dashboard_url = url_for('dashboard.index', _external=True)
        logo_url = url_for('static', filename='img/logo-light.svg', _external=True)
        template_vars.setdefault('release_url', release_url)
        template_vars.setdefault('dashboard_url', dashboard_url)
        template_vars.setdefault('logo_url', logo_url)
        template_vars.setdefault('release_title', release.title)
        template_vars.setdefault('artist_name', release.owner.name if release.owner else None)
        html_body = render_template(f'emails/{template_name}', **template_vars)
        # Текстовая версия для клиентов без HTML
        if template_name == 'release_submitted.html':
            body = f"""Релиз «{release.title}» отправлен на модерацию.
Ориентировочный срок проверки — 2–3 дня. Мы уведомим вас о результате на эту почту.

Ссылка на релиз: {release_url}

---
Личный кабинет Toolls Music Distribution"""
        elif template_name == 'release_approved.html':
            body = f"""Релиз одобрен! Трек отправлен на платформы (Spotify, Apple Music, Яндекс Музыка, VK Music и др.).

Релиз: «{release.title}»

Ссылка: {release_url}

---
Личный кабинет Toolls Music Distribution"""
        elif template_name == 'release_rejected.html':
            reason = template_vars.get('rejection_reason', 'Не указана.')
            body = f"""Релиз «{release.title}» отклонён.

Причина: {reason}

Вы можете внести правки и снова отправить релиз на проверку.

Ссылка: {release_url}

---
Личный кабинет Toolls Music Distribution"""
        elif template_name == 'release_revoked.html':
            reason = template_vars.get('rejection_reason', 'Не указана.')
            body = f"""Релиз «{release.title}» отозван администратором.

Причина: {reason}

Подробности доступны в карточке релиза в личном кабинете.

Ссылка: {release_url}

---
Личный кабинет Toolls Music Distribution"""
        else:
            body = f"{subject}\n\nРелиз: {release.title}\nСсылка: {release_url}\n\n---\nЛичный кабинет Toolls Music Distribution"
        msg = Message(
            subject=subject,
            body=body,
            html=html_body,
            recipients=[recipient_email.strip()],
            sender=sender
        )
        mail.send(msg)
        logger.info('Отправлено письмо по релизу #%s (%s) на %s', release.id, template_name, recipient_email)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки email по релизу #%s (%s): %s', release.id, template_name, e)
        return False


def send_release_submitted_email(release):
    """
    Письмо артисту: релиз отправлен на модерацию.
    В письме — что он указал (название релиза и треков) и срок проверки 2–3 дня.
    """
    from app.models.release import Track
    track_titles = [t.display_title for t in release.tracks.order_by(Track.track_order).all()]
    return _send_release_email(
        release,
        subject=f'Релиз «{release.title}» отправлен на модерацию',
        template_name='release_submitted.html',
        track_titles=track_titles
    )


def send_release_approved_email(release):
    """Письмо артисту: релиз одобрен, трек отправлен на платформы."""
    return _send_release_email(
        release,
        subject=f'Релиз «{release.title}» одобрен!',
        template_name='release_approved.html'
    )


def send_release_rejected_email(release):
    """Письмо артисту: релиз отклонён, с причиной из moderator_comment."""
    reason = (release.moderator_comment or 'Не указана.').strip()
    return _send_release_email(
        release,
        subject=f'Релиз «{release.title}» отклонён',
        template_name='release_rejected.html',
        rejection_reason=reason
    )


def send_release_revoked_email(release):
    """Письмо артисту: релиз отозван администратором, с причиной."""
    reason = (release.moderator_comment or 'Не указана.').strip()
    return _send_release_email(
        release,
        subject=f'Релиз «{release.title}» отозван администратором',
        template_name='release_revoked.html',
        rejection_reason=reason,
    )


def _send_billing_email(recipient_email, subject, body, html_body=None):
    if not recipient_email:
        return False
    if not current_app.config.get('MAIL_SERVER'):
        logger.warning('Email не настроен (MAIL_SERVER). Пропуск: %s', subject)
        return False
    sender = _smtp_sender_email()
    if not sender:
        logger.warning('Не задан отправитель. Пропуск: %s', subject)
        return False
    try:
        msg = Message(
            subject=subject,
            body=body,
            html=html_body,
            recipients=[recipient_email],
            sender=sender,
        )
        mail.send(msg)
        return True
    except Exception as e:
        logger.exception('Ошибка отправки billing email: %s', e)
        return False


def send_invoice_created_email(invoice):
    """Уведомление пользователю о новом счёте."""
    user = invoice.user
    if not user or not user.email:
        return False
    invoices_url = url_for('documents.hub_invoices', _external=True)
    dashboard_url = url_for('dashboard.index', _external=True)
    due = invoice.due_date.strftime('%d.%m.%Y') if invoice.due_date else 'не указан'
    pay_line = ''
    if invoice.payment_link:
        pay_line = f'\nОплатить: {invoice.payment_link}\n'
    body = f"""Здравствуйте, {user.display_name}!

Вам выставлен новый счёт {invoice.invoice_number}.

Тема: {invoice.subject}
Сумма: {invoice.amount} {invoice.currency}
Срок оплаты: {due}
{pay_line}
Раздел «Финансы → Счета»: {invoices_url}

---
Личный кабинет Toolls Music Distribution
"""
    html_body = render_template(
        'emails/invoice_created.html',
        dashboard_url=dashboard_url,
        invoices_url=invoices_url,
        payment_url=invoice.payment_link or '',
        invoice_number=invoice.invoice_number,
        subject=invoice.subject or '—',
        amount=invoice.amount,
        currency=invoice.currency,
        due_date=due,
        author_name=user.display_name,
    )
    return _send_billing_email(
        user.email,
        f'Новый счёт {invoice.invoice_number}',
        body,
        html_body=html_body,
    )


def send_invoice_overdue_email(invoice):
    """Просрочка счёта — приостановка выгрузки релизов."""
    user = invoice.user
    if not user or not user.email:
        return False
    invoices_url = url_for('documents.hub_invoices', _external=True)
    dashboard_url = url_for('dashboard.index', _external=True)
    body = f"""Здравствуйте, {user.display_name}!

Срок оплаты счёта {invoice.invoice_number} истёк.
Выгрузка новых релизов приостановлена до оплаты подписки.

Сумма: {invoice.amount} {invoice.currency}
Оплатить счёт: {invoices_url}

После оплаты доступ к выгрузке будет восстановлен автоматически.

---
Личный кабинет Toolls Music Distribution
"""
    html_body = render_template(
        'emails/invoice_overdue.html',
        dashboard_url=dashboard_url,
        invoices_url=invoices_url,
        invoice_number=invoice.invoice_number,
        amount=invoice.amount,
        currency=invoice.currency,
        author_name=user.display_name,
    )
    return _send_billing_email(
        user.email,
        f'Приостановка выгрузки — счёт {invoice.invoice_number} просрочен',
        body,
        html_body=html_body,
    )


def send_subscription_reminder_email(user):
    """Напоминание за 7 дней до окончания подписки."""
    if not user or not user.email:
        return False
    if not user.subscription_expires_at:
        return False
    expires = user.subscription_expires_at.strftime('%d.%m.%Y')
    invoices_url = url_for('documents.hub_invoices', _external=True)
    dashboard_url = url_for('dashboard.index', _external=True)
    plan = user.subscription_plan or 'Подписка'
    body = f"""Здравствуйте, {user.display_name}!

Напоминаем: подписка «{plan}» действует до {expires} (осталось около 7 дней).

Чтобы не прерывать выгрузку релизов, оплатите продление в разделе «Финансы → Счета»:
{invoices_url}

---
Личный кабинет Toolls Music Distribution
"""
    html_body = render_template(
        'emails/subscription_reminder.html',
        dashboard_url=dashboard_url,
        invoices_url=invoices_url,
        plan=plan,
        expires=expires,
        author_name=user.display_name,
    )
    return _send_billing_email(
        user.email,
        f'Напоминание: подписка «{plan}» заканчивается {expires}',
        body,
        html_body=html_body,
    )
