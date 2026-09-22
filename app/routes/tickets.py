"""
Тикеты поддержки
"""

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from sqlalchemy.orm import joinedload
from flask_login import login_required, current_user
from app import db
from app.models.ticket import Ticket, TicketMessage, Attachment
from app.models.notification import Notification
from app.models.user import User
from app.utils.decorators import admin_required
from app.utils.files import save_file, allowed_file
from app.services.ticket_service import (
    ACTIVE_STATUSES,
    add_message,
    close_ticket,
    create_admin_ticket,
)
from app.services.manager_chat_unread import (
    is_message_read_by_peer,
    mark_chat_viewed,
    outgoing_read_map,
    unread_from_user_count,
)

tickets_bp = Blueprint('tickets', __name__)
MANAGER_CHAT_PREFIX = '[MANAGER_CHAT]'
VOICE_MESSAGE_TEXT = 'Голосовое сообщение'
DEFAULT_MANAGER_SCHEDULE = 'Пн–Пт 9:00–18:00 (МСК)'

OUTAGE_SECTION_LABELS = {
    'cabinet': 'Кабинет в целом',
    'releases': 'Релизы',
    'stats': 'Аналитика',
    'finance': 'Финансы',
    'uploads': 'Загрузка файлов',
    'auth': 'Вход и авторизация',
    'other': 'Другое',
}


def _outage_section_label(key):
    return OUTAGE_SECTION_LABELS.get(key, OUTAGE_SECTION_LABELS['other'])


def _manager_chat_base_query():
    return Ticket.query.filter(Ticket.subject.like(f'{MANAGER_CHAT_PREFIX}%'))


def _is_manager_chat_ticket(ticket):
    return bool(ticket and ticket.subject and ticket.subject.startswith(MANAGER_CHAT_PREFIX))


def _manager_chat_enabled():
    return current_app.config.get('MANAGER_CHAT_ENABLED', False)


def _manager_chat_or_support_redirect(ticket):
    if _manager_chat_enabled():
        return redirect(url_for('tickets.manager_chat_index', ticket_id=ticket.id))
    return redirect(url_for('tickets.index'))


def _manager_schedule_from_ticket(ticket):
    if not ticket or not ticket.message:
        return DEFAULT_MANAGER_SCHEDULE
    for line in ticket.message.splitlines():
        line = line.strip()
        if line.lower().startswith('график работы:'):
            value = line.split(':', 1)[1].strip() if ':' in line else ''
            return value or DEFAULT_MANAGER_SCHEDULE
    return DEFAULT_MANAGER_SCHEDULE


def _ticket_counts_for_user(user):
    """Счётчики: всё / активные (не закрытые) / закрытые."""
    if user.is_admin:
        base = Ticket.query.filter(~Ticket.subject.like(f'{MANAGER_CHAT_PREFIX}%'))
    else:
        base = Ticket.query.filter_by(user_id=user.id).filter(
            ~Ticket.subject.like(f'{MANAGER_CHAT_PREFIX}%')
        )
    return {
        'all': base.count(),
        'open': base.filter(Ticket.status.in_(ACTIVE_STATUSES)).count(),
        'closed': base.filter_by(status='closed').count(),
    }


def _get_tickets_sidebar(user, status=''):
    """Тикеты для левой панели (последние 50)."""
    if user.is_admin:
        query = Ticket.query.filter(~Ticket.subject.like(f'{MANAGER_CHAT_PREFIX}%'))
    else:
        query = Ticket.query.filter_by(user_id=user.id).filter(
            ~Ticket.subject.like(f'{MANAGER_CHAT_PREFIX}%')
        )
    if status == 'closed':
        query = query.filter_by(status='closed')
    elif status == 'open':
        query = query.filter(Ticket.status.in_(ACTIVE_STATUSES))
    query = query.order_by(Ticket.updated_at.desc()).limit(50)
    if user.is_admin:
        query = query.options(
            joinedload(Ticket.user),
            joinedload(Ticket.creator_admin),
        )
    return query.all()


def _has_uploaded_files(files):
    return bool(files and any(f and getattr(f, 'filename', None) for f in files))


def _process_ticket_attachments(files, ticket_message_id):
    """Обработка загруженных файлов для сообщения тикета.
    
    Args:
        files: список FileStorage объектов (request.files.getlist('attachments'))
        ticket_message_id: ID сообщения, к которому прикрепляем файлы
    
    Returns:
        список созданных объектов Attachment
    """
    if not files or not any(f.filename for f in files):
        return []
    
    allowed_extensions = current_app.config.get('ALLOWED_TICKET_ATTACHMENT_EXTENSIONS', set())
    max_size = current_app.config.get('MAX_TICKET_ATTACHMENT_SIZE', 10 * 1024 * 1024)
    subfolder = 'ticket_attachments'
    
    attachments = []
    for file in files:
        if not file.filename:
            continue
        
        # Проверка расширения
        if not allowed_file(file.filename, allowed_extensions):
            current_app.logger.warning(
                f'Недопустимое расширение файла {file.filename} для вложения тикета'
            )
            continue
        
        # Проверка размера (через request.content_length? но file.stream)
        # Сохраняем файл, save_file вернёт уникальное имя
        stored_filename = save_file(file, subfolder)
        if not stored_filename:
            continue
        
        # Получаем размер файла
        file.seek(0, 2)  # перейти в конец
        file_size = file.tell()
        file.seek(0)  # вернуться в начало
        
        # Создаём запись Attachment
        attachment = Attachment(
            ticket_message_id=ticket_message_id,
            filename=file.filename,
            stored_filename=stored_filename,
            file_size=file_size,
            mime_type=file.content_type,
        )
        db.session.add(attachment)
        attachments.append(attachment)
    
    if attachments:
        db.session.commit()
    
    return attachments


@tickets_bp.route('/tickets')
@login_required
def index():
    """Поддержка: левая панель — архив, правая — выбор обращения"""
    status = request.args.get('status', '')
    tickets_list = _get_tickets_sidebar(current_user, status)
    counts = _ticket_counts_for_user(current_user)
    return render_template(
        'tickets/inbox.html',
        tickets_list=tickets_list,
        selected_ticket=None,
        messages=[],
        status=status,
        counts=counts,
    )


@tickets_bp.route('/manager-chat')
@login_required
def manager_chat_index():
    if not _manager_chat_enabled():
        return redirect(url_for('dashboard.index'))
    ticket_id = request.args.get('ticket_id', type=int)
    if current_user.is_admin:
        chats = _manager_chat_base_query().order_by(Ticket.updated_at.desc()).all()
    else:
        chats = (
            _manager_chat_base_query()
            .filter_by(user_id=current_user.id)
            .order_by(Ticket.updated_at.desc())
            .all()
        )

    selected_chat = None
    if ticket_id:
        selected_chat = next((t for t in chats if t.id == ticket_id), None)
    if not selected_chat and chats:
        selected_chat = chats[0]

    chat_messages = []
    if selected_chat:
        chat_messages = selected_chat.messages.order_by(TicketMessage.created_at.asc()).all()

    users_list = []
    managers_list = []
    if current_user.is_admin:
        users_list = (
            User.query.filter(User.is_active.is_(True), User.role != 'admin')
            .order_by(User.name.asc())
            .all()
        )
        managers_list = (
            User.query.filter(User.is_active.is_(True), User.role == 'admin')
            .order_by(User.name.asc())
            .all()
        )

    manager_name = ''
    manager_schedule = DEFAULT_MANAGER_SCHEDULE
    if selected_chat:
        manager_name = (
            selected_chat.creator_admin.display_name
            if selected_chat.creator_admin
            else 'Не назначен'
        )
        manager_schedule = _manager_schedule_from_ticket(selected_chat)
        mark_chat_viewed(selected_chat, current_user)
        db.session.commit()
        db.session.refresh(selected_chat)

    manager_chat_list_unread = {}
    if current_user.is_admin and chats:
        for c in chats:
            if c.created_by_admin_id == current_user.id:
                manager_chat_list_unread[c.id] = unread_from_user_count(c)
            else:
                manager_chat_list_unread[c.id] = 0

    return render_template(
        'tickets/manager_chat.html',
        chats=chats,
        selected_chat=selected_chat,
        chat_messages=chat_messages,
        users_list=users_list,
        managers_list=managers_list,
        manager_name=manager_name,
        manager_schedule=manager_schedule,
        manager_chat_list_unread=manager_chat_list_unread,
        voice_message_text=VOICE_MESSAGE_TEXT,
        is_message_read_by_peer=is_message_read_by_peer,
    )


@tickets_bp.route('/manager-chat/assign', methods=['POST'])
@login_required
@admin_required
def manager_chat_assign():
    if not _manager_chat_enabled():
        return redirect(url_for('dashboard.index'))
    try:
        user_id = int(request.form.get('user_id', '0'))
        manager_id = int(request.form.get('manager_id', '0'))
    except (TypeError, ValueError):
        user_id = 0
        manager_id = 0
    schedule = request.form.get('schedule', '').strip() or DEFAULT_MANAGER_SCHEDULE

    target_user = User.query.filter_by(id=user_id, is_active=True).first()
    manager = User.query.filter_by(id=manager_id, is_active=True, role='admin').first()
    if not target_user or target_user.is_admin or not manager:
        flash('Проверьте пользователя и назначенного менеджера', 'error')
        return redirect(url_for('tickets.manager_chat_index'))

    subject = f'{MANAGER_CHAT_PREFIX} Чат с персональным менеджером'
    initial_message = (
        f'Персональный менеджер назначен: {manager.display_name}\n'
        f'График работы: {schedule}'
    )
    chat = (
        _manager_chat_base_query()
        .filter_by(user_id=target_user.id)
        .order_by(Ticket.updated_at.desc())
        .first()
    )

    if chat:
        chat.created_by_admin_id = manager.id
        chat.message = initial_message
        chat.status = 'waiting_for_user'
        chat.updated_at = datetime.utcnow()
        db.session.commit()

        assignment_message = add_message(
            chat.id,
            manager.id,
            f'Здравствуйте! Я ваш персональный менеджер.\nГрафик работы: {schedule}',
            True,
        )
        files = request.files.getlist('attachments')
        if files and any(f.filename for f in files):
            _process_ticket_attachments(files, assignment_message.id)
    else:
        chat = Ticket(
            user_id=target_user.id,
            created_by_admin_id=manager.id,
            subject=subject,
            message=initial_message,
            status='waiting_for_user',
            initiator='admin',
        )
        db.session.add(chat)
        db.session.commit()

        first_message = TicketMessage(
            ticket_id=chat.id,
            user_id=manager.id,
            message=f'Здравствуйте! Я ваш персональный менеджер.\nГрафик работы: {schedule}',
            is_admin=True,
        )
        db.session.add(first_message)
        db.session.commit()

    db.session.add(
        Notification(
            user_id=target_user.id,
            kind='ticket_admin_initiated',
            title='Назначен персональный менеджер',
            message=f'Для вас открыт персональный чат с менеджером {manager.display_name}.',
            ticket_id=chat.id,
        )
    )
    db.session.commit()
    flash('Персональный менеджер назначен', 'success')
    return redirect(url_for('tickets.manager_chat_index', ticket_id=chat.id))


@tickets_bp.route('/manager-chat/<int:id>/sync')
@login_required
def manager_chat_sync(id):
    """
    Живой чат:
    - отмечает просмотр;
    - отдаёт галочки прочтения;
    - при новых сообщениях отдаёт HTML переписки (без перезагрузки страницы).
    """
    if not _manager_chat_enabled():
        return jsonify({'ok': False, 'error': 'disabled'}), 404
    chat = Ticket.query.get_or_404(id)
    if not _is_manager_chat_ticket(chat):
        return jsonify({'ok': False, 'error': 'not_found'}), 404

    if not current_user.is_admin and chat.user_id != current_user.id:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    client_last_id = request.args.get('last_id', type=int) or 0
    client_count = request.args.get('count', type=int) or 0

    mark_chat_viewed(chat, current_user)
    try:
        db.session.commit()
        db.session.refresh(chat)
    except Exception:
        db.session.rollback()
        return jsonify({'ok': False, 'error': 'db'}), 500

    chat_messages = chat.messages.order_by(TicketMessage.created_at.asc(), TicketMessage.id.asc()).all()
    messages_count = len(chat_messages)
    last_msg = chat_messages[-1] if chat_messages else None
    last_message_id = last_msg.id if last_msg else 0

    reads = outgoing_read_map(chat, current_user.is_admin)
    reads_json = {str(k): bool(v) for k, v in reads.items()}

    payload = {
        'ok': True,
        'reads': reads_json,
        'last_message_id': last_message_id,
        'messages_count': messages_count,
        'html': None,
    }

    # HTML только если реально появились новые сообщения (строго больше)
    if last_message_id > client_last_id or messages_count > client_count:
        payload['html'] = render_template(
            'tickets/partials/_manager_chat_messages.html',
            selected_chat=chat,
            chat_messages=chat_messages,
            voice_message_text=VOICE_MESSAGE_TEXT,
            is_message_read_by_peer=is_message_read_by_peer,
        )

    return jsonify(payload)


@tickets_bp.route('/manager-chat/<int:id>/reply', methods=['POST'])
@login_required
def manager_chat_reply(id):
    if not _manager_chat_enabled():
        return redirect(url_for('dashboard.index'))
    chat = Ticket.query.get_or_404(id)
    if not _is_manager_chat_ticket(chat):
        flash('Чат не найден', 'error')
        return redirect(url_for('tickets.manager_chat_index'))

    if not current_user.is_admin and chat.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('tickets.manager_chat_index'))

    message_text = request.form.get('message', '').strip()
    files = request.files.getlist('attachments')
    has_files = _has_uploaded_files(files)

    if not message_text and not has_files:
        flash('Напишите сообщение или прикрепите файл', 'error')
        return redirect(url_for('tickets.manager_chat_index', ticket_id=chat.id))

    is_voice = request.form.get('voice_message') == '1'
    if not message_text and has_files:
        message_text = VOICE_MESSAGE_TEXT if is_voice else 'Вложение'

    new_message = add_message(
        chat.id,
        current_user.id,
        message_text,
        current_user.is_admin,
    )
    attachments = []
    if has_files:
        attachments = _process_ticket_attachments(files, new_message.id)

    if message_text == VOICE_MESSAGE_TEXT and not attachments:
        db.session.delete(new_message)
        db.session.commit()
        flash('Не удалось сохранить голосовое сообщение. Проверьте формат и размер файла (до 10 МБ).', 'error')
        return redirect(url_for('tickets.manager_chat_index', ticket_id=chat.id))

    if current_user.is_admin:
        db.session.add(
            Notification(
                user_id=chat.user_id,
                kind='ticket_reply',
                title='Новое сообщение от персонального менеджера',
                message='В персональном чате есть новый ответ.',
                ticket_id=chat.id,
            )
        )
        db.session.commit()
    flash('Сообщение отправлено', 'success')
    return redirect(url_for('tickets.manager_chat_index', ticket_id=chat.id))


@tickets_bp.route('/tickets/admin/write', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_write():
    """Инициация переписки от администратора к пользователю."""
    users_list = (
        User.query.filter(User.is_active.is_(True), User.role != 'admin')
        .order_by(User.name.asc())
        .all()
    )
    if request.method == 'POST':
        try:
            user_id = int(request.form.get('user_id', '0'))
        except (TypeError, ValueError):
            user_id = 0
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        if not user_id or not subject or not message:
            flash('Выберите пользователя и заполните тему и сообщение', 'error')
            return render_template(
                'tickets/admin_write.html',
                users_list=users_list,
            )
        target = User.query.filter_by(id=user_id, is_active=True).first()
        if not target or target.is_admin:
            flash('Пользователь не найден или недоступен', 'error')
            return render_template(
                'tickets/admin_write.html',
                users_list=users_list,
            )
        ticket = create_admin_ticket(
            current_user.id,
            user_id,
            subject,
            message,
        )
        flash('Обращение создано: %s' % ticket.display_id, 'success')
        return redirect(url_for('tickets.view', id=ticket.id))

    return render_template('tickets/admin_write.html', users_list=users_list)


@tickets_bp.route('/tickets/tech-outage', methods=['GET', 'POST'])
@login_required
def tech_outage():
    """Сообщение о технической накладке — приватный тикет в поддержку."""
    if request.method == 'POST':
        section_key = request.form.get('section', 'cabinet').strip().lower()
        if section_key not in OUTAGE_SECTION_LABELS:
            section_key = 'other'
        message = request.form.get('message', '').strip()

        if not message or len(message) < 10:
            flash('Опишите проблему подробнее (не менее 10 символов)', 'error')
            return render_template(
                'tickets/tech_outage.html',
                sections=OUTAGE_SECTION_LABELS,
                form_section=section_key,
                form_message=message,
            )

        section_label = _outage_section_label(section_key)
        subject = f'[Тех. накладка] {section_label}'
        ticket_body = (
            f'Раздел: {section_label}\n\n'
            f'Описание проблемы:\n{message}'
        )

        ticket = Ticket(
            user_id=current_user.id,
            subject=subject,
            message=ticket_body,
            status='waiting_for_admin',
            initiator='user',
            priority='high',
        )
        db.session.add(ticket)
        db.session.commit()

        first_message = TicketMessage(
            ticket_id=ticket.id,
            user_id=current_user.id,
            message=ticket_body,
            is_admin=False,
        )
        db.session.add(first_message)

        notif = Notification(
            user_id=current_user.id,
            kind='ticket_created',
            title='Обращение о тех. накладке принято',
            message=f'Ваше сообщение «{subject}» передано в поддержку.',
            ticket_id=ticket.id,
        )
        db.session.add(notif)
        db.session.commit()

        from app.utils.email import send_ticket_accepted_email, send_ticket_confirmation_to_author

        try:
            send_ticket_accepted_email(ticket)
        except Exception as e:
            current_app.logger.warning('Ошибка отправки тикета исполнителям: %s', e)
        try:
            send_ticket_confirmation_to_author(ticket)
        except Exception as e:
            current_app.logger.warning('Ошибка отправки подтверждения автору: %s', e)

        from app.services.ticket_service import notify_ticket_created_telegram

        notify_ticket_created_telegram(ticket)

        flash('Обращение о тех. накладке принято. Поддержка ответит в ближайшее время.', 'success')
        return redirect(url_for('tickets.view', id=ticket.id))

    return render_template(
        'tickets/tech_outage.html',
        sections=OUTAGE_SECTION_LABELS,
        form_section='cabinet',
        form_message='',
    )


@tickets_bp.route('/tickets/create', methods=['GET', 'POST'])
@login_required
def create():
    """Создание тикета"""
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        category = request.form.get('category', 'general').strip()
        if category not in {
            'general', 'finance', 'releases', 'uploads', 'auth', 'other'
        }:
            category = 'general'

        if not subject or not message:
            flash('Заполните все обязательные поля', 'error')
            return render_template(
                'tickets/create.html',
                ticket_categories={
                    'general': 'Общие вопросы',
                    'finance': 'Финансы',
                    'releases': 'Релизы',
                    'uploads': 'Загрузка файлов',
                    'auth': 'Вход и авторизация',
                    'other': 'Другое',
                },
                category=category,
            )

        ticket = Ticket(
            user_id=current_user.id,
            subject=subject,
            message=message,
            category=category,
            status='waiting_for_admin',
            initiator='user',
        )

        db.session.add(ticket)
        db.session.commit()

        # Создаём первое сообщение (от пользователя)
        first_message = TicketMessage(
            ticket_id=ticket.id,
            user_id=current_user.id,
            message=message,
            is_admin=False,
        )
        db.session.add(first_message)
        db.session.commit()

        # Обработка вложений, если есть
        files = request.files.getlist('attachments')
        if files and any(f.filename for f in files):
            _process_ticket_attachments(files, first_message.id)

        notif = Notification(
            user_id=current_user.id,
            kind='ticket_created',
            title='Тикет создан',
            message=f'Ваш тикет «{ticket.subject}» успешно создан.',
            ticket_id=ticket.id,
        )
        db.session.add(notif)
        db.session.commit()

        from app.utils.email import send_ticket_accepted_email, send_ticket_confirmation_to_author

        try:
            send_ticket_accepted_email(ticket)
        except Exception as e:
            current_app.logger.warning('Ошибка отправки тикета исполнителям: %s', e)
        author_email_ok = False
        try:
            author_email_ok = send_ticket_confirmation_to_author(ticket)
        except Exception as e:
            current_app.logger.warning('Ошибка отправки подтверждения автору: %s', e)

        from app.services.ticket_service import notify_ticket_created_telegram

        notify_ticket_created_telegram(ticket)

        flash('Тикет %s создан' % ticket.display_id, 'success')
        if not author_email_ok:
            flash(
                'Подтверждение на почту не отправлено. Проверьте email в профиле и настройки SMTP в .env',
                'warning',
            )
        return redirect(url_for('tickets.view', id=ticket.id))

    return render_template(
        'tickets/create.html',
        ticket_categories={
            'general': 'Общие вопросы',
            'finance': 'Финансы',
            'releases': 'Релизы',
            'uploads': 'Загрузка файлов',
            'auth': 'Вход и авторизация',
            'other': 'Другое',
        },
    )


@tickets_bp.route('/tickets/<int:id>')
@login_required
def view(id):
    """Просмотр тикета: левая панель — архив, правая — чат"""
    ticket = Ticket.query.options(
        joinedload(Ticket.user),
        joinedload(Ticket.creator_admin),
    ).get_or_404(id)
    if _is_manager_chat_ticket(ticket):
        return _manager_chat_or_support_redirect(ticket)

    if not current_user.is_admin and ticket.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('tickets.index'))

    Notification.query.filter_by(
        user_id=current_user.id, ticket_id=ticket.id, is_read=False
    ).update({'is_read': True})
    db.session.commit()

    status = request.args.get('status', '')
    messages = ticket.messages.order_by(TicketMessage.created_at).all()
    tickets_list = _get_tickets_sidebar(current_user, status)
    counts = _ticket_counts_for_user(current_user)

    return render_template(
        'tickets/inbox.html',
        tickets_list=tickets_list,
        selected_ticket=ticket,
        messages=messages,
        status=status,
        counts=counts,
    )


@tickets_bp.route('/tickets/<int:id>/reply', methods=['POST'])
@login_required
def reply(id):
    """Ответ в тикете"""
    ticket = Ticket.query.get_or_404(id)
    if _is_manager_chat_ticket(ticket):
        return _manager_chat_or_support_redirect(ticket)

    if not current_user.is_admin and ticket.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('tickets.index'))

    message_text = request.form.get('message', '').strip()

    if not message_text:
        flash('Сообщение не может быть пустым', 'error')
        return redirect(url_for('tickets.view', id=id))

    # Создаём сообщение
    new_message = add_message(
        ticket.id,
        current_user.id,
        message_text,
        current_user.is_admin,
    )

    # Обработка вложений, если есть
    files = request.files.getlist('attachments')
    if files and any(f.filename for f in files):
        _process_ticket_attachments(files, new_message.id)

    if ticket.user_id != current_user.id:
        reply_notif = Notification(
            user_id=ticket.user_id,
            kind='ticket_reply',
            title='Новый ответ в тикете',
            message=f'В тикете «{ticket.subject}» новый ответ.',
            ticket_id=ticket.id,
        )
        db.session.add(reply_notif)
        db.session.commit()

        if current_user.is_admin:
            try:
                db.session.refresh(ticket)
                from app.utils.email import send_ticket_reply_email

                ok = send_ticket_reply_email(ticket, message_text)
                if not ok:
                    flash('Уведомление на почту автору не отправлено', 'warning')
            except Exception as e:
                current_app.logger.warning('Ошибка отправки email об ответе: %s', e)
                flash(f'Ошибка отправки email: {e}', 'warning')

    flash('Сообщение отправлено', 'success')
    return redirect(url_for('tickets.view', id=id))


@tickets_bp.route('/tickets/<int:id>/status')
@login_required
def ticket_status(id):
    """JSON-статус тикета для реального времени."""
    ticket = Ticket.query.get_or_404(id)
    if _is_manager_chat_ticket(ticket):
        return jsonify({'ok': False, 'error': 'use_manager_chat'}), 400
    if not current_user.is_admin and ticket.user_id != current_user.id:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    return jsonify(
        {
            'ok': True,
            'ticket_id': ticket.id,
            'status': ticket.status,
            'status_display': ticket.status_display,
            'status_class': ticket.status_class,
            'updated_at': ticket.updated_at.isoformat() if ticket.updated_at else '',
        }
    )


@tickets_bp.route('/tickets/<int:id>/thread')
@login_required
def thread(id):
    """JSON для модального окна переписки по тикету."""
    ticket = Ticket.query.get_or_404(id)
    if _is_manager_chat_ticket(ticket):
        return jsonify({'ok': False, 'error': 'use_manager_chat'}), 400
    if not current_user.is_admin and ticket.user_id != current_user.id:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    Notification.query.filter_by(
        user_id=current_user.id, ticket_id=ticket.id, is_read=False
    ).update({'is_read': True})
    db.session.commit()

    messages = ticket.messages.order_by(TicketMessage.created_at).all()
    html = render_template(
        'tickets/_thread_modal_content.html',
        ticket=ticket,
        messages=messages,
    )
    return jsonify(
        {
            'ok': True,
            'html': html,
            'ticket_id': ticket.id,
            'status': ticket.status,
            'status_display': ticket.status_display,
            'status_class': ticket.status_class,
            'updated_at': ticket.updated_at.isoformat() if ticket.updated_at else '',
        }
    )


@tickets_bp.route('/tickets/<int:id>/reply-ajax', methods=['POST'])
@login_required
def reply_ajax(id):
    """AJAX-ответ в тикете из модального окна."""
    ticket = Ticket.query.get_or_404(id)
    if _is_manager_chat_ticket(ticket):
        return jsonify({'ok': False, 'error': 'use_manager_chat'}), 400
    if not current_user.is_admin and ticket.user_id != current_user.id:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    message_text = request.form.get('message', '').strip()
    if not message_text:
        return jsonify({'ok': False, 'error': 'empty_message'}), 400

    new_message = add_message(
        ticket.id,
        current_user.id,
        message_text,
        current_user.is_admin,
    )

    # Обработка вложений, если есть (как в обычной форме ответа)
    files = request.files.getlist('attachments')
    if files and any(f.filename for f in files):
        _process_ticket_attachments(files, new_message.id)

    if ticket.user_id != current_user.id:
        reply_notif = Notification(
            user_id=ticket.user_id,
            kind='ticket_reply',
            title='Новый ответ в тикете',
            message=f'В тикете «{ticket.subject}» новый ответ.',
            ticket_id=ticket.id,
        )
        db.session.add(reply_notif)
        db.session.commit()

        if current_user.is_admin:
            try:
                db.session.refresh(ticket)
                from app.utils.email import send_ticket_reply_email

                send_ticket_reply_email(ticket, message_text)
            except Exception as e:
                current_app.logger.warning('Ошибка отправки email об ответе (ajax): %s', e)

    messages = ticket.messages.order_by(TicketMessage.created_at).all()
    html = render_template(
        'tickets/_thread_modal_content.html',
        ticket=ticket,
        messages=messages,
    )
    return jsonify(
        {
            'ok': True,
            'html': html,
            'ticket_id': ticket.id,
            'status': ticket.status,
            'status_display': ticket.status_display,
            'status_class': ticket.status_class,
            'updated_at': ticket.updated_at.isoformat() if ticket.updated_at else '',
        }
    )


@tickets_bp.route('/tickets/<int:id>/close-ajax', methods=['POST'])
@login_required
def close_ajax(id):
    """AJAX-закрытие тикета из модального окна."""
    ticket = Ticket.query.get_or_404(id)
    if _is_manager_chat_ticket(ticket):
        return jsonify({'ok': False, 'error': 'use_manager_chat'}), 400
    if not current_user.is_admin and ticket.user_id != current_user.id:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    if ticket.status != 'closed':
        close_ticket(ticket.id, actor_user_id=current_user.id)
        db.session.refresh(ticket)

        if ticket.user_id != current_user.id:
            close_notif = Notification(
                user_id=ticket.user_id,
                kind='ticket_closed',
                title='Тикет закрыт',
                message=f'Тикет «{ticket.subject}» закрыт.',
                ticket_id=ticket.id,
            )
            db.session.add(close_notif)
            db.session.commit()

            if current_user.is_admin:
                try:
                    db.session.refresh(ticket)
                    from app.utils.email import send_ticket_closed_email

                    send_ticket_closed_email(ticket)
                except Exception as e:
                    current_app.logger.warning('Ошибка отправки email о закрытии (ajax): %s', e)

    messages = ticket.messages.order_by(TicketMessage.created_at).all()
    html = render_template(
        'tickets/_thread_modal_content.html',
        ticket=ticket,
        messages=messages,
    )
    return jsonify(
        {
            'ok': True,
            'html': html,
            'ticket_id': ticket.id,
            'status': ticket.status,
            'status_display': ticket.status_display,
            'status_class': ticket.status_class,
            'updated_at': ticket.updated_at.isoformat() if ticket.updated_at else '',
        }
    )


@tickets_bp.route('/tickets/<int:id>/open-ajax', methods=['POST'])
@login_required
@admin_required
def reopen_ajax(id):
    """AJAX-открытие тикета (только админ) из модального окна."""
    ticket = Ticket.query.get_or_404(id)
    if _is_manager_chat_ticket(ticket):
        return jsonify({'ok': False, 'error': 'use_manager_chat'}), 400
    if ticket.status == 'closed':
        ticket.status = 'waiting_for_admin'
        ticket.updated_at = datetime.utcnow()
        db.session.commit()
        try:
            from app.services.telegram_bot import send_ticket_status

            send_ticket_status(ticket, actor_user_id=current_user.id)
        except Exception as e:
            current_app.logger.warning('Telegram ticket reopen notify failed: %s', e)

    messages = ticket.messages.order_by(TicketMessage.created_at).all()
    html = render_template(
        'tickets/_thread_modal_content.html',
        ticket=ticket,
        messages=messages,
    )
    return jsonify(
        {
            'ok': True,
            'html': html,
            'ticket_id': ticket.id,
            'status': ticket.status,
            'status_display': ticket.status_display,
            'status_class': ticket.status_class,
            'updated_at': ticket.updated_at.isoformat() if ticket.updated_at else '',
        }
    )


@tickets_bp.route('/tickets/<int:id>/close', methods=['POST'])
@login_required
def close(id):
    """Закрытие тикета"""
    ticket = Ticket.query.get_or_404(id)
    if _is_manager_chat_ticket(ticket):
        return _manager_chat_or_support_redirect(ticket)

    if not current_user.is_admin and ticket.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('tickets.index'))

    close_ticket(ticket.id, actor_user_id=current_user.id)

    if ticket.user_id != current_user.id:
        close_notif = Notification(
            user_id=ticket.user_id,
            kind='ticket_closed',
            title='Тикет закрыт',
            message=f'Тикет «{ticket.subject}» закрыт.',
            ticket_id=ticket.id,
        )
        db.session.add(close_notif)
        db.session.commit()

        if current_user.is_admin:
            try:
                db.session.refresh(ticket)
                from app.utils.email import send_ticket_closed_email

                ok = send_ticket_closed_email(ticket)
                if not ok:
                    flash('Уведомление на почту автору не отправлено', 'warning')
            except Exception as e:
                current_app.logger.warning('Ошибка отправки email о закрытии: %s', e)
                flash(f'Ошибка отправки email: {e}', 'warning')
    else:
        close_notif = Notification(
            user_id=current_user.id,
            kind='ticket_closed',
            title='Тикет закрыт',
            message=f'Тикет «{ticket.subject}» закрыт.',
            ticket_id=ticket.id,
        )
        db.session.add(close_notif)
        db.session.commit()

    flash('Тикет закрыт', 'success')
    status = request.args.get('status', '')
    return redirect(url_for('tickets.view', id=id, status=status))


@tickets_bp.route('/tickets/<int:id>/open', methods=['POST'])
@login_required
@admin_required
def reopen(id):
    """Открытие тикета (только админ)"""
    ticket = Ticket.query.get_or_404(id)
    if _is_manager_chat_ticket(ticket):
        return _manager_chat_or_support_redirect(ticket)

    ticket.status = 'waiting_for_admin'
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    try:
        from app.services.telegram_bot import send_ticket_status

        send_ticket_status(ticket, actor_user_id=current_user.id)
    except Exception as e:
        current_app.logger.warning('Telegram ticket reopen notify failed: %s', e)

    flash('Тикет открыт', 'success')
    return redirect(url_for('tickets.view', id=id))


@tickets_bp.route('/tickets/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    """Удаление тикета"""
    ticket = Ticket.query.get_or_404(id)

    db.session.delete(ticket)
    db.session.commit()

    flash('Тикет удалён', 'success')
    return redirect(url_for('tickets.index'))
