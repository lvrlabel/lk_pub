"""
Авторизация
"""

import json
import secrets
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from flask import Blueprint, redirect, url_for, request, flash, render_template, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.auth import AuthToken, LoginCode
from app.models.user import User
from app.models.social_account import SocialAccount
from app.utils.email import send_login_code_email

auth_bp = Blueprint('auth', __name__)

SESSION_SOCIAL_LOGIN_STATE = 'social_login_state'
SOCIAL_PROVIDERS = ('yandex',)


def _admin_email():
    """Email для кодов входа администратора (из .env ADMIN_EMAIL)."""
    return (current_app.config.get('ADMIN_EMAIL') or 'l.vilyasante@icloud.com').strip()


def _blocked_account_message(user):
    """Сообщение после верного логина/пароля, если учётная запись отключена."""
    base = (
        'Доступ в личный кабинет ограничён: учётная запись заблокирована администратором.'
    )
    reason = (getattr(user, 'block_reason', None) or '').strip()
    if reason:
        return f'{base}\n\nПричина:\n{reason}'
    return base


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


def _social_login_providers():
    providers = []
    for provider in SOCIAL_PROVIDERS:
        providers.append(
            {
                'key': provider,
                'title': _social_provider_title(provider),
                'enabled': _provider_enabled(provider),
            }
        )
    return providers


def _render_login():
    return render_template('auth/login.html', social_login_providers=_social_login_providers())


def _user_telegram_connected(user):
    return bool(getattr(user, 'telegram_chat_id', None))


def _login_code_delivery_message(email_ok, telegram_ok, resend=False):
    prefix = 'Новый код подтверждения' if resend else 'Код подтверждения'
    if email_ok and telegram_ok:
        return f'{prefix} отправлен на почту и в Telegram.'
    if email_ok:
        return f'{prefix} отправлен на почту.'
    if telegram_ok:
        return f'{prefix} отправлен в Telegram.'
    return None


def _send_login_code_telegram(user, code):
    """Отправка кода в Telegram; при ошибке модуля вход по email не ломается."""
    try:
        from app.services.telegram_bot import send_login_code
        return send_login_code(user, code)
    except Exception as exc:
        current_app.logger.warning('Telegram login code skipped: %s', exc)
        return False


def _deliver_login_code(user, code, recipient_override=None, resend=False):
    """
    Отправить код входа на email и в Telegram (если привязан).
    Возвращает (успех, сообщение_для_пользователя, email_err).
    """
    email_ok, email_err = send_login_code_email(user, code, recipient_override=recipient_override)
    telegram_ok = _send_login_code_telegram(user, code)
    # Для админа код обязан уйти на email (recipient_override), Telegram — дополнительно.
    if recipient_override and not email_ok:
        return False, None, email_err
    message = _login_code_delivery_message(email_ok, telegram_ok, resend=resend)
    return bool(message), message, email_err


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
        return {'provider_user_id': str(info.get('id') or '')}
    return {'provider_user_id': ''}


def _issue_sml_session(user):
    """Выдать sessionId после login_user (SML-слой)."""
    try:
        from app.services.session_manager import issue_session_after_login
        issue_session_after_login(user)
    except Exception:
        pass


def _lk_home_url():
    """Корень ЛК после успешного входа: https://lk…/"""
    callback_url = (current_app.config.get('AUTH_CALLBACK_URL') or '').strip()
    if callback_url:
        try:
            parsed = urlparse(callback_url)
            if parsed.scheme and parsed.netloc:
                return f'{parsed.scheme}://{parsed.netloc}/'
        except Exception:
            pass
    return url_for('dashboard.index')


def _finish_login(user):
    """Единая безопасная финализация входа."""
    callback_url = (current_app.config.get('AUTH_CALLBACK_URL') or '').strip()
    if callback_url:
        try:
            parsed = urlparse(callback_url)
            if parsed.netloc and parsed.netloc != request.host:
                auth_token = AuthToken.create_for_user(user.id)
                db.session.add(auth_token)
                db.session.commit()
                sep = '&' if '?' in callback_url else '?'
                return render_template(
                    'auth/login_loading.html',
                    user=user,
                    redirect_url=f'{callback_url}{sep}token={auth_token.token}',
                    delay_ms=1400,
                )
        except Exception:
            pass
    login_user(user, remember=True)
    _issue_sml_session(user)
    return render_template(
        'auth/login_loading.html',
        user=user,
        redirect_url=_lk_home_url(),
        delay_ms=1400,
    )


@auth_bp.route('/favicon.ico')
def favicon():
    """Браузеры запрашивают /favicon.ico по умолчанию."""
    return redirect(url_for('static', filename='img/favicon.svg'))


@auth_bp.route('/ping')
def ping():
    """Проверка, что приложение Passenger запущено."""
    return 'OK', 200


@auth_bp.route('/')
def index():
    """Главная: на auth — логин; на lk после входа остаёмся на / (дашборд)."""
    if current_user.is_authenticated:
        # Чтобы итоговый URL был https://lk…/, а не /dashboard
        from app.routes.dashboard import index as dashboard_index
        return dashboard_index()
    return redirect(url_for('auth.login'))


@auth_bp.route('/faq')
def faq():
    """Страница «Часто задаваемые вопросы»"""
    return render_template('auth/faq.html')


@auth_bp.route('/legal/agreement')
def legal_agreement():
    """Пользовательское соглашение"""
    return render_template('legal/agreement.html')


@auth_bp.route('/legal/privacy')
def legal_privacy():
    """Политика конфиденциальности"""
    return render_template('legal/privacy.html')


@auth_bp.route('/login/forgot-password')
def forgot_password():
    """Напоминание о забытом пароле"""
    flash('Если вы забыли пароль, обратитесь в службу поддержки по электронной почте: support@toolls-music.ru. Либо на официальном сайте, в разделе «Контакты», в форме обратной связи.', 'support')
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа — обычная форма логин/пароль"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        login_value = request.form.get('login', '').strip()
        password = request.form.get('password', '')

        if not login_value or not password:
            flash('Введите логин и пароль', 'error')
            return _render_login()

        # Логин или email
        user = User.query.filter(
            (User.login == login_value) | (User.email == login_value)
        ).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash(_blocked_account_message(user), 'error')
                return _render_login()
            login_code = LoginCode.create_for_user(user.id)
            db.session.commit()

            # SMS-коды отключены: отправляем код подтверждения ТОЛЬКО на email.
            # Для админа письмо уходит всегда на ADMIN_EMAIL.
            if user.role != 'admin' and not user.email:
                flash('В вашем аккаунте не указан email для получения кода. Заполните email в профиле.', 'error')
                return _render_login()

            recipient = _admin_email() if user.role == 'admin' else None
            ok, success_msg, err_msg = _deliver_login_code(user, login_code.code, recipient_override=recipient)
            session['login_verify_user_id'] = user.id

            if ok:
                flash(success_msg, 'success')
                return redirect(url_for('auth.login_verify'))

            if current_app.debug:
                flash(f'Почта и Telegram недоступны. Режим разработки — введите код: {login_code.code}', 'warning')
                return redirect(url_for('auth.login_verify'))

            flash(err_msg or 'Не удалось отправить код. Попробуйте позже.', 'error')
            return redirect(url_for('auth.login'))

        else:
            flash('Неверный логин или пароль', 'error')

    return _render_login()


@auth_bp.route('/login/social/<provider>')
def social_login_start(provider):
    """Начало входа через соцсеть (для уже привязанных аккаунтов)."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    provider = (provider or '').strip().lower()
    if provider not in SOCIAL_PROVIDERS:
        flash('Неизвестный провайдер', 'error')
        return redirect(url_for('auth.login'))
    if not _provider_enabled(provider):
        flash(f'Вход через {_social_provider_title(provider)} пока не настроен', 'warning')
        return redirect(url_for('auth.login'))
    current_app.logger.info('Social login started: provider=%s', provider)

    state = secrets.token_urlsafe(24)
    session[SESSION_SOCIAL_LOGIN_STATE] = {'provider': provider, 'state': state}
    redirect_uri = url_for('auth.social_login_callback', provider=provider, _external=True)
    auth_url = _oauth_start_url(provider, redirect_uri, state)
    if not auth_url:
        flash('Не удалось запустить вход через соцсеть', 'error')
        return redirect(url_for('auth.login'))
    return redirect(auth_url)


@auth_bp.route('/login/social/<provider>/callback')
def social_login_callback(provider):
    """OAuth callback входа через соцсеть."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    provider = (provider or '').strip().lower()
    stored = session.pop(SESSION_SOCIAL_LOGIN_STATE, None) or {}
    if provider not in SOCIAL_PROVIDERS or stored.get('provider') != provider:
        flash('Сессия входа через соцсеть истекла. Попробуйте снова.', 'error')
        current_app.logger.warning('Social login state missing: provider=%s', provider)
        return redirect(url_for('auth.login'))
    if request.args.get('state') != stored.get('state'):
        flash('Проверка безопасности не пройдена. Повторите вход.', 'error')
        current_app.logger.warning('Social login state mismatch: provider=%s', provider)
        return redirect(url_for('auth.login'))
    if request.args.get('error'):
        flash(f'Вход через {_social_provider_title(provider)} отменён', 'warning')
        return redirect(url_for('auth.login'))

    code = (request.args.get('code') or '').strip()
    if not code:
        flash('Провайдер не вернул код авторизации', 'error')
        return redirect(url_for('auth.login'))

    try:
        identity = _fetch_oauth_identity(
            provider,
            code,
            url_for('auth.social_login_callback', provider=provider, _external=True),
        )
    except (HTTPError, URLError, TimeoutError, ValueError) as e:
        current_app.logger.warning('Social login %s failed: %s', provider, e)
        flash('Не удалось завершить вход через соцсеть. Попробуйте позже.', 'error')
        return redirect(url_for('auth.login'))

    provider_user_id = (identity.get('provider_user_id') or '').strip()
    if not provider_user_id:
        flash('Провайдер не вернул идентификатор пользователя', 'error')
        return redirect(url_for('auth.login'))

    account = SocialAccount.query.filter_by(
        provider=provider,
        provider_user_id=provider_user_id,
    ).first()
    if not account:
        current_app.logger.info(
            'Social login unlinked account: provider=%s provider_user_id=%s',
            provider,
            provider_user_id,
        )
        flash(
            'Этот соц-аккаунт ещё не привязан. Войдите по логину/паролю и подключите его в профиле.',
            'warning',
        )
        return redirect(url_for('auth.login'))

    user = User.query.get(account.user_id)
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('auth.login'))
    if not user.is_active:
        flash(_blocked_account_message(user), 'error')
        return redirect(url_for('auth.login'))

    flash(f'Добро пожаловать, {user.display_name}!', 'success')
    current_app.logger.info('Social login success: user_id=%s provider=%s', user.id, provider)
    return _finish_login(user)


# Ключ в session для ожидания кода подтверждения входа
SESSION_LOGIN_VERIFY_USER_ID = 'login_verify_user_id'

# Минимальный интервал (секунды) между повторными отправками кода
LOGIN_CODE_RESEND_COOLDOWN = 60


@auth_bp.route('/login/verify', methods=['GET', 'POST'])
def login_verify():
    """Страница ввода кода подтверждения (после успешного логин/пароль)."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    user_id = session.get(SESSION_LOGIN_VERIFY_USER_ID)
    if not user_id:
        flash('Сначала введите логин и пароль', 'info')
        return redirect(url_for('auth.login'))

    user = User.query.get(user_id)
    if not user:
        session.pop(SESSION_LOGIN_VERIFY_USER_ID, None)
        flash('Сессия входа истекла. Войдите снова.', 'error')
        return redirect(url_for('auth.login'))

    if not user.is_active:
        session.pop(SESSION_LOGIN_VERIFY_USER_ID, None)
        flash(_blocked_account_message(user), 'error')
        return redirect(url_for('auth.login'))

    # Для администратора всегда показываем и отправляем код на ADMIN_EMAIL
    display_email = _admin_email() if user.role == 'admin' else (user.email or '')
    telegram_connected = _user_telegram_connected(user)

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip().replace(' ', '')
        if len(code) != 5 or not code.isdigit():
            flash('Введите 5 цифр кода', 'error')
            return render_template(
                'auth/login_verify.html',
                user=user,
                display_email=display_email,
                telegram_connected=telegram_connected,
            )

        login_code = LoginCode.get_valid_for_user(user.id)
        if not login_code:
            flash('Код истёк или недействителен. Запросите новый код.', 'error')
            return render_template(
                'auth/login_verify.html',
                user=user,
                display_email=display_email,
                telegram_connected=telegram_connected,
            )

        if login_code.code != code:
            flash('Неверный код. Проверьте почту или Telegram и введите код ещё раз.', 'error')
            return render_template(
                'auth/login_verify.html',
                user=user,
                display_email=display_email,
                telegram_connected=telegram_connected,
            )

        session.pop(SESSION_LOGIN_VERIFY_USER_ID, None)

        # Редирект на ЛК (lk.toolls-muisic-distribution.ru): создаём токен и отправляем пользователя в callback
        callback_url = (current_app.config.get('AUTH_CALLBACK_URL') or '').strip()
        if callback_url:
            try:
                parsed = urlparse(callback_url)
                if parsed.netloc and parsed.netloc != request.host:
                    auth_token = AuthToken.create_for_user(user.id)
                    db.session.add(auth_token)
                    db.session.commit()
                    sep = '&' if '?' in callback_url else '?'
                    return render_template(
                        'auth/login_loading.html',
                        user=user,
                        redirect_url=f'{callback_url}{sep}token={auth_token.token}',
                        delay_ms=1400
                    )
            except Exception:
                pass

        # Иначе остаёмся на auth (например, локальная разработка)
        login_user(user, remember=True)
        _issue_sml_session(user)
        return render_template(
            'auth/login_loading.html',
            user=user,
            redirect_url=_lk_home_url(),
            delay_ms=1400
        )

    return render_template(
        'auth/login_verify.html',
        user=user,
        display_email=display_email,
        telegram_connected=telegram_connected,
    )


@auth_bp.route('/login/verify/resend', methods=['POST'])
def login_verify_resend():
    """Повторная отправка кода подтверждения на почту."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    user_id = session.get(SESSION_LOGIN_VERIFY_USER_ID)
    if not user_id:
        flash('Сначала введите логин и пароль', 'info')
        return redirect(url_for('auth.login'))

    user = User.query.get(user_id)
    if not user:
        session.pop(SESSION_LOGIN_VERIFY_USER_ID, None)
        flash('Сессия входа истекла. Войдите снова.', 'error')
        return redirect(url_for('auth.login'))

    if not user.is_active:
        session.pop(SESSION_LOGIN_VERIFY_USER_ID, None)
        flash(_blocked_account_message(user), 'error')
        return redirect(url_for('auth.login'))

    from datetime import datetime, timedelta
    last = LoginCode.last_sent_at(user.id)
    if last and (datetime.utcnow() - last).total_seconds() < LOGIN_CODE_RESEND_COOLDOWN:
        flash('Новый код можно запросить через минуту после предыдущей отправки.', 'warning')
        return redirect(url_for('auth.login_verify'))

    login_code = LoginCode.create_for_user(user.id)
    db.session.commit()
    recipient = _admin_email() if user.role == 'admin' else None
    ok, success_msg, err_msg = _deliver_login_code(
        user, login_code.code, recipient_override=recipient, resend=True
    )
    if ok:
        flash(success_msg, 'success')
        return redirect(url_for('auth.login_verify'))
    elif current_app.debug:
        flash(f'Режим разработки — код: {login_code.code}', 'warning')
        return redirect(url_for('auth.login_verify'))
    else:
        flash(err_msg or 'Не удалось отправить код. Попробуйте позже.', 'error')
        return redirect(url_for('auth.login'))


@auth_bp.route('/auth/callback')
def callback():
    """Callback авторизации"""
    token_str = request.args.get('token')
    
    if not token_str:
        flash('Токен авторизации не предоставлен', 'error')
        return redirect(url_for('auth.login'))
    
    # Поиск токена в БД
    token = AuthToken.query.filter_by(token=token_str).first()
    
    if not token:
        flash('Недействительный токен авторизации', 'error')
        return redirect(url_for('auth.login'))
    
    # Проверка срока действия
    if token.is_expired:
        flash('Срок действия токена истек', 'error')
        return redirect(url_for('auth.login'))
    
    # Проверка, что токен не использован
    if token.is_used:
        flash('Токен уже был использован', 'error')
        return redirect(url_for('auth.login'))
    
    # Получение пользователя
    user = User.query.get(token.user_id)
    
    if not user:
        flash('Пользователь не найден', 'error')
        return redirect(url_for('auth.login'))
    
    if not user.is_active:
        flash(_blocked_account_message(user), 'error')
        return redirect(url_for('auth.login'))
    
    # Авторизация пользователя
    login_user(user, remember=True)
    _issue_sml_session(user)
    
    # Помечаем токен как использованный
    token.mark_as_used()
    db.session.commit()
    
    flash(f'Добро пожаловать, {user.display_name}!', 'success')
    # После входа — корень ЛК: https://lk.toolls-muisic-distribution.ru/
    return redirect(_lk_home_url())



@auth_bp.route('/logout')
@login_required
def logout():
    """Выход из системы. Редирект на auth.toolls-muisic-distribution.ru (страница входа), если сейчас на ЛК."""
    from app.services.activity_log import record_user_activity_event
    from app.services.session_manager import revoke_current_bound_session

    uid = current_user.id
    path_logout = request.path
    log_activity = not current_user.is_admin
    try:
        revoke_current_bound_session(reason='logout')
    except Exception:
        pass
    logout_user()
    if log_activity:
        try:
            record_user_activity_event(
                uid,
                'GET',
                'auth.logout',
                path_logout,
                302,
                summary='Выход из системы',
            )
        except Exception:
            pass
    flash('Вы вышли из системы', 'info')
    auth_url = (current_app.config.get('AUTH_SERVICE_URL') or '').strip().rstrip('/')
    if auth_url:
        try:
            parsed = urlparse(auth_url)
            if parsed.netloc and parsed.netloc != request.host:
                return redirect(f'{auth_url}/login')
        except Exception:
            pass
    return redirect(url_for('auth.login'))


# Для разработки - простая форма входа
@auth_bp.route('/dev-login', methods=['GET', 'POST'])
def dev_login():
    """Простая форма входа для разработки"""
    if not current_app.debug:
        return redirect(url_for('auth.login'))
    
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        login = request.form.get('login')
        password = request.form.get('password')
        
        user = User.query.filter_by(login=login).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash(_blocked_account_message(user), 'error')
                return render_template('auth/dev_login.html')
            
            login_user(user, remember=True)
            _issue_sml_session(user)
            flash(f'Добро пожаловать, {user.display_name}!', 'success')
            return redirect(url_for('dashboard.index'))
        
        flash('Неверный логин или пароль', 'error')
    
    return render_template('auth/dev_login.html')


# Создание тестового пользователя для разработки
@auth_bp.route('/dev-setup')
def dev_setup():
    """Создание тестовых данных для разработки"""
    if not current_app.debug:
        return redirect(url_for('auth.login'))
    
    # Проверка, есть ли уже пользователи
    if User.query.count() > 0:
        flash('Тестовые данные уже созданы', 'info')
        return redirect(url_for('auth.dev_login'))
    
    # Создание администратора
    admin = User(
        login='admin',
        email='l.vilyasante@icloud.com',
        name='Администратор',
        role='admin'
    )
    admin.set_password('Admin123!')
    db.session.add(admin)
    
    # Создание артиста
    artist = User(
        login='artist',
        email='artist@example.com',
        name='Тестовый Артист',
        role='artist',
        copyright='© 2026 Тестовый Артист'
    )
    artist.set_password('Artist123!')
    db.session.add(artist)
    
    # Создание лейбла
    label = User(
        login='label',
        email='label@example.com',
        name='Тестовый Лейбл',
        role='label',
        copyright='© 2026 Test Records',
        partner_code='TEST001'
    )
    label.set_password('Label123!')
    db.session.add(label)
    
    # Создание платформ
    from app.models.release import Platform
    for platform_data in Platform.get_default_platforms():
        platform = Platform(**platform_data)
        db.session.add(platform)
    
    db.session.commit()
    
    flash('Тестовые данные созданы. Логины: admin, artist, label. Пароли: Admin123!, Artist123!, Label123!', 'success')
    return redirect(url_for('auth.dev_login'))


@auth_bp.route('/dev-update-admin-email')
def dev_update_admin_email():
    """Обновить email администратора на l.vilyasante@icloud.com (коды подтверждения).
    Доступ: FLASK_DEBUG=1 или однократно ALLOW_UPDATE_ADMIN_EMAIL=1 на продакшене."""
    import os
    if not current_app.debug and os.environ.get('ALLOW_UPDATE_ADMIN_EMAIL') != '1':
        flash('Доступно только в режиме отладки или с ALLOW_UPDATE_ADMIN_EMAIL=1.', 'error')
        return redirect(url_for('auth.login'))
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        flash('Пользователь с ролью admin не найден.', 'error')
        return redirect(url_for('auth.login'))
    old_email = admin.email
    admin.email = _admin_email()
    db.session.commit()
    flash(f'Email администратора обновлён: {old_email} → {_admin_email()}', 'success')
    return redirect(url_for('auth.login'))
