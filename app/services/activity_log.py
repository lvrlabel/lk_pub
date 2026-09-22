"""
Регистрация действий пользователей (не админов) и просмотр журнала администратором.
"""

from typing import Optional

from flask import request
from sqlalchemy.orm import sessionmaker

from app import db


# Человекочитаемые подписи для частых endpoint'ов (остальные — по шаблону blueprint.имя)
ENDPOINT_LABELS = {
    'auth.login': 'Вход в систему',
    'auth.login_verify': 'Подтверждение входа',
    'auth.login_verify_resend': 'Повтор кода входа',
    'auth.logout': 'Выход из системы',
    'profile.edit': 'Сохранение профиля',
    'profile.change_password': 'Смена пароля',
    'workspace.notes': 'Заметка в пространстве',
    'workspace.tasks': 'Задача в пространстве',
    'workspace.ideas': 'Идея в пространстве',
    'workspace.plans': 'План релиза в пространстве',
    'workspace.calendar': 'Событие календаря',
    'workspace.settings': 'Настройка блоков пространства',
    'notifications.mark_read': 'Отметка уведомления прочитанным',
    'notifications.mark_all_read': 'Все уведомления прочитаны',
    'tickets.create': 'Создание обращения в поддержку',
    'tickets.reply': 'Ответ в тикете',
    'tickets.manager_chat_reply': 'Сообщение в чате с менеджером',
    'tickets.close': 'Закрытие тикета',
    'releases.create': 'Создание релиза',
    'releases.edit': 'Редактирование релиза',
    'releases.submit': 'Отправка релиза на модерацию',
    'releases.delete': 'Удаление релиза',
    'releases.add_track': 'Добавление трека',
    'releases.edit_track': 'Редактирование трека',
    'releases.delete_track': 'Удаление трека',
    'contracts.upload': 'Загрузка документа по договору',
    'contracts.sign_upload': 'Загрузка подписанного договора',
    'money.upload': 'Загрузка финансовых данных',
    'smart_link.create': 'Создание смарт-ссылки',
    'smart_link.edit': 'Редактирование смарт-ссылки',
    'stories.create': 'Публикация новости',
    'stories.edit': 'Редактирование новости',
    'tools.auto_form_submit': 'Отправка автоформы',
    'labels.create': 'Создание лейбла',
    'labels.edit': 'Редактирование лейбла',
    'knowledge.rate_article': 'Оценка статьи базы знаний',
}


def _client_ip():
    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        return xff.split(',')[0].strip()[:45]
    return (request.remote_addr or '')[:45]


def _format_view_args() -> str:
    va = getattr(request, 'view_args', None) or {}
    if not va:
        return ''
    parts = [f'{k}={v}' for k, v in sorted(va.items())]
    return ', '.join(parts)[:200]


def build_activity_summary(endpoint: Optional[str]) -> str:
    ep = endpoint or ''
    label = ENDPOINT_LABELS.get(ep)
    extra = _format_view_args()
    if label:
        return f'{label} ({extra})' if extra else label
    if ep:
        tail = f' ({extra})' if extra else ''
        return ep + tail
    return 'Действие в кабинете'


def _current_sml_session_id() -> Optional[str]:
    try:
        from flask import g, has_request_context, session as flask_session

        if not has_request_context():
            return None
        row = getattr(g, 'sml_session', None)
        if row is not None and getattr(row, 'session_id', None):
            return str(row.session_id)[:64]
        sid = flask_session.get('sml_session_id')
        return str(sid)[:64] if sid else None
    except Exception:
        return None


def record_user_activity_event(
    user_id: int,
    method: str,
    endpoint: Optional[str],
    path: str,
    status_code: int | None,
    summary: str | None = None,
    session_id: str | None = None,
):
    """Сохранить событие в отдельной сессии БД (не смешивается с транзакцией запроса)."""
    from app.models.user_activity_log import UserActivityLog

    Session = sessionmaker(bind=db.engine)
    session = Session()
    try:
        sid = (session_id or _current_sml_session_id() or '')[:64] or None
        row = UserActivityLog(
            user_id=user_id,
            method=(method or '')[:8],
            endpoint=(endpoint or '')[:160] if endpoint else None,
            path=(path or '')[:512],
            status_code=status_code,
            summary=(summary or '')[:512] if summary else None,
            ip_address=_client_ip(),
            session_id=sid,
        )
        session.add(row)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def register_user_activity_logger(app):
    """Логирование POST/PUT/PATCH/DELETE от пользователей с ролями artist/label."""

    @app.after_request
    def _log_user_activity(response):
        try:
            if request.method == 'OPTIONS':
                return response
            path = request.path or ''
            if path.startswith('/static'):
                return response

            from flask_login import current_user

            if not current_user.is_authenticated:
                return response
            if getattr(current_user, 'is_admin', False):
                return response
            role = getattr(current_user, 'role', '') or ''
            if role == 'admin':
                return response

            if response.status_code >= 400:
                return response

            method = request.method
            if method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
                return response

            endpoint = request.endpoint or ''
            if endpoint == 'admin.user_activity':
                return response

            summary = build_activity_summary(endpoint)
            record_user_activity_event(
                user_id=current_user.id,
                method=method,
                endpoint=endpoint,
                path=path,
                status_code=response.status_code,
                summary=summary,
            )
        except Exception:
            pass
        return response
