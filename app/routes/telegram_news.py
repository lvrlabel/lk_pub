"""Админ: текстовые новости в Telegram-бот."""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app import csrf
from app.models.telegram_broadcast import TelegramBroadcast
from app.utils.decorators import admin_required
from app.services import telegram_bot

telegram_news_bp = Blueprint('telegram_news', __name__)


@telegram_news_bp.route('/admin/telegram-news', methods=['GET', 'POST'])
@login_required
@admin_required
def index():
    """Форма рассылки и журнал отправок."""
    configured = telegram_bot.is_configured()

    if request.method == 'POST':
        if not configured:
            flash('Telegram-бот не настроен: добавьте TELEGRAM_BOT_TOKEN в .env', 'error')
            return redirect(url_for('telegram_news.index'))

        kind = request.form.get('kind', 'update').strip().lower()
        if kind not in ('outage', 'update'):
            kind = 'update'
        title = request.form.get('title', '').strip()
        text = request.form.get('text', '').strip()

        if not text:
            flash('Введите текст сообщения', 'error')
            return render_template(
                'admin/telegram_news.html',
                configured=configured,
                broadcasts=_recent_broadcasts(),
                subscribers=telegram_bot.profile_linked_count(),
                bot_username=telegram_bot.bot_username(),
                webhook_url=telegram_bot.webhook_url(),
            )

        subs = telegram_bot.profile_linked_count()
        if subs == 0:
            flash(
                'Нет пользователей с привязанным Telegram. Они должны нажать «Привязать» в профиле '
                'и подтвердить Start в боте @'
                + telegram_bot.bot_username(),
                'warning',
            )

        try:
            record = telegram_bot.broadcast_news(
                kind=kind,
                title=title,
                text=text,
                author_id=current_user.id,
            )
        except RuntimeError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('telegram_news.index'))

        if record.recipients_failed and record.recipients_ok:
            flash(
                f'Отправлено {record.recipients_ok} из {record.recipients_ok + record.recipients_failed} подписчикам',
                'warning',
            )
        elif record.recipients_failed and not record.recipients_ok:
            flash('Не удалось доставить сообщение ни одному подписчику', 'error')
        elif record.recipients_ok:
            flash(f'Новость отправлена {record.recipients_ok} подписчикам', 'success')
        else:
            flash('Сообщение сохранено в журнале (подписчиков пока нет)', 'success')

        return redirect(url_for('telegram_news.index'))

    return render_template(
        'admin/telegram_news.html',
        configured=configured,
        broadcasts=_recent_broadcasts(),
        subscribers=telegram_bot.profile_linked_count(),
        bot_username=telegram_bot.bot_username(),
        webhook_url=telegram_bot.webhook_url(),
    )


@telegram_news_bp.route('/admin/telegram-news/set-webhook', methods=['POST'])
@login_required
@admin_required
def set_webhook_route():
    if not telegram_bot.is_configured():
        flash('Telegram-бот не настроен', 'error')
        return redirect(url_for('telegram_news.index'))

    hook = telegram_bot.webhook_url(external=True)
    if not hook:
        flash('Не удалось сформировать URL webhook', 'error')
        return redirect(url_for('telegram_news.index'))

    try:
        telegram_bot.set_webhook(hook)
    except RuntimeError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('telegram_news.index'))

    flash('Webhook зарегистрирован в Telegram', 'success')
    return redirect(url_for('telegram_news.index'))


@telegram_news_bp.route('/telegram/webhook', methods=['POST'])
@telegram_news_bp.route('/telegram/webhook/<secret>', methods=['POST'])
@csrf.exempt
def webhook(secret=None):
    """Webhook Telegram Bot API (/start, /stop)."""
    expected = current_app.config.get('TELEGRAM_WEBHOOK_SECRET')
    if expected and secret != expected:
        return {'ok': False}, 403

    if not telegram_bot.is_configured():
        return {'ok': False}, 503

    try:
        update = request.get_json(force=True, silent=False)
    except Exception:
        return {'ok': False}, 400

    if not isinstance(update, dict):
        return {'ok': False}, 400

    try:
        telegram_bot.handle_webhook_update(update)
    except Exception as exc:
        current_app.logger.warning('telegram webhook: %s', exc)
        return {'ok': False}, 500

    return {'ok': True}


def _recent_broadcasts(limit=20):
    return (
        TelegramBroadcast.query
        .order_by(TelegramBroadcast.created_at.desc())
        .limit(limit)
        .all()
    )
