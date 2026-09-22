"""
Личный кабинет toolls-muisic-distribution.ru
Фабрика Flask-приложения
"""

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

# Инициализация расширений
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_name=None):
    """Фабрика приложения"""
    app = Flask(__name__, instance_relative_config=True)
    
    # Загрузка конфигурации
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    from app.config import config
    if config_name not in config:
        config_name = 'development'
    app.config.from_object(config[config_name])
    if config_name == 'production' and not app.config.get('SQLALCHEMY_DATABASE_URI'):
        raise ValueError('DATABASE_URL обязателен для production')
    
    # В production за прокси: доверяем X-Forwarded-Host/Proto, чтобы url_for(..., _external=True) давал основной домен (toolls-muisic-distribution.ru)
    if config_name == 'production':
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # Создание директории instance
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Для SQLite: гарантированно создаём папку с БД (на shared-хостинге часто отсутствует)
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_uri.startswith('sqlite:///'):
        path_part = db_uri.replace('sqlite:///', '')
        if path_part and path_part != ':memory:':
            db_dir = os.path.dirname(path_part)
            if db_dir:
                try:
                    os.makedirs(db_dir, exist_ok=True)
                except OSError as e:
                    raise RuntimeError(
                        f'Не удалось создать папку для БД: {db_dir}. '
                        f'Проверьте права доступа. Ошибка: {e}'
                    ) from e
    
    # Создание директорий для загрузок
    upload_dirs = [
        'uploads/covers',
        'uploads/tracks',
        'uploads/avatars',
        'uploads/news_covers',
        'uploads/finances',
        'uploads/contracts/original',
        'uploads/contracts/signed',
        'uploads/ticket_attachments',
        'uploads/workspace',
        'uploads/documents/payment_confirmations',
    ]
    for directory in upload_dirs:
        dir_path = os.path.join(app.root_path, '..', directory)
        os.makedirs(dir_path, exist_ok=True)
    
    # Инициализация расширений
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.utils.email import init_mail
    init_mail(app)
    
    # Настройка Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите в систему'
    login_manager.login_message_category = 'warning'
    
    # Загрузчик пользователя
    from app.models.user import User
    
    @login_manager.user_loader
    def load_user(user_id):
        if user_id is None:
            return None
        try:
            return db.session.get(User, int(user_id))
        except (ValueError, TypeError):
            return None
    
    # Регистрация blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.releases import releases_bp
    from app.routes.moderation import moderation_bp
    from app.routes.money import money_bp
    from app.routes.smart_link import smart_link_bp
    from app.routes.stories import stories_bp
    from app.routes.tickets import tickets_bp
    from app.routes.knowledge import knowledge_bp
    from app.routes.tools import tools_bp
    from app.routes.notifications import notifications_bp
    from app.routes.contracts import contracts_bp
    from app.routes.users import users_bp
    from app.routes.labels import labels_bp
    from app.routes.profile import profile_bp
    from app.routes.admin import admin_bp
    from app.routes.stats import stats_bp
    from app.routes.ringtones_video import ringtones_video_bp
    from app.routes.service_updates import service_updates_bp
    from app.routes.telegram_news import telegram_news_bp
    from app.routes.workspace import workspace_bp
    from app.routes.documents import documents_bp
    from app.routes.community import community_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(releases_bp)
    app.register_blueprint(moderation_bp)
    app.register_blueprint(money_bp)
    app.register_blueprint(smart_link_bp)
    app.register_blueprint(stories_bp)
    app.register_blueprint(tickets_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(contracts_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(labels_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(ringtones_video_bp)
    app.register_blueprint(service_updates_bp)
    app.register_blueprint(telegram_news_bp)
    app.register_blueprint(workspace_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(community_bp)

    # Обработчики ошибок
    from app.utils.errors import register_error_handlers
    register_error_handlers(app)

    from app.services.activity_log import register_user_activity_logger
    register_user_activity_logger(app)

    from app.services.session_manager import register_sml_middleware
    register_sml_middleware(app)

    @app.before_request
    def _run_billing_tasks_if_due():
        try:
            from app.services.billing_scheduler import run_billing_tasks_if_due
            run_billing_tasks_if_due()
        except Exception:
            pass
    
    # Контекстный процессор для шаблонов
    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from flask import request
        from flask_login import current_user
        from app.utils.user_popup_notice import page_scope_for_endpoint, popups_for_user
        data = {
            'current_year': datetime.now().year,
            'current_quarter': (datetime.now().month - 1) // 3 + 1
        }
        if current_user.is_authenticated:
            data['unread_notifications_count'] = 0
            data['total_notifications_count'] = 0
            data['header_notifications'] = []
            try:
                from app.models.notification import Notification
                data['unread_notifications_count'] = Notification.query.filter_by(
                    user_id=current_user.id, is_read=False
                ).count()
                data['total_notifications_count'] = Notification.query.filter_by(
                    user_id=current_user.id
                ).count()
                data['header_notifications'] = (
                    Notification.query.filter_by(user_id=current_user.id)
                    .order_by(Notification.created_at.desc())
                    .limit(12)
                    .all()
                )
            except Exception:
                pass
        else:
            data['unread_notifications_count'] = 0
            data['total_notifications_count'] = 0
            data['header_notifications'] = []
        data['manager_chat_unread_count'] = 0
        data['sidebar_moderation_count'] = 0
        data['service_updates_unread_count'] = 0
        data['manager_chat_enabled'] = app.config.get('MANAGER_CHAT_ENABLED', False)
        if current_user.is_authenticated and getattr(current_user, 'is_admin', False):
            try:
                from app.models.release import Release
                data['sidebar_moderation_count'] = Release.query.filter_by(status='moderation').count()
            except Exception:
                pass
        if current_user.is_authenticated and data['manager_chat_enabled']:
            try:
                from app.services.manager_chat_unread import total_unread_for_viewer

                data['manager_chat_unread_count'] = total_unread_for_viewer(current_user)
            except Exception:
                pass
        if current_user.is_authenticated:
            try:
                from app.services.service_updates import unread_service_updates_count
                data['service_updates_unread_count'] = unread_service_updates_count(current_user.id)
            except Exception:
                pass
        # Всегда задаём has_endpoint до любых других обращений к БД в шаблонах
        def _has_endpoint(name):
            try:
                return name in app.view_functions
            except Exception:
                return False
        data['has_endpoint'] = _has_endpoint
        data['user_popups'] = []
        data['releases_restricted'] = False
        if current_user.is_authenticated:
            data['releases_restricted'] = bool(getattr(current_user, 'is_releases_restricted', False))
            try:
                page_scope = page_scope_for_endpoint(request.endpoint)
                if page_scope:
                    popups = popups_for_user(current_user, page_scope)
                    restriction_popup = current_user.releases_restriction_popup()
                    if restriction_popup:
                        popups = [restriction_popup] + popups
                    data['user_popups'] = popups
            except Exception:
                pass
        from app.utils.support_chat_timeline import build_support_chat_timeline

        def _build_support_chat_timeline(ticket, messages):
            if not current_user.is_authenticated:
                return []
            return build_support_chat_timeline(ticket, messages, current_user.is_admin)

        data['build_support_chat_timeline'] = _build_support_chat_timeline
        return data
    
    # Кастомные фильтры Jinja2
    @app.template_filter('intcomma')
    def intcomma_filter(value):
        """Форматирование числа с разделителями тысяч (пробелы)."""
        if value is None:
            return ''
        try:
            return f"{int(value):,}".replace(",", " ")
        except (ValueError, TypeError):
            return str(value)
    
    # Создание таблиц БД
    with app.app_context():
        from app.models.knowledge_article import KnowledgeArticle  # noqa: F401
        from app.models.knowledge_section import KnowledgeSection  # noqa: F401
        from app.models.knowledge_topic import KnowledgeTopic  # noqa: F401
        from app.models.finance import FinancePlatformLine  # noqa: F401
        from app.models.invoice import Invoice, PaymentConfirmation, DocNotification  # noqa: F401
        from app.models.social_account import SocialAccount  # noqa: F401
        from app.models.user_activity_log import UserActivityLog  # noqa: F401
        from app.models.user_session import UserSession, SessionEvent  # noqa: F401
        from app.models.workspace import (  # noqa: F401
            WorkspaceLayout,
            WorkspaceNote,
            WorkspaceTask,
            WorkspaceIdea,
            WorkspaceReleasePlan,
            WorkspaceCalendarEvent,
        )
        from app.models.release_event import ReleaseEvent  # noqa: F401
        from app.models.service_update import ServiceUpdate, ServiceUpdateRead  # noqa: F401
        from app.models.telegram_broadcast import TelegramBroadcast, TelegramSubscriber  # noqa: F401
        from app.models.bonus import BonusTransaction  # noqa: F401
        from app.models.community import (  # noqa: F401
            CommunityMessage,
            Story,
            StoryComment,
            StoryReaction,
        )
        try:
            db.create_all()
        except Exception as e:
            app.logger.warning('db.create_all(): %s', e)
        try:
            from app.services.service_updates import sync_service_updates_from_manifest
            synced = sync_service_updates_from_manifest(app)
            if synced:
                app.logger.info('service_updates manifest: synced %s', synced)
        except Exception as e:
            app.logger.warning('sync_service_updates_from_manifest: %s', e)
        try:
            from app.utils.knowledge_migrate import run_knowledge_migrations
            run_knowledge_migrations(app)
        except Exception as e:
            app.logger.warning('run_knowledge_migrations: %s', e)
        _ensure_knowledge_article_topic_id_column(app)
        _ensure_contract_rejection_reason_column(app)
        _ensure_contract_signing_columns(app)
        _ensure_auto_form_columns(app)
        _ensure_video_request_columns(app)
        _ensure_user_phone_column(app)
        _ensure_user_telegram_columns(app)
        _ensure_user_tax_profile_columns(app)
        _ensure_user_block_reason_column(app)
        _ensure_user_releases_restriction_columns(app)
        _ensure_user_bonus_balance_column(app)
        _ensure_user_subscription_columns(app)
        _ensure_invoice_billing_columns(app)
        _ensure_notification_release_id_column(app)
        _ensure_ticket_workflow_columns(app)
        _ensure_manager_chat_read_columns(app)
        _ensure_tracks_isrc_column_length(app)
        _ensure_user_activity_session_id_column(app)
        _ensure_workspace_layout_theme_column(app)
        _ensure_community_message_media_columns(app)
        _ensure_community_message_reply_column(app)

    return app


def _ensure_workspace_layout_theme_column(app):
    """Тема оформления Моего пространства."""
    from sqlalchemy import text

    try:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE workspace_layouts ADD COLUMN theme_json TEXT'))
            conn.commit()
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' in msg or 'already exists' in msg:
            pass
        else:
            app.logger.warning('_ensure_workspace_layout_theme_column: %s', e)


def _ensure_community_message_media_columns(app):
    """Медиа-поля общего чата для уже существующих баз данных."""
    from sqlalchemy import text

    for sql in (
        'ALTER TABLE community_messages ADD COLUMN media VARCHAR(256)',
        'ALTER TABLE community_messages ADD COLUMN media_type VARCHAR(16)',
    ):
        try:
            with db.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception as e:
            msg = str(e).lower()
            if 'duplicate column' not in msg and 'already exists' not in msg:
                app.logger.warning('_ensure_community_message_media_columns: %s', e)


def _ensure_community_message_reply_column(app):
    """Связь ответа с исходным сообщением общего чата."""
    from sqlalchemy import text

    try:
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE community_messages ADD COLUMN reply_to_id INTEGER'))
            conn.commit()
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' not in msg and 'already exists' not in msg:
            app.logger.warning('_ensure_community_message_reply_column: %s', e)


def _ensure_user_activity_session_id_column(app):
    """SML: привязка журнала действий к sessionId."""
    from sqlalchemy import text

    statements = [
        'ALTER TABLE user_activity_logs ADD COLUMN session_id VARCHAR(64)',
    ]
    for sql in statements:
        try:
            with db.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception as e:
            msg = str(e).lower()
            if 'duplicate column' in msg or 'already exists' in msg:
                pass
            else:
                app.logger.warning('_ensure_user_activity_session_id_column: %s', e)


def _ensure_user_subscription_columns(app):
    """Подписка: тариф и срок действия."""
    from sqlalchemy import text

    statements = [
        'ALTER TABLE users ADD COLUMN subscription_plan VARCHAR(64)',
        'ALTER TABLE users ADD COLUMN subscription_expires_at DATETIME',
        'ALTER TABLE users ADD COLUMN subscription_reminder_sent_at DATETIME',
    ]
    for sql in statements:
        try:
            with db.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception as e:
            msg = str(e).lower()
            if 'duplicate column' in msg or 'already exists' in msg:
                pass
            else:
                app.logger.warning('Миграция users subscription: %s — %s', sql[:48], e)


def _ensure_invoice_billing_columns(app):
    """Счета: тариф и отметка о просрочке."""
    from sqlalchemy import text

    statements = [
        'ALTER TABLE invoices ADD COLUMN plan_code VARCHAR(32)',
        'ALTER TABLE invoices ADD COLUMN overdue_notified_at DATETIME',
        'ALTER TABLE invoices ADD COLUMN yookassa_invoice_id VARCHAR(128)',
    ]
    for sql in statements:
        try:
            with db.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception as e:
            msg = str(e).lower()
            if 'duplicate column' in msg or 'already exists' in msg:
                pass
            else:
                app.logger.warning('Миграция invoices billing: %s — %s', sql[:48], e)


def _ensure_user_bonus_balance_column(app):
    """Баланс бонусной программы в users."""
    from sqlalchemy import text

    statements = [
        'ALTER TABLE users ADD COLUMN bonus_balance INTEGER DEFAULT 0 NOT NULL',
    ]
    for sql in statements:
        try:
            with db.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception as e:
            msg = str(e).lower()
            if 'duplicate column' in msg or 'already exists' in msg:
                pass
            else:
                app.logger.warning('Миграция users bonus_balance: %s — %s', sql[:48], e)


def _ensure_tracks_isrc_column_length(app):
    """Расширить tracks.isrc до VARCHAR(128) в MySQL/PostgreSQL (SQLite не ограничивает длину)."""
    try:
        from sqlalchemy import inspect, text

        dialect = db.engine.dialect.name
        if dialect not in ('mysql', 'postgresql', 'mariadb'):
            return
        insp = inspect(db.engine)
        if 'tracks' not in insp.get_table_names():
            return
        if dialect in ('mysql', 'mariadb'):
            with db.engine.begin() as conn:
                conn.execute(
                    text('ALTER TABLE tracks MODIFY COLUMN isrc VARCHAR(128) NULL')
                )
        elif dialect == 'postgresql':
            with db.engine.begin() as conn:
                conn.execute(
                    text('ALTER TABLE tracks ALTER COLUMN isrc TYPE VARCHAR(128)')
                )
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate' in msg or 'same' in msg or 'no change' in msg:
            pass
        else:
            app.logger.warning('Миграция tracks.isrc VARCHAR(128): %s', e)


def _ensure_notification_release_id_column(app):
    """Колонка release_id в notifications для уведомлений по релизам."""
    try:
        from sqlalchemy import inspect, text

        insp = inspect(db.engine)
        tables = insp.get_table_names()
        if 'notifications' not in tables:
            return
        cols = {c['name'] for c in insp.get_columns('notifications')}
        if 'release_id' in cols:
            return
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE notifications ADD COLUMN release_id INTEGER'))
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' in msg or 'already exists' in msg or 'release_id' in msg:
            pass
        else:
            app.logger.warning('Миграция notifications.release_id: %s', e)


def _ensure_ticket_workflow_columns(app):
    """Поля created_by_admin_id, initiator, priority и статусы переписки."""
    try:
        from sqlalchemy import inspect, text

        insp = inspect(db.engine)
        if 'tickets' not in insp.get_table_names():
            return
        cols = {c['name'] for c in insp.get_columns('tickets')}
        dialect = db.engine.dialect.name

        with db.engine.begin() as conn:
            if 'created_by_admin_id' not in cols:
                conn.execute(text('ALTER TABLE tickets ADD COLUMN created_by_admin_id INTEGER'))
            if 'initiator' not in cols:
                conn.execute(
                    text("ALTER TABLE tickets ADD COLUMN initiator VARCHAR(10) DEFAULT 'user'")
                )
            if 'priority' not in cols:
                conn.execute(
                    text("ALTER TABLE tickets ADD COLUMN priority VARCHAR(20) DEFAULT 'normal'")
                )
            if 'category' not in cols:
                conn.execute(
                    text("ALTER TABLE tickets ADD COLUMN category VARCHAR(32) DEFAULT 'general' NOT NULL")
                )

            conn.execute(
                text(
                    "UPDATE tickets SET initiator = 'user' "
                    "WHERE initiator IS NULL OR initiator = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE tickets SET priority = 'normal' "
                    "WHERE priority IS NULL OR priority = ''"
                )
            )
            conn.execute(
                text(
                    "UPDATE tickets SET category = 'general' "
                    "WHERE category IS NULL OR category = ''"
                )
            )

            if dialect in ('mysql', 'mariadb'):
                try:
                    conn.execute(
                        text(
                            'ALTER TABLE tickets MODIFY COLUMN status VARCHAR(32) NOT NULL'
                        )
                    )
                except Exception:
                    pass
            elif dialect == 'postgresql':
                try:
                    conn.execute(
                        text('ALTER TABLE tickets ALTER COLUMN status TYPE VARCHAR(32)')
                    )
                except Exception:
                    pass

            conn.execute(
                text("UPDATE tickets SET status = 'waiting_for_admin' WHERE status = 'open'")
            )
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate' in msg and 'column' in msg:
            pass
        else:
            app.logger.warning('Миграция tickets workflow: %s', e)


def _ensure_manager_chat_read_columns(app):
    """Поля «последний просмотр» персонального чата для счётчика непрочитанных."""
    try:
        from sqlalchemy import inspect, text

        insp = inspect(db.engine)
        if 'tickets' not in insp.get_table_names():
            return
        cols = {c['name'] for c in insp.get_columns('tickets')}
        dialect = db.engine.dialect.name
        if dialect == 'postgresql':
            col_type = 'TIMESTAMP WITHOUT TIME ZONE'
        else:
            col_type = 'DATETIME'
        with db.engine.begin() as conn:
            if 'manager_chat_read_by_user_at' not in cols:
                conn.execute(
                    text(
                        f'ALTER TABLE tickets ADD COLUMN manager_chat_read_by_user_at {col_type} NULL'
                    )
                )
            if 'manager_chat_read_by_admin_at' not in cols:
                conn.execute(
                    text(
                        f'ALTER TABLE tickets ADD COLUMN manager_chat_read_by_admin_at {col_type} NULL'
                    )
                )
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate' in msg and 'column' in msg:
            pass
        elif 'already exists' in msg:
            pass
        else:
            app.logger.warning('Миграция tickets manager_chat_read: %s', e)


def _ensure_knowledge_article_topic_id_column(app):
    """Таблица knowledge_topics + колонка topic_id у статей (подразделы / вкладки)."""
    try:
        from sqlalchemy import inspect, text

        insp = inspect(db.engine)
        tables = insp.get_table_names()
        if 'knowledge_articles' not in tables:
            return
        cols = {c['name'] for c in insp.get_columns('knowledge_articles')}
        if 'topic_id' in cols:
            return
        with db.engine.begin() as conn:
            conn.execute(
                text(
                    'ALTER TABLE knowledge_articles ADD COLUMN topic_id INTEGER NULL'
                )
            )
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' in msg or 'already exists' in msg or 'topic_id' in msg:
            pass
        else:
            app.logger.warning('Миграция knowledge_articles.topic_id: %s', e)


def _ensure_contract_rejection_reason_column(app):
    """Добавить колонку rejection_reason в contracts, если её ещё нет (миграция без Flask-Migrate)."""
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE contracts ADD COLUMN rejection_reason TEXT"))
            conn.commit()
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' in msg or 'already exists' in msg or 'rejection_reason' in msg:
            pass
        else:
            app.logger.warning('Миграция contracts.rejection_reason: %s', e)


def _ensure_contract_signing_columns(app):
    """Добавить поля электронного договора без Flask-Migrate."""
    columns = (
        ('contract_body', 'TEXT'),
        ('contract_type', "VARCHAR(20) NOT NULL DEFAULT 'file'"),
        ('signing_code_hash', 'VARCHAR(256)'),
        ('signing_code_expires_at', 'DATETIME'),
        ('signing_code_sent_at', 'DATETIME'),
        ('signed_ip', 'VARCHAR(64)'),
        ('signed_user_agent', 'VARCHAR(512)'),
    )
    try:
        from sqlalchemy import inspect, text
        existing = {column['name'] for column in inspect(db.engine).get_columns('contracts')}
        with db.engine.begin() as conn:
            for name, definition in columns:
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE contracts ADD COLUMN {name} {definition}'))
    except Exception as e:
        app.logger.warning('Миграция полей электронного договора: %s', e)


def _ensure_auto_form_columns(app):
    """Добавить колонку artist_name в auto_form_requests, если её ещё нет."""
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE auto_form_requests ADD COLUMN artist_name VARCHAR(256)"))
            conn.commit()
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' in msg or 'already exists' in msg or 'artist_name' in msg:
            pass
        else:
            app.logger.warning('Миграция auto_form_requests.artist_name: %s', e)


def _ensure_user_tax_profile_columns(app):
    """Колонки налоговой и платёжной информации в users."""
    from sqlalchemy import text

    statements = [
        "ALTER TABLE users ADD COLUMN tax_status VARCHAR(32)",
        "ALTER TABLE users ADD COLUMN tax_legal_name VARCHAR(512)",
        "ALTER TABLE users ADD COLUMN tax_inn VARCHAR(12)",
        "ALTER TABLE users ADD COLUMN tax_bank_account VARCHAR(32)",
        "ALTER TABLE users ADD COLUMN tax_bank_name VARCHAR(256)",
        "ALTER TABLE users ADD COLUMN tax_bank_bik VARCHAR(9)",
    ]
    for sql in statements:
        try:
            with db.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception as e:
            msg = str(e).lower()
            if 'duplicate column' in msg or 'already exists' in msg:
                pass
            else:
                app.logger.warning('Миграция users tax: %s — %s', sql[:50], e)


def _ensure_user_phone_column(app):
    """Добавить колонку phone в users, если её ещё нет (для SMS-кодов авторизации)."""
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(20)"))
            conn.commit()
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' in msg or 'already exists' in msg or 'phone' in msg:
            pass
        else:
            app.logger.warning('Миграция users.phone: %s', e)


def _ensure_user_telegram_columns(app):
    """Telegram: username, chat_id, токен привязки из профиля."""
    from sqlalchemy import text

    statements = [
        'ALTER TABLE users ADD COLUMN telegram_username VARCHAR(64)',
        'ALTER TABLE users ADD COLUMN telegram_chat_id BIGINT',
        'ALTER TABLE users ADD COLUMN telegram_link_token VARCHAR(48)',
    ]
    for sql in statements:
        try:
            with db.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception as e:
            msg = str(e).lower()
            if 'duplicate column' in msg or 'already exists' in msg:
                continue
            app.logger.warning('Миграция users telegram: %s — %s', sql[:48], e)


def _ensure_user_block_reason_column(app):
    """Текст причины блокировки учётной записи (для экрана входа)."""
    try:
        from sqlalchemy import text

        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE users ADD COLUMN block_reason TEXT'))
            conn.commit()
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' in msg or 'already exists' in msg or 'block_reason' in msg:
            pass
        else:
            app.logger.warning('Миграция users.block_reason: %s', e)


def _ensure_user_releases_restriction_columns(app):
    """Ограничение релизов и текст уведомления для пользователя."""
    from sqlalchemy import text

    statements = [
        'ALTER TABLE users ADD COLUMN releases_restricted BOOLEAN DEFAULT 0 NOT NULL',
        'ALTER TABLE users ADD COLUMN releases_restriction_title VARCHAR(200)',
        'ALTER TABLE users ADD COLUMN releases_restriction_message TEXT',
    ]
    for sql in statements:
        try:
            with db.engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception as e:
            msg = str(e).lower()
            if 'duplicate column' in msg or 'already exists' in msg:
                pass
            else:
                app.logger.warning('Миграция users releases restriction: %s — %s', sql[:48], e)


def _ensure_video_request_columns(app):
    """Добавить колонки service_type и lyrics_text в video_requests, если их ещё нет."""
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE video_requests ADD COLUMN service_type VARCHAR(20) DEFAULT 'video'"))
            conn.commit()
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' in msg or 'already exists' in msg or 'service_type' in msg:
            pass
        else:
            app.logger.warning('Миграция video_requests.service_type: %s', e)
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE video_requests ADD COLUMN lyrics_text TEXT"))
            conn.commit()
    except Exception as e:
        msg = str(e).lower()
        if 'duplicate column' in msg or 'already exists' in msg or 'lyrics_text' in msg:
            pass
        else:
            app.logger.warning('Миграция video_requests.lyrics_text: %s', e)
