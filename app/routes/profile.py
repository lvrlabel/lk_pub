"""
Профиль пользователя
"""

import os
import json
import secrets
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, session
from flask_login import login_required, current_user
from app import db
from app.utils.files import save_file, delete_file, allowed_file
from app.utils.validators import validate_password
from app.utils.user_tax import apply_tax_fields_from_request
from app.utils.email import send_profile_update_code_email
from app.models.user import User
from app.models.contract import Contract
from app.models.social_account import SocialAccount
from app.models.auth import ProfileUpdateCode
from app.models.bonus import BonusTransaction
from app.utils.bonus_program import bonus_services_for_user, bonus_services_catalog

profile_bp = Blueprint('profile', __name__)

OAUTH_STATE_KEY = 'oauth_link_state'
SOCIAL_PROVIDERS = ('yandex',)
SESSION_PROFILE_EDIT_PENDING = 'profile_edit_pending'
PROFILE_EDIT_CODE_RESEND_COOLDOWN = 60


def _normalize_telegram_username(value):
    raw = (value or '').strip().lstrip('@')
    if not raw:
        return None
    if len(raw) > 64:
        raw = raw[:64]
    return raw


def _ensure_telegram_link_token(user):
    if user.telegram_link_token:
        return user.telegram_link_token
    user.telegram_link_token = secrets.token_urlsafe(16)
    db.session.commit()
    return user.telegram_link_token


def _telegram_bot_username():
    return (current_app.config.get('TELEGRAM_BOT_USERNAME') or 'toolls_music_bot').lstrip('@')


def _telegram_connect_url(user):
    token = _ensure_telegram_link_token(user)
    bot = _telegram_bot_username()
    return f'https://t.me/{bot}?start=link_{token}'


def _social_provider_title(provider):
    return {
        'yandex': 'Яндекс',
    }.get(provider, provider)


def _provider_credentials(provider):
    if provider == 'yandex':
        return (
            current_app.config.get('OAUTH_YANDEX_CLIENT_ID'),
            current_app.config.get('OAUTH_YANDEX_CLIENT_SECRET'),
        )
    return (None, None)


def _provider_enabled(provider):
    client_id, client_secret = _provider_credentials(provider)
    return bool(client_id and client_secret)


def _oauth_start_url(provider, redirect_uri, state):
    if provider == 'yandex':
        params = {
            'client_id': current_app.config.get('OAUTH_YANDEX_CLIENT_ID'),
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'state': state,
        }
        return 'https://oauth.yandex.ru/authorize?' + urlencode(params)
    return None


def _post_form_json(url, data):
    body = urlencode(data).encode('utf-8')
    req = Request(url, data=body, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _get_json(url, token):
    req = Request(url, headers={'Authorization': f'Bearer {token}'})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _fetch_oauth_identity(provider, code, redirect_uri):
    if provider == 'yandex':
        token_data = _post_form_json(
            'https://oauth.yandex.ru/token',
            {
                'code': code,
                'client_id': current_app.config.get('OAUTH_YANDEX_CLIENT_ID'),
                'client_secret': current_app.config.get('OAUTH_YANDEX_CLIENT_SECRET'),
                'grant_type': 'authorization_code',
            },
        )
        access_token = token_data.get('access_token')
        info = _get_json('https://login.yandex.ru/info?format=json', access_token)
        return {
            'provider_user_id': str(info.get('id') or ''),
            'email': info.get('default_email') or info.get('emails', [None])[0] or None,
        }

    return {'provider_user_id': '', 'email': None}


@profile_bp.route('/profile')
@login_required
def index():
    """Профиль пользователя"""
    from app.services.session_manager import get_bound_session_id, list_active_sessions_for_ui

    accounts = {a.provider: a for a in current_user.social_accounts.all()}
    social_providers = []
    for provider in SOCIAL_PROVIDERS:
        social_providers.append(
            {
                'key': provider,
                'title': _social_provider_title(provider),
                'enabled': _provider_enabled(provider),
                'account': accounts.get(provider),
            }
        )
    current_sid = get_bound_session_id()
    active_sessions = list_active_sessions_for_ui(current_user.id, current_sid)
    return render_template(
        'profile/index.html',
        social_providers=social_providers,
        telegram_bot_username=_telegram_bot_username(),
        telegram_connect_url=_telegram_connect_url(current_user),
        bonus_balance=current_user.bonus_balance_display,
        bonus_services=bonus_services_for_user(current_user.bonus_balance_display),
        bonus_history=(
            BonusTransaction.query.filter_by(user_id=current_user.id)
            .order_by(BonusTransaction.created_at.desc())
            .limit(50)
            .all()
        ),
        bonus_catalog=bonus_services_catalog(),
        active_sessions=active_sessions,
        current_session_id=current_sid,
        latest_contract=current_user.contracts.order_by(Contract.created_at.desc()).first(),
    )


@profile_bp.route('/profile/sessions/<int:session_pk>/revoke', methods=['POST'])
@login_required
def revoke_session(session_pk):
    """Принудительный выход с выбранного устройства."""
    from app.services.session_manager import (
        device_fingerprint,
        get_bound_session_id,
        revoke_sessions_same_device,
    )
    from flask_login import logout_user
    from app.models.user_session import UserSession

    current_sid = get_bound_session_id()
    target = UserSession.query.filter_by(id=session_pk, user_id=current_user.id).first()
    if not target:
        flash('Сессия не найдена', 'error')
        return redirect(url_for('profile.index') + '#profile-devices')

    is_current = False
    if current_sid:
        cur = UserSession.query.filter_by(
            session_id=current_sid, user_id=current_user.id
        ).first()
        if cur and device_fingerprint(cur.ip_address, cur.device_label) == device_fingerprint(
            target.ip_address, target.device_label
        ):
            is_current = True

    ok, _row = revoke_sessions_same_device(
        current_user.id, session_pk, reason='self_revoke' if is_current else 'device_revoke'
    )
    if not ok:
        flash('Не удалось отключить устройство', 'error')
        return redirect(url_for('profile.index') + '#profile-devices')

    if is_current:
        from app.services.session_manager import clear_bound_session_id
        clear_bound_session_id()
        logout_user()
        flash('Вы вышли с этого устройства', 'info')
        return redirect(url_for('auth.login'))

    flash('Устройство отключено', 'success')
    return redirect(url_for('profile.index') + '#profile-devices')


@profile_bp.route('/profile/sessions/revoke-others', methods=['POST'])
@login_required
def revoke_other_sessions_route():
    """Выйти со всех устройств, кроме текущего."""
    from app.services.session_manager import get_bound_session_id, revoke_other_sessions

    current_sid = get_bound_session_id()
    count = revoke_other_sessions(current_user.id, current_sid, reason='revoke_others')
    if count:
        flash(f'Отключено устройств: {count}', 'success')
    else:
        flash('Других активных устройств нет', 'info')
    return redirect(url_for('profile.index') + '#profile-devices')


@profile_bp.route('/profile/sessions/<int:session_pk>/trust', methods=['POST'])
@login_required
def trust_session(session_pk):
    """Отметить устройство как доверенное / снять метку."""
    from app.services.session_manager import set_trusted

    trusted = (request.form.get('trusted') or '1').strip() in ('1', 'true', 'yes', 'on')
    ok = set_trusted(current_user.id, session_pk, trusted)
    if ok:
        flash('Доверенное устройство обновлено' if trusted else 'Метка доверия снята', 'success')
    else:
        flash('Не удалось обновить устройство', 'error')
    return redirect(url_for('profile.index') + '#profile-devices')


@profile_bp.route('/profile/social/connect/<provider>')
@login_required
def social_connect(provider):
    """Начать OAuth привязку аккаунта соцсети."""
    provider = (provider or '').strip().lower()
    if provider not in SOCIAL_PROVIDERS:
        flash('Неизвестный провайдер', 'error')
        return redirect(url_for('profile.index'))
    if not _provider_enabled(provider):
        flash(f'Интеграция {_social_provider_title(provider)} пока не настроена', 'warning')
        return redirect(url_for('profile.index'))
    current_app.logger.info('Social connect started: user_id=%s provider=%s', current_user.id, provider)

    state = secrets.token_urlsafe(24)
    session[OAUTH_STATE_KEY] = {'provider': provider, 'state': state}
    redirect_uri = url_for('profile.social_callback', provider=provider, _external=True)
    auth_url = _oauth_start_url(provider, redirect_uri, state)
    if not auth_url:
        flash('Не удалось запустить привязку', 'error')
        return redirect(url_for('profile.index'))
    return redirect(auth_url)


@profile_bp.route('/profile/social/callback/<provider>')
@login_required
def social_callback(provider):
    """OAuth callback для привязки соцсети к текущему пользователю."""
    provider = (provider or '').strip().lower()
    stored = session.pop(OAUTH_STATE_KEY, None) or {}
    if provider not in SOCIAL_PROVIDERS or stored.get('provider') != provider:
        flash('Сессия привязки истекла. Попробуйте снова.', 'error')
        return redirect(url_for('profile.index'))
    if request.args.get('state') != stored.get('state'):
        flash('Проверка безопасности не пройдена. Попробуйте снова.', 'error')
        current_app.logger.warning(
            'Social connect state mismatch: user_id=%s provider=%s',
            current_user.id,
            provider,
        )
        return redirect(url_for('profile.index'))
    if request.args.get('error'):
        flash(f'Привязка {_social_provider_title(provider)} отменена или отклонена', 'warning')
        return redirect(url_for('profile.index'))

    code = (request.args.get('code') or '').strip()
    if not code:
        flash('Не получен код авторизации от провайдера', 'error')
        return redirect(url_for('profile.index'))

    try:
        identity = _fetch_oauth_identity(
            provider,
            code,
            url_for('profile.social_callback', provider=provider, _external=True),
        )
    except (HTTPError, URLError, TimeoutError, ValueError) as e:
        current_app.logger.warning('OAuth callback %s failed: %s', provider, e)
        flash(f'Не удалось завершить привязку {_social_provider_title(provider)}. Попробуйте позже.', 'error')
        return redirect(url_for('profile.index'))

    provider_user_id = (identity.get('provider_user_id') or '').strip()
    provider_email = (identity.get('email') or '').strip() or None
    if not provider_user_id:
        flash('Провайдер не вернул идентификатор аккаунта. Привязка не выполнена.', 'error')
        return redirect(url_for('profile.index'))

    existing = SocialAccount.query.filter_by(
        provider=provider,
        provider_user_id=provider_user_id,
    ).first()
    if existing and existing.user_id != current_user.id:
        flash('Этот соц-аккаунт уже привязан к другому пользователю', 'error')
        current_app.logger.warning(
            'Social connect conflict: user_id=%s provider=%s provider_user_id=%s',
            current_user.id,
            provider,
            provider_user_id,
        )
        return redirect(url_for('profile.index'))

    account = SocialAccount.query.filter_by(user_id=current_user.id, provider=provider).first()
    if not account:
        account = SocialAccount(
            user_id=current_user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=provider_email,
        )
        db.session.add(account)
    else:
        account.provider_user_id = provider_user_id
        account.email = provider_email
    db.session.commit()
    current_app.logger.info('Social connected: user_id=%s provider=%s', current_user.id, provider)
    flash(f'Аккаунт {_social_provider_title(provider)} успешно привязан', 'success')
    return redirect(url_for('profile.index'))


@profile_bp.route('/profile/social/disconnect/<provider>', methods=['POST'])
@login_required
def social_disconnect(provider):
    """Отвязать соцсеть от текущего пользователя."""
    provider = (provider or '').strip().lower()
    if provider not in SOCIAL_PROVIDERS:
        flash('Неизвестный провайдер', 'error')
        return redirect(url_for('profile.index'))
    account = SocialAccount.query.filter_by(user_id=current_user.id, provider=provider).first()
    if not account:
        flash('Аккаунт уже не привязан', 'info')
        return redirect(url_for('profile.index'))
    linked_count = current_user.social_accounts.count()
    if not current_user.has_password and linked_count <= 1:
        flash(
            'Нельзя отвязать последний способ входа. Сначала задайте пароль или подключите другую соцсеть.',
            'error',
        )
        return redirect(url_for('profile.index'))
    db.session.delete(account)
    db.session.commit()
    current_app.logger.info('Social disconnected: user_id=%s provider=%s', current_user.id, provider)
    flash(f'Привязка {_social_provider_title(provider)} удалена', 'success')
    return redirect(url_for('profile.index'))


@profile_bp.route('/profile/telegram/disconnect', methods=['POST'])
@login_required
def telegram_disconnect():
    """Отвязать Telegram-уведомления от аккаунта."""
    chat_id = current_user.telegram_chat_id
    if chat_id:
        try:
            from app.services.telegram_bot import unsubscribe
            unsubscribe(int(chat_id))
        except Exception as exc:
            current_app.logger.warning('telegram_disconnect: %s', exc)
    current_user.telegram_chat_id = None
    db.session.commit()
    flash('Telegram-уведомления отключены для этого аккаунта', 'success')
    return redirect(url_for('profile.index'))


@profile_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit():
    """Редактирование профиля"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip() or None
        copyright_text = request.form.get('copyright', '').strip()
        telegram_username = _normalize_telegram_username(request.form.get('telegram_username'))
        
        # Валидация email
        if email != current_user.email:
            if User.query.filter_by(email=email).first():
                flash('Этот email уже используется', 'error')
                return render_template('profile/edit.html')
        
        # Нормализация телефона (упрощённая: оставляем цифры, 79XXXXXXXXX)
        if phone:
            import re
            digits = re.sub(r'\D', '', phone)
            if len(digits) == 10 and digits.startswith('9'):
                phone = '7' + digits
            elif len(digits) == 11 and digits.startswith('7'):
                phone = digits
            elif len(digits) == 11 and digits.startswith('8'):
                phone = '7' + digits[1:]
            else:
                phone = digits if len(digits) >= 10 else None
        
        # Обновление данных
        pending = {
            'name': name,
            'email': email,
            'phone': phone,
            'copyright': copyright_text or None,
            'telegram_username': telegram_username,
        }
        
        # Обновление аватара
        avatar_file = request.files.get('avatar')
        if avatar_file and avatar_file.filename:
            if allowed_file(avatar_file.filename, current_app.config['ALLOWED_IMAGE_EXTENSIONS']):
                filename = save_file(avatar_file, 'avatars')
                if filename:
                    pending['new_avatar'] = filename
            else:
                flash('Недопустимый формат аватара. Разрешены: JPG, PNG', 'error')
                return render_template('profile/edit.html')

        code_obj = ProfileUpdateCode.create_for_user(current_user.id)
        db.session.commit()
        ok, err_msg = send_profile_update_code_email(current_user, code_obj.code)
        if not ok:
            if pending.get('new_avatar'):
                delete_file(pending['new_avatar'], 'avatars')
            ProfileUpdateCode.query.filter_by(user_id=current_user.id).delete()
            db.session.commit()
            flash(err_msg or 'Не удалось отправить код подтверждения на почту', 'error')
            return render_template('profile/edit.html')

        session[SESSION_PROFILE_EDIT_PENDING] = pending
        session['profile_edit_pending_at'] = datetime.utcnow().isoformat()
        flash('Код подтверждения отправлен на вашу почту. Введите его для сохранения изменений.', 'success')
        return redirect(url_for('profile.edit_verify'))
    
    return render_template('profile/edit.html')


@profile_bp.route('/profile/edit/verify', methods=['GET', 'POST'])
@login_required
def edit_verify():
    """Подтверждение изменения профиля кодом из email."""
    pending = session.get(SESSION_PROFILE_EDIT_PENDING)
    if not pending:
        flash('Нет ожидающих подтверждения изменений профиля.', 'info')
        return redirect(url_for('profile.edit'))

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip().replace(' ', '')
        if len(code) != 5 or not code.isdigit():
            flash('Введите 5 цифр кода', 'error')
            return render_template('profile/edit_verify.html')

        code_obj = ProfileUpdateCode.get_valid_for_user(current_user.id)
        if not code_obj:
            flash('Код истёк или недействителен. Запросите новый код.', 'error')
            return render_template('profile/edit_verify.html')

        if code_obj.code != code:
            flash('Неверный код. Проверьте письмо и попробуйте ещё раз.', 'error')
            return render_template('profile/edit_verify.html')

        old_avatar = current_user.avatar
        current_user.name = pending.get('name') or current_user.name
        current_user.email = pending.get('email') or current_user.email
        current_user.phone = pending.get('phone')
        current_user.copyright = pending.get('copyright')
        current_user.telegram_username = pending.get('telegram_username')
        if pending.get('new_avatar'):
            current_user.avatar = pending.get('new_avatar')
        db.session.commit()

        if pending.get('new_avatar') and old_avatar and old_avatar != current_user.avatar:
            delete_file(old_avatar, 'avatars')

        ProfileUpdateCode.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        session.pop(SESSION_PROFILE_EDIT_PENDING, None)
        session.pop('profile_edit_pending_at', None)
        flash('Профиль успешно обновлён', 'success')
        return redirect(url_for('profile.index'))

    return render_template('profile/edit_verify.html')


@profile_bp.route('/profile/edit/verify/resend', methods=['POST'])
@login_required
def edit_verify_resend():
    """Повторная отправка кода подтверждения изменения профиля."""
    pending = session.get(SESSION_PROFILE_EDIT_PENDING)
    if not pending:
        flash('Нет ожидающих подтверждения изменений.', 'info')
        return redirect(url_for('profile.edit'))

    last = ProfileUpdateCode.last_sent_at(current_user.id)
    if last and (datetime.utcnow() - last).total_seconds() < PROFILE_EDIT_CODE_RESEND_COOLDOWN:
        flash('Новый код можно запросить через минуту после предыдущей отправки.', 'warning')
        return redirect(url_for('profile.edit_verify'))

    code_obj = ProfileUpdateCode.create_for_user(current_user.id)
    db.session.commit()
    ok, err_msg = send_profile_update_code_email(current_user, code_obj.code)
    if ok:
        flash('Новый код отправлен на почту.', 'success')
        return redirect(url_for('profile.edit_verify'))
    flash(err_msg or 'Не удалось отправить код.', 'error')
    return redirect(url_for('profile.edit_verify'))


@profile_bp.route('/profile/tax-info/edit', methods=['GET', 'POST'])
@login_required
def tax_info_edit():
    """
    Налоговая информация: у артиста/лейбла — только через поддержку.
    Администратор может править свою карточку здесь; чужие — в разделе Пользователи.
    """
    if not current_user.is_admin:
        flash(
            'Изменить налоговую и платёжную информацию можно только через запрос в поддержку: '
            'создайте тикет и опишите, какие реквизиты нужно обновить.',
            'warning',
        )
        return redirect(url_for('profile.index'))

    if request.method == 'POST':
        apply_tax_fields_from_request(current_user, request.form)
        db.session.commit()
        flash('Налоговая и платёжная информация сохранена', 'success')
        return redirect(url_for('profile.index'))

    return render_template(
        'profile/tax_info.html',
        user=current_user,
        tax_choices=User.TAX_STATUS_CHOICES,
    )


@profile_bp.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Смена пароля"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Проверка текущего пароля
        if not current_user.check_password(current_password):
            flash('Неверный текущий пароль', 'error')
            return render_template('profile/change_password.html')
        
        # Проверка совпадения паролей
        if new_password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return render_template('profile/change_password.html')
        
        # Валидация нового пароля
        password_errors = validate_password(new_password)
        if password_errors:
            for error in password_errors:
                flash(error, 'error')
            return render_template('profile/change_password.html')
        
        # Смена пароля
        current_user.set_password(new_password)
        db.session.commit()
        
        flash('Пароль успешно изменён', 'success')
        return redirect(url_for('profile.index'))
    
    return render_template('profile/change_password.html')


@profile_bp.route('/profile/delete-avatar', methods=['POST'])
@login_required
def delete_avatar():
    """Удаление аватара"""
    if current_user.avatar:
        delete_file(current_user.avatar, 'avatars')
        current_user.avatar = None
        db.session.commit()
        flash('Аватар удалён', 'success')
    
    return redirect(url_for('profile.edit'))


@profile_bp.route('/uploads/avatars/<filename>')
@login_required
def serve_avatar(filename):
    """Отдача файла аватара"""
    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', 'avatars')
    return send_file(os.path.join(upload_folder, filename))
