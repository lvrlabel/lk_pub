"""
Инструменты — питчинг релиза, генератор обложек, караоке TTML и др.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models.pitch import Pitch
from app.models.release import Release, Track
from app.models.auto_form import AutoFormRequest, AutoFormMessage
from app.models.video_request import VideoRequest
from app.utils.decorators import admin_required
from app.utils.files import delete_file, save_file, allowed_file
from app.utils.cover_generator import STYLE_PRESETS, style_choices

tools_bp = Blueprint('tools', __name__)


@tools_bp.route('/tools')
@login_required
def index():
    """Инструменты: форма питчинга и список заявок"""
    pitches = Pitch.query.filter_by(user_id=current_user.id).order_by(
        Pitch.created_at.desc()
    ).all()
    # Релизы пользователя для выбора (одобренные)
    releases = Release.query.filter_by(
        user_id=current_user.id,
        status='approved'
    ).order_by(Release.created_at.desc()).all()
    return render_template('tools/index.html', pitches=pitches, releases=releases)


@tools_bp.route('/tools/pitch', methods=['POST'])
@login_required
def create_pitch():
    """Создание заявки на питчинг"""
    title = request.form.get('title', '').strip()
    artists = request.form.get('artists', '').strip()
    genre = request.form.get('genre', '').strip()
    comment = request.form.get('comment', '').strip()
    release_id = request.form.get('release_id', type=int)

    if not title or not artists:
        flash('Укажите название и артистов', 'error')
        return redirect(url_for('tools.index'))

    # Если выбран релиз — подставляем данные
    release = None
    if release_id:
        release = Release.query.filter_by(
            id=release_id,
            user_id=current_user.id
        ).first()
        if release:
            if not title:
                title = release.title
            if not artists:
                artists = release.artists
            if not genre:
                genre = release.genre

    pitch = Pitch(
        user_id=current_user.id,
        release_id=release.id if release else None,
        title=title,
        artists=artists,
        genre=genre or None,
        comment=comment or None,
        status='pending'
    )
    db.session.add(pitch)
    db.session.commit()

    flash('Заявка на питчинг отправлена', 'success')
    return redirect(url_for('tools.index'))


# === Админ: управление заявками на питчинг ===

@tools_bp.route('/tools/admin')
@login_required
@admin_required
def pitches_admin():
    """Список заявок на питчинг (для админа)"""
    tab = request.args.get('tab', 'pending')
    page = request.args.get('page', 1, type=int)

    status_map = {
        'all': None,
        'pending': 'pending',
        'in_review': 'in_review',
        'approved': 'approved',
        'rejected': 'rejected',
    }
    status_filter = status_map.get(tab, 'pending')

    query = Pitch.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    pitches = query.order_by(Pitch.created_at.desc()).paginate(
        page=page,
        per_page=20,
        error_out=False
    )

    counts = {
        'all': Pitch.query.count(),
        'pending': Pitch.query.filter_by(status='pending').count(),
        'in_review': Pitch.query.filter_by(status='in_review').count(),
        'approved': Pitch.query.filter_by(status='approved').count(),
        'rejected': Pitch.query.filter_by(status='rejected').count(),
    }

    return render_template('tools/admin.html',
                          pitches=pitches,
                          tab=tab,
                          counts=counts)


@tools_bp.route('/tools/admin/<int:id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_pitch(id):
    """Одобрить заявку"""
    pitch = Pitch.query.get_or_404(id)
    pitch.status = 'approved'
    db.session.commit()
    flash('Заявка одобрена', 'success')
    return redirect(request.referrer or url_for('tools.pitches_admin'))


@tools_bp.route('/tools/admin/<int:id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_pitch(id):
    """Отклонить заявку"""
    pitch = Pitch.query.get_or_404(id)
    pitch.status = 'rejected'
    db.session.commit()
    flash('Заявка отклонена', 'success')
    return redirect(request.referrer or url_for('tools.pitches_admin'))


# === Админ: запросы из автоматической формы ===

@tools_bp.route('/tools/admin/requests')
@login_required
@admin_required
def auto_form_requests_admin():
    """Список запросов из автоматической формы (для админа)"""
    tab = request.args.get('tab', 'pending')
    page = request.args.get('page', 1, type=int)
    status_map = {
        'all': None,
        'pending': 'pending',
        'processed': 'processed',
        'closed': 'closed',
    }
    status_filter = status_map.get(tab, 'pending')
    query = AutoFormRequest.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    requests = query.order_by(AutoFormRequest.created_at.desc()).paginate(
        page=page,
        per_page=20,
        error_out=False
    )
    counts = {
        'all': AutoFormRequest.query.count(),
        'pending': AutoFormRequest.query.filter_by(status='pending').count(),
        'processed': AutoFormRequest.query.filter_by(status='processed').count(),
        'closed': AutoFormRequest.query.filter_by(status='closed').count(),
    }
    return render_template('tools/auto_form_requests.html',
                          requests=requests,
                          tab=tab,
                          counts=counts)


@tools_bp.route('/tools/admin/requests/<int:id>')
@login_required
@admin_required
def auto_form_request_detail(id):
    """Просмотр заявки автоформы: переписка, ответ, смена статуса."""
    req = AutoFormRequest.query.get_or_404(id)
    messages = req.messages.order_by(AutoFormMessage.created_at).all()
    return render_template('tools/auto_form_request_detail.html', req=req, messages=messages)


@tools_bp.route('/tools/admin/requests/<int:id>/reply', methods=['POST'])
@login_required
@admin_required
def auto_form_request_reply(id):
    """Ответ по заявке — сообщение уходит пользователю на почту."""
    req = AutoFormRequest.query.get_or_404(id)
    message_text = request.form.get('message', '').strip()
    if not message_text:
        flash('Введите сообщение', 'error')
        return redirect(url_for('tools.auto_form_request_detail', id=id))
    msg = AutoFormMessage(
        request_id=req.id,
        user_id=current_user.id,
        message=message_text,
        is_admin=True
    )
    db.session.add(msg)
    db.session.commit()
    try:
        from app.utils.email import send_auto_form_reply_to_user
        send_auto_form_reply_to_user(req, message_text)
    except Exception as e:
        current_app.logger.warning('Ошибка отправки email пользователю: %s', e)
    flash('Ответ отправлен, пользователю ушло уведомление на почту', 'success')
    return redirect(url_for('tools.auto_form_request_detail', id=id))


@tools_bp.route('/tools/admin/requests/<int:id>/status', methods=['POST'])
@login_required
@admin_required
def auto_form_request_status(id):
    """Сменить статус заявки: в обработке / закрыто."""
    req = AutoFormRequest.query.get_or_404(id)
    new_status = request.form.get('status', '').strip()
    if new_status in ('processed', 'closed'):
        req.status = new_status
        db.session.commit()
        flash('Статус обновлён', 'success')
    return redirect(url_for('tools.auto_form_request_detail', id=id))


# === Админ: заявки на загрузку видео (рингтоны и видео) ===

@tools_bp.route('/tools/admin/video-requests')
@login_required
@admin_required
def video_requests_admin():
    """Список заявок на загрузку видео для админа."""
    tab = request.args.get('tab', 'all')
    page = request.args.get('page', 1, type=int)
    status_map = {
        'all': None,
        'pending_payment': 'pending_payment',
        'paid': 'paid',
        'processed': 'processed',
        'closed': 'closed',
    }
    status_filter = status_map.get(tab)
    query = VideoRequest.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    requests = query.order_by(VideoRequest.created_at.desc()).paginate(
        page=page,
        per_page=20,
        error_out=False
    )
    counts = {
        'all': VideoRequest.query.count(),
        'pending_payment': VideoRequest.query.filter_by(status='pending_payment').count(),
        'paid': VideoRequest.query.filter_by(status='paid').count(),
        'processed': VideoRequest.query.filter_by(status='processed').count(),
        'closed': VideoRequest.query.filter_by(status='closed').count(),
    }
    return render_template(
        'tools/video_requests.html',
        requests=requests,
        tab=tab,
        counts=counts,
    )


@tools_bp.route('/tools/admin/video-requests/<int:id>/status', methods=['POST'])
@login_required
@admin_required
def video_request_status(id):
    """Сменить статус заявки на видео: обработано / закрыто."""
    req = VideoRequest.query.get_or_404(id)
    new_status = request.form.get('status', '').strip()
    if new_status in ('processed', 'closed'):
        req.status = new_status
        db.session.commit()
        flash('Статус обновлён', 'success')
    return redirect(url_for('tools.video_requests_admin', tab=request.form.get('tab', 'all')))


# === Автоматическая форма ===

@tools_bp.route('/tools/auto-form', methods=['GET', 'POST'])
@login_required
def auto_form():
    """Форма для типовых задач: перенос релиза, нотка YouTube, восстановление VK."""
    releases = Release.query.filter_by(
        user_id=current_user.id,
        status='approved'
    ).order_by(Release.created_at.desc()).all()

    my_requests = AutoFormRequest.query.filter_by(user_id=current_user.id).order_by(
        AutoFormRequest.created_at.desc()
    ).limit(50).all()

    from sqlalchemy import func
    request_ids = [r.id for r in my_requests]
    message_counts = {}
    if request_ids:
        rows = db.session.query(
            AutoFormMessage.request_id,
            func.count(AutoFormMessage.id).label('cnt')
        ).filter(AutoFormMessage.request_id.in_(request_ids)).group_by(AutoFormMessage.request_id).all()
        message_counts = {r.request_id: r.cnt for r in rows}

    if request.method == 'GET':
        return render_template('tools/auto_form.html', releases=releases, my_requests=my_requests, message_counts=message_counts)

    request_type = request.form.get('request_type', '').strip()
    if request_type not in ('transfer_release', 'youtube_note', 'vk_restore'):
        flash('Выберите тип задачи', 'error')
        return render_template('tools/auto_form.html', releases=releases, my_requests=my_requests, message_counts=message_counts)

    if request_type == 'transfer_release':
        platform = request.form.get('platform', '').strip().lower()
        if platform == 'other':
            flash('Для переноса на другую площадку создайте тикет в разделе «Поддержка».', 'info')
            return redirect(url_for('tickets.index'))
        release_id = request.form.get('release_id', type=int)
        if not release_id:
            flash('Выберите релиз', 'error')
            return render_template('tools/auto_form.html', releases=releases, my_requests=my_requests, message_counts=message_counts)
        release = Release.query.filter_by(id=release_id, user_id=current_user.id).first()
        if not release:
            flash('Релиз не найден', 'error')
            return render_template('tools/auto_form.html', releases=releases, my_requests=my_requests, message_counts=message_counts)
        if platform not in ('vk', 'yandex', 'spotify'):
            flash('Выберите площадку: ВК, Яндекс.Музыка или Spotify', 'error')
            return render_template('tools/auto_form.html', releases=releases, my_requests=my_requests, message_counts=message_counts)
        correct_card_url = request.form.get('correct_card_url', '').strip()
        wrong_card_url = request.form.get('wrong_card_url', '').strip()
        if not correct_card_url or not wrong_card_url:
            flash('Укажите обе ссылки на карточки', 'error')
            return render_template('tools/auto_form.html', releases=releases, my_requests=my_requests, message_counts=message_counts)

        req = AutoFormRequest(
            user_id=current_user.id,
            request_type='transfer_release',
            release_id=release.id,
            platform=platform,
            correct_card_url=correct_card_url or None,
            wrong_card_url=wrong_card_url or None,
            status='pending'
        )
        db.session.add(req)
        db.session.commit()
        _send_auto_form_admin_notify(req)
        _send_auto_form_user_confirmation(req, days=7)
        flash('Заявка на перенос принята. Срок обработки до 7 дней. Подтверждение отправлено на вашу почту.', 'success')
        return redirect(url_for('tools.auto_form'))

    if request_type == 'youtube_note':
        artist_name = request.form.get('artist_name', '').strip()
        channel_url = request.form.get('channel_url', '').strip()
        topic_urls = request.form.get('topic_urls', '').strip()
        if not artist_name or not channel_url or not topic_urls:
            flash('Заполните имя артиста, ссылку на канал и ссылку на топик', 'error')
            return render_template('tools/auto_form.html', releases=releases, my_requests=my_requests, message_counts=message_counts)
        req = AutoFormRequest(
            user_id=current_user.id,
            request_type='youtube_note',
            artist_name=artist_name,
            channel_url=channel_url,
            topic_urls=topic_urls,
            status='pending'
        )
        db.session.add(req)
        db.session.commit()
        _send_auto_form_admin_notify(req)
        _send_auto_form_user_confirmation(req, days=14, kind='youtube_note')
        flash('Заявка на получение «Нотки» на YouTube-канал принята. Срок до 14 дней. Подтверждение отправлено на вашу почту.', 'success')
        return redirect(url_for('tools.auto_form'))

    if request_type == 'vk_restore':
        previous_distributor = request.form.get('previous_distributor', '').strip()
        upc_codes = request.form.get('upc_codes', '').strip()
        if not previous_distributor or not upc_codes:
            flash('Укажите название дистрибьютора и UPC-коды релизов', 'error')
            return render_template('tools/auto_form.html', releases=releases, my_requests=my_requests, message_counts=message_counts)
        req = AutoFormRequest(
            user_id=current_user.id,
            request_type='vk_restore',
            previous_distributor=previous_distributor,
            upc_codes=upc_codes,
            status='pending'
        )
        db.session.add(req)
        db.session.commit()
        _send_auto_form_admin_notify(req)
        _send_auto_form_user_confirmation(req, days=14, kind='vk_restore')
        flash('Заявка принята. Срок до 14 дней. Подтверждение отправлено на вашу почту.', 'success')
        return redirect(url_for('tools.auto_form'))

    return render_template('tools/auto_form.html', releases=releases, my_requests=my_requests, message_counts=message_counts)


@tools_bp.route('/tools/auto-form/<int:id>', methods=['GET'])
@login_required
def auto_form_my_request(id):
    """Просмотр своей заявки: статус и переписка (чат)."""
    req = AutoFormRequest.query.get_or_404(id)
    if req.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('tools.auto_form'))
    messages = req.messages.order_by(AutoFormMessage.created_at).all()
    return render_template('tools/auto_form_my_request.html', req=req, messages=messages)


@tools_bp.route('/tools/auto-form/<int:id>/reply', methods=['POST'])
@login_required
def auto_form_my_request_reply(id):
    """Пользователь отправляет сообщение в переписку по своей заявке."""
    req = AutoFormRequest.query.get_or_404(id)
    if req.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('tools.auto_form'))
    message_text = request.form.get('message', '').strip()
    if not message_text:
        flash('Введите сообщение', 'error')
        return redirect(url_for('tools.auto_form_my_request', id=id))
    msg = AutoFormMessage(
        request_id=req.id,
        user_id=current_user.id,
        message=message_text,
        is_admin=False
    )
    db.session.add(msg)
    db.session.commit()
    try:
        from app.utils.email import send_auto_form_user_reply_to_admin
        send_auto_form_user_reply_to_admin(req, message_text)
    except Exception as e:
        current_app.logger.warning('Ошибка отправки уведомления админу о сообщении пользователя: %s', e)
    flash('Сообщение отправлено. Ответ поддержки придёт сюда и на вашу почту.', 'success')
    return redirect(url_for('tools.auto_form_my_request', id=id))


def _send_auto_form_admin_notify(req):
    """Уведомить админа о новом запросе автоформы."""
    try:
        from app.utils.email import send_auto_form_request_email
        send_auto_form_request_email(req)
    except Exception as e:
        current_app.logger.warning('Ошибка отправки уведомления админу о запросе #%s: %s', req.id, e)


def _send_auto_form_user_confirmation(req, days=7, kind=None):
    """Отправить пользователю подтверждение приёма заявки."""
    try:
        from app.utils.email import send_auto_form_user_confirmation_email
        send_auto_form_user_confirmation_email(req, days=days, kind=kind or req.request_type)
    except Exception as e:
        current_app.logger.warning('Ошибка отправки подтверждения пользователю #%s: %s', req.id, e)


# === Генератор обложек (рендер в браузере, на сервер только сохранение файла) ===

def _editable_releases_for_cover():
    return Release.query.filter(
        Release.user_id == current_user.id,
        Release.status.in_(('draft', 'rejected')),
    ).order_by(Release.updated_at.desc()).all()


@tools_bp.route('/tools/cover-generator', methods=['GET'])
@login_required
def cover_generator():
    """Генератор обложек для релизов."""
    releases = _editable_releases_for_cover()
    return render_template(
        'tools/cover_generator.html',
        styles=style_choices(),
        cover_styles=STYLE_PRESETS,
        releases=releases,
        default_artists=current_user.display_name or '',
    )


@tools_bp.route('/tools/cover-generator/apply', methods=['POST'])
@login_required
def cover_generator_apply():
    """Применить обложку к черновику релиза (файл из браузера)."""
    release_id = request.form.get('release_id', type=int)
    cover_file = request.files.get('generated_cover')

    if not release_id:
        flash('Выберите релиз', 'error')
        return redirect(url_for('tools.cover_generator'))

    release = Release.query.filter_by(id=release_id, user_id=current_user.id).first()
    if not release or release.status not in ('draft', 'rejected'):
        flash('Обложку можно применить только к черновику или отклонённому релизу', 'error')
        return redirect(url_for('tools.cover_generator'))

    if not cover_file or not cover_file.filename:
        flash('Не удалось получить файл обложки. Попробуйте ещё раз.', 'error')
        return redirect(url_for('tools.cover_generator'))

    if not allowed_file(cover_file.filename, current_app.config['ALLOWED_COVER_EXTENSIONS']):
        flash('Недопустимый формат обложки. Разрешены: JPG, PNG', 'error')
        return redirect(url_for('tools.cover_generator'))

    try:
        filename = save_file(cover_file, 'covers')
        if not filename:
            flash('Не удалось сохранить обложку', 'error')
            return redirect(url_for('tools.cover_generator'))
        if release.cover:
            delete_file(release.cover, 'covers')
        release.cover = filename
        db.session.commit()
        flash('Обложка применена к релизу', 'success')
        return redirect(url_for('releases.edit', id=release.id))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('cover_generator_apply: %s', e)
        flash('Ошибка при сохранении обложки', 'error')
        return redirect(url_for('tools.cover_generator'))


# === Генератор караоке TTML (синхронизация в браузере) ===

@tools_bp.route('/tools/karaoke-ttml', methods=['GET'])
@login_required
def karaoke_ttml():
    """Генератор синхронизированного текста песни (TTML)."""
    tracks = (
        Track.query.join(Release)
        .filter(
            Release.user_id == current_user.id,
            Track.wav_file.isnot(None),
            Track.wav_file != '',
        )
        .order_by(Release.updated_at.desc(), Track.track_order.asc())
        .limit(80)
        .all()
    )
    track_options = []
    for t in tracks:
        release = t.release
        if not release:
            continue
        track_options.append(
            {
                'id': t.id,
                'label': f'{release.title} — {t.display_title}',
                'url': url_for('releases.serve_track', filename=t.wav_file, play=1),
                'lyrics': (t.lyrics or '').strip(),
            }
        )
    track_lyrics = {str(opt['id']): opt['lyrics'] for opt in track_options if opt.get('lyrics')}
    return render_template(
        'tools/karaoke_ttml.html',
        track_options=track_options,
        track_lyrics=track_lyrics,
        default_title='',
    )
