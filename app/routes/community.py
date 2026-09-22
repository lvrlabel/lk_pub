"""
Сообщество артистов: общий чат и сторис с реакциями и комментариями.
"""

import json
import os
import time
from time import monotonic
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from app import db
from app.models.community import CommunityMessage, Story, StoryComment, StoryReaction
from app.models.notification import Notification
from app.models.user import User
from app.utils.files import allowed_file, delete_file, save_file

community_bp = Blueprint('community', __name__)

# --- Вспомогательные функции -------------------------------------------------

COMMUNITY_CHAT_MIN_INTERVAL = 2.0  # секунд между сообщениями пользователя
STORIES_PER_DAY_LIMIT = 5
COMMUNITY_TYPING_TTL = 4.0
_community_typing = {}


def _notify(user_id, kind, title, message=None):
    """Создать уведомление пользователю (тихо при ошибке)."""
    if not user_id or user_id == current_user.id:
        return
    try:
        db.session.add(
            Notification(user_id=user_id, kind=kind, title=title, message=message)
        )
    except Exception:
        pass


def _last_message_ts(user_id):
    msg = (
        CommunityMessage.query.filter_by(user_id=user_id)
        .order_by(CommunityMessage.created_at.desc())
        .first()
    )
    return msg.created_at if msg else None


# --- Чат сообщества ----------------------------------------------------------

@community_bp.route('/community')
@login_required
def chat():
    """Общий чат артистов."""
    messages = (
        CommunityMessage.query.order_by(CommunityMessage.created_at.desc())
        .limit(100)
        .all()
    )
    messages = list(reversed(messages))
    return render_template('community/chat.html', messages=messages)


@community_bp.route('/community/send', methods=['POST'])
@login_required
def send_message():
    """Отправить сообщение в общий чат (с защитой от спама)."""
    text = (request.form.get('text') or '').strip()
    if not text:
        flash('Сообщение не может быть пустым', 'error')
        return redirect(url_for('community.chat'))
    if len(text) > 1000:
        flash('Сообщение слишком длинное (максимум 1000 символов)', 'error')
        return redirect(url_for('community.chat'))

    reply_to_id = request.form.get('reply_to_id', type=int)
    if reply_to_id and not CommunityMessage.query.filter_by(id=reply_to_id).first():
        reply_to_id = None

    last = _last_message_ts(current_user.id)
    if last and (datetime.utcnow() - last).total_seconds() < COMMUNITY_CHAT_MIN_INTERVAL:
        flash('Не спамьте: подождите пару секунд между сообщениями', 'warning')
        return redirect(url_for('community.chat'))

    db.session.add(CommunityMessage(user_id=current_user.id, text=text, reply_to_id=reply_to_id))
    db.session.commit()
    return redirect(url_for('community.chat'))


@community_bp.route('/community/send-media', methods=['POST'])
@login_required
def send_media_message():
    """Сохранить голосовое или видео-сообщение общего чата."""
    media_file = request.files.get('media')
    media_type = (request.form.get('media_type') or '').strip().lower()
    allowed = {'webm', 'mp4', 'ogg', 'wav', 'mp3', 'm4a', 'mov'}
    media_mime = (media_file.mimetype or '').split(';', 1)[0].strip().lower() if media_file else ''
    if media_type not in {'audio', 'video'} or not media_file or not media_file.filename:
        flash('Не удалось определить медиа-сообщение', 'error')
        return redirect(url_for('community.chat'))
    if not allowed_file(media_file.filename, allowed, media_mime):
        flash('Недопустимый формат аудио или видео', 'error')
        return redirect(url_for('community.chat'))

    media_file.stream.seek(0, 2)
    size = media_file.stream.tell()
    media_file.stream.seek(0)
    max_size = int(current_app.config.get('MAX_NEWS_COVER_SIZE', 5 * 1024 * 1024))
    if size > max_size:
        flash('Медиа-сообщение слишком большое (максимум 5 МБ)', 'error')
        return redirect(url_for('community.chat'))

    filename = save_file(media_file, 'community', allowed_extensions=allowed, mime_type=media_mime)
    if not filename:
        flash('Не удалось сохранить медиа-сообщение', 'error')
        return redirect(url_for('community.chat'))
    reply_to_id = request.form.get('reply_to_id', type=int)
    if reply_to_id and not CommunityMessage.query.filter_by(id=reply_to_id).first():
        reply_to_id = None
    db.session.add(CommunityMessage(user_id=current_user.id, text='', media=filename, media_type=media_type, reply_to_id=reply_to_id))
    db.session.commit()
    return redirect(url_for('community.chat'))


@community_bp.route('/uploads/community/<path:filename>')
@login_required
def serve_community_media(filename):
    safe_name = filename.split('/')[-1]
    if safe_name != filename:
        abort(404)
    path = os.path.join(current_app.root_path, '..', 'uploads', 'community', safe_name)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, conditional=True)


@community_bp.route('/community/api/typing', methods=['POST'])
@login_required
def api_typing():
    """Обновить временный статус набора текста без записи в БД."""
    is_typing = request.get_json(silent=True) or {}
    if bool(is_typing.get('typing')):
        _community_typing[current_user.id] = (current_user.display_name, monotonic())
    else:
        _community_typing.pop(current_user.id, None)
    return jsonify({'ok': True})


@community_bp.route('/community/api/typing')
@login_required
def api_typing_status():
    now = monotonic()
    active = [
        name for user_id, (name, timestamp) in list(_community_typing.items())
        if user_id != current_user.id and now - timestamp < COMMUNITY_TYPING_TTL
    ]
    for user_id, (_, timestamp) in list(_community_typing.items()):
        if now - timestamp >= COMMUNITY_TYPING_TTL:
            _community_typing.pop(user_id, None)
    return jsonify({'users': active[:3]})


@community_bp.route('/community/api/messages')
@login_required
def api_messages():
    """Новые сообщения чата для автообновления (?after_id=N)."""
    after_id = request.args.get('after_id', 0, type=int)
    query = CommunityMessage.query
    if after_id:
        query = query.filter(CommunityMessage.id > after_id)
    messages = query.order_by(CommunityMessage.id.asc()).limit(50).all()
    return jsonify(
        {
            'messages': [m.to_dict() for m in messages],
            'now': datetime.utcnow().isoformat(),
        }
    )


# --- Сторис ------------------------------------------------------------------

@community_bp.route('/community/stories')
@login_required
def stories():
    """Лента активных сторис всех артистов."""
    active = Story.active_query().all()
    my_today_count = (
        Story.query.filter(
            Story.user_id == current_user.id,
            Story.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0),
        ).count()
    )
    return render_template(
        'community/stories.html',
        stories=active,
        my_today_count=my_today_count,
        stories_per_day_limit=STORIES_PER_DAY_LIMIT,
        StoryComment=StoryComment,
    )


@community_bp.route('/community/stories/create', methods=['POST'])
@login_required
def stories_create():
    """Создать сторис: изображение + подпись. Не чаще 5 в день."""
    caption = (request.form.get('caption') or '').strip()[:500]

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
    today_count = Story.query.filter(
        Story.user_id == current_user.id,
        Story.created_at >= today_start,
    ).count()
    if today_count >= STORIES_PER_DAY_LIMIT:
        flash(f'Достигнут дневной лимит сторис ({STORIES_PER_DAY_LIMIT} в день)', 'error')
        return redirect(url_for('community.stories'))

    media_file = request.files.get('media')
    if not media_file or not media_file.filename:
        flash('Прикрепите медиафайл к сторис', 'error')
        return redirect(url_for('community.stories'))

    media_mime = (media_file.mimetype or '').split(';', 1)[0].strip().lower()
    allowed = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mov', 'webm', 'avi', 'm4v', 'mkv'}
    if not allowed_file(media_file.filename, allowed, media_mime):
        flash('Недопустимый формат медиа. Разрешены: JPG, PNG, GIF, WebP, MP4, MOV, WebM, AVI', 'error')
        return redirect(url_for('community.stories'))

    media_kind = 'image' if media_mime.startswith('image/') else 'video'
    max_size = int(current_app.config.get('MAX_NEWS_COVER_SIZE', 5 * 1024 * 1024))
    media_file.stream.seek(0, 2)
    size = media_file.stream.tell()
    media_file.stream.seek(0)
    if size > max_size:
        flash('Файл слишком большой (максимум 5 МБ)', 'error')
        return redirect(url_for('community.stories'))

    filename = save_file(media_file, 'stories', allowed_extensions=allowed, mime_type=media_mime)
    if not filename:
        flash('Не удалось сохранить медиафайл. Попробуйте ещё раз.', 'error')
        return redirect(url_for('community.stories'))

    story = Story(
        user_id=current_user.id,
        media=filename,
        media_type=media_kind,
        caption=caption or None,
        expires_at=Story.default_expires_at(),
    )
    db.session.add(story)
    db.session.commit()
    flash('Сторис опубликована! Она будет доступна 24 часа.', 'success')
    return redirect(url_for('community.stories'))


@community_bp.route('/uploads/stories/<path:filename>')
@login_required
def serve_story_media(filename):
    """Отдача файлов сторис из uploads/stories."""
    safe_name = filename.split('/')[-1]
    if safe_name != filename:
        abort(404)

    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', 'stories')
    path = os.path.join(upload_folder, safe_name)
    if not os.path.isfile(path):
        abort(404)

    return send_file(path, conditional=True)


@community_bp.route('/community/stories/<int:story_id>/react', methods=['POST'])
@login_required
def stories_react(story_id):
    """Поставить или снять сердечко."""
    story = Story.query.get_or_404(story_id)
    if story.is_expired:
        flash('Эта сторис уже недоступна', 'warning')
        return redirect(url_for('community.stories'))

    reaction = StoryReaction.query.filter_by(
        story_id=story.id, user_id=current_user.id
    ).first()
    if reaction:
        db.session.delete(reaction)
        db.session.commit()
        return redirect(url_for('community.stories'))

    db.session.add(
        StoryReaction(story_id=story.id, user_id=current_user.id, reaction='heart')
    )
    db.session.commit()
    _notify(
        story.user_id,
        'story_reaction',
        'Вашей сторис поставили сердечко ❤️',
        f'{current_user.display_name} отметил(а) вашу сторис.',
    )
    db.session.commit()
    return redirect(url_for('community.stories'))


@community_bp.route('/community/stories/<int:story_id>/comment', methods=['POST'])
@login_required
def stories_comment(story_id):
    """Оставить комментарий под сторис."""
    story = Story.query.get_or_404(story_id)
    if story.is_expired:
        flash('Эта сторис уже недоступна', 'warning')
        return redirect(url_for('community.stories'))

    text = (request.form.get('text') or '').strip()
    if not text:
        flash('Комментарий не может быть пустым', 'error')
        return redirect(url_for('community.stories'))
    if len(text) > 500:
        flash('Комментарий слишком длинный (максимум 500 символов)', 'error')
        return redirect(url_for('community.stories'))

    db.session.add(
        StoryComment(story_id=story.id, user_id=current_user.id, text=text)
    )
    db.session.commit()
    _notify(
        story.user_id,
        'story_comment',
        'Новый комментарий к вашей сторис',
        f'{current_user.display_name}: {text[:120]}',
    )
    db.session.commit()
    return redirect(url_for('community.stories'))


@community_bp.route('/community/stories/<int:story_id>/delete', methods=['POST'])
@login_required
def stories_delete(story_id):
    """Удалить свою сторис (или любую — для админа)."""
    story = Story.query.get_or_404(story_id)
    if story.user_id != current_user.id and not current_user.is_admin:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('community.stories'))

    delete_file(story.media, 'stories')
    db.session.delete(story)
    db.session.commit()
    flash('Сторис удалена', 'success')
    return redirect(url_for('community.stories'))


@community_bp.route('/community/stories/<int:story_id>/toggle-hide', methods=['POST'])
@login_required
def stories_toggle_hide(story_id):
    """Модерация: скрыть/вернуть сторис (только администратор)."""
    if not current_user.is_admin:
        flash('Недостаточно прав', 'error')
        return redirect(url_for('community.stories'))
    story = Story.query.get_or_404(story_id)
    story.is_hidden = not story.is_hidden
    db.session.commit()
    flash('Сторис скрыта' if story.is_hidden else 'Сторис снова видна', 'success')
    return redirect(url_for('community.stories'))


# --- Профили артистов (карточка в ленте) -------------------------------------

@community_bp.route('/community/user/<int:user_id>')
@login_required
def user_profile(user_id):
    """Мини-карточка участника сообщества."""
    user = User.query.get_or_404(user_id)
    user_stories = Story.active_query().filter(Story.user_id == user_id).all()
    return render_template(
        'community/user_profile.html',
        profile_user=user,
        user_stories=user_stories,
        StoryComment=StoryComment,
    )