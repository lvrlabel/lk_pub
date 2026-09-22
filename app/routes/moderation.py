"""
Модерация релизов (только для админов)
"""

import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user
from app import db
from app.models.release import Release, Track
from app.models.notification import Notification
from app.utils.decorators import admin_required
from app.utils.email import (
    send_release_approved_email,
    send_release_rejected_email,
    send_release_revoked_email,
)
from app.services.release_events import log_release_event, log_admin_viewed_if_needed, get_release_events

moderation_bp = Blueprint('moderation', __name__)


def _release_docs_dir(release_id):
    return os.path.join(current_app.root_path, '..', 'uploads', 'release_docs', str(release_id))


def _list_release_documents(release_id):
    docs_dir = _release_docs_dir(release_id)
    if not os.path.isdir(docs_dir):
        return []
    docs = []
    for filename in sorted(os.listdir(docs_dir)):
        file_path = os.path.join(docs_dir, filename)
        if not os.path.isfile(file_path):
            continue
        docs.append({'filename': filename, 'size': os.path.getsize(file_path)})
    return docs


@moderation_bp.route('/moderation')
@login_required
@admin_required
def index():
    """Список релизов на модерации"""
    tab = request.args.get('tab', 'moderation')
    page = request.args.get('page', 1, type=int)
    
    # Определение статуса по вкладке
    status_map = {
        'moderation': 'moderation',
        'approved': 'approved',
        'rejected': 'rejected',
        'deletion': 'deletion',
        'revoked': 'revoked',
    }
    
    status = status_map.get(tab, 'moderation')
    
    # Запрос релизов
    releases = Release.query.filter_by(status=status).order_by(
        Release.created_at.desc()
    ).paginate(
        page=page,
        per_page=current_app.config.get('RELEASES_PER_PAGE', 12),
        error_out=False
    )
    
    # Количество по статусам
    counts = {
        'moderation': Release.query.filter_by(status='moderation').count(),
        'approved': Release.query.filter_by(status='approved').count(),
        'rejected': Release.query.filter_by(status='rejected').count(),
        'deletion': Release.query.filter_by(status='deletion').count(),
        'revoked': Release.query.filter_by(status='revoked').count(),
    }
    
    return render_template('moderation/index.html',
                          releases=releases,
                          tab=tab,
                          counts=counts)


@moderation_bp.route('/moderation/<int:id>')
@login_required
@admin_required
def view(id):
    """Просмотр релиза на модерации"""
    release = Release.query.get_or_404(id)
    try:
        log_admin_viewed_if_needed(release, current_user)
    except Exception as e:
        current_app.logger.warning('release event admin_viewed: %s', e)
    tracks = release.tracks.order_by(Track.track_order).all()
    release_documents = _list_release_documents(release.id)
    release_events = get_release_events(release.id, viewer=current_user, release=release)
    from app.routes.releases import _delivery_rows_for_release, DELIVERY_STATUS_OPTIONS

    return render_template(
        'moderation/view.html',
        release=release,
        tracks=tracks,
        release_documents=release_documents,
        release_events=release_events,
        delivery_rows=_delivery_rows_for_release(release),
        delivery_status_options=DELIVERY_STATUS_OPTIONS,
    )


@moderation_bp.route('/moderation/<int:id>/approve', methods=['POST'])
@login_required
@admin_required
def approve(id):
    """Одобрение релиза"""
    release = Release.query.get_or_404(id)
    
    if release.status != 'moderation':
        flash('Этот релиз не находится на модерации', 'error')
        return redirect(url_for('moderation.view', id=id))
    
    # UPC код (опционально)
    upc = request.form.get('upc', '').strip()
    if upc:
        release.upc = upc
    
    release.status = 'approved'
    release.moderator_comment = None
    log_release_event(release, 'approved', actor=current_user, commit=False)
    db.session.commit()

    try:
        db.session.add(
            Notification(
                user_id=release.user_id,
                kind='release_approved',
                title='Релиз одобрен',
                message=f'«{release.title}» прошёл модерацию и отправлен на площадки.',
                release_id=release.id,
            )
        )
        db.session.commit()
    except Exception as e:
        current_app.logger.warning('in-app notification release_approved: %s', e)

    try:
        ok = send_release_approved_email(release)
        if not ok:
            flash('Релиз одобрен. Уведомление артисту на почту не отправлено — проверьте email в профиле артиста и настройки SMTP.', 'warning')
    except Exception as e:
        current_app.logger.warning('Ошибка отправки уведомления об одобрении: %s', e)
        flash('Релиз одобрен. Не удалось отправить письмо артисту — проверьте настройки SMTP.', 'warning')

    flash('Релиз одобрен', 'success')
    return redirect(url_for('moderation.index'))


@moderation_bp.route('/moderation/<int:id>/reject', methods=['POST'])
@login_required
@admin_required
def reject(id):
    """Отклонение релиза"""
    release = Release.query.get_or_404(id)
    
    if release.status != 'moderation':
        flash('Этот релиз не находится на модерации', 'error')
        return redirect(url_for('moderation.view', id=id))
    
    comment = request.form.get('comment', '').strip()
    if not comment:
        flash('Укажите причину отклонения', 'error')
        return redirect(url_for('moderation.view', id=id))
    
    release.status = 'rejected'
    release.moderator_comment = comment
    log_release_event(release, 'rejected', actor=current_user, comment=comment, commit=False)
    db.session.commit()

    try:
        short = comment if len(comment) <= 400 else comment[:397] + '…'
        db.session.add(
            Notification(
                user_id=release.user_id,
                kind='release_rejected',
                title='Релиз отклонён',
                message=f'«{release.title}». Причина: {short}',
                release_id=release.id,
            )
        )
        db.session.commit()
    except Exception as e:
        current_app.logger.warning('in-app notification release_rejected: %s', e)

    try:
        ok = send_release_rejected_email(release)
        if not ok:
            flash('Релиз отклонён. Уведомление артисту на почту не отправлено — проверьте email в профиле артиста и настройки SMTP.', 'warning')
    except Exception as e:
        current_app.logger.warning('Ошибка отправки уведомления об отклонении: %s', e)
        flash('Релиз отклонён. Не удалось отправить письмо артисту — проверьте настройки SMTP.', 'warning')

    flash('Релиз отклонён', 'success')
    return redirect(url_for('moderation.index'))


@moderation_bp.route('/moderation/<int:id>/revoke', methods=['POST'])
@login_required
@admin_required
def revoke(id):
    """Отзыв релиза администратором с обязательной причиной."""
    release = Release.query.get_or_404(id)
    if release.status in ('draft', 'deletion'):
        flash('Этот релиз нельзя отозвать из текущего статуса', 'error')
        return redirect(url_for('moderation.view', id=id))

    comment = request.form.get('comment', '').strip()
    if not comment:
        flash('Укажите причину отзыва релиза', 'error')
        return redirect(url_for('moderation.view', id=id))

    release.status = 'revoked'
    release.moderator_comment = comment
    log_release_event(release, 'revoked', actor=current_user, comment=comment, commit=False)
    db.session.commit()

    try:
        short = comment if len(comment) <= 400 else comment[:397] + '…'
        db.session.add(
            Notification(
                user_id=release.user_id,
                kind='release_revoked',
                title='Релиз отозван администратором',
                message=f'«{release.title}». Причина: {short}',
                release_id=release.id,
            )
        )
        db.session.commit()
    except Exception as e:
        current_app.logger.warning('in-app notification release_revoked: %s', e)

    try:
        ok = send_release_revoked_email(release)
        if not ok:
            flash('Релиз отозван. Уведомление артисту на почту не отправлено — проверьте email и SMTP.', 'warning')
    except Exception as e:
        current_app.logger.warning('Ошибка отправки уведомления об отзыве: %s', e)
        flash('Релиз отозван. Не удалось отправить письмо артисту — проверьте настройки SMTP.', 'warning')

    flash('Релиз отозван администратором', 'success')
    return redirect(url_for('moderation.index', tab='revoked'))


@moderation_bp.route('/moderation/<int:id>/confirm-delete', methods=['POST'])
@login_required
@admin_required
def confirm_delete(id):
    """Подтверждение удаления релиза"""
    release = Release.query.get_or_404(id)

    if release.status != 'deletion':
        flash('Этот релиз не ожидает удаления', 'error')
        return redirect(url_for('moderation.view', id=id))

    title = release.title
    # Мягкое удаление: статус deleted, запись остаётся в кабинете пользователя («Удалены»)
    release.status = 'deleted'
    log_release_event(release, 'deletion_confirmed', actor=current_user, commit=False)
    db.session.commit()

    flash(f'Релиз «{title}» удалён (доступен пользователю в разделе «Удалены»)', 'success')
    return redirect(url_for('moderation.index', tab='deletion'))


@moderation_bp.route('/moderation/<int:id>/cancel-delete', methods=['POST'])
@login_required
@admin_required
def cancel_delete(id):
    """Отмена удаления релиза"""
    release = Release.query.get_or_404(id)
    
    if release.status != 'deletion':
        flash('Этот релиз не ожидает удаления', 'error')
        return redirect(url_for('moderation.view', id=id))
    
    release.status = 'approved'
    log_release_event(release, 'deletion_cancelled', actor=current_user, commit=False)
    db.session.commit()
    
    flash('Запрос на удаление отменён', 'success')
    return redirect(url_for('moderation.index', tab='deletion'))


@moderation_bp.route('/moderation/<int:id>/update-upc', methods=['POST'])
@login_required
@admin_required
def update_upc(id):
    """Обновление UPC кода"""
    release = Release.query.get_or_404(id)
    if release.status not in ('moderation', 'approved'):
        flash('UPC можно менять только для релиза на модерации или одобренного', 'error')
        return redirect(url_for('moderation.view', id=id))

    upc = request.form.get('upc', '').strip()
    release.upc = upc if upc else None
    db.session.commit()
    
    flash('UPC код обновлён', 'success')
    return redirect(url_for('moderation.view', id=id))


@moderation_bp.route('/moderation/<int:id>/download-cover')
@login_required
@admin_required
def download_cover(id):
    """Скачивание обложки"""
    release = Release.query.get_or_404(id)
    
    if not release.cover:
        flash('Обложка не найдена', 'error')
        return redirect(url_for('moderation.view', id=id))
    
    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', 'covers')
    file_path = os.path.join(upload_folder, release.cover)
    
    if not os.path.exists(file_path):
        flash('Файл не найден', 'error')
        return redirect(url_for('moderation.view', id=id))
    
    return send_file(file_path, as_attachment=True,
                    download_name=f'{release.title}_cover{os.path.splitext(release.cover)[1]}')


@moderation_bp.route('/moderation/<int:release_id>/track/<int:track_id>/set-isrc', methods=['POST'])
@login_required
@admin_required
def set_track_isrc(release_id, track_id):
    """Установка или изменение ISRC кода трека (админ)"""
    release = Release.query.get_or_404(release_id)
    if release.status not in ('moderation', 'approved'):
        flash('ISRC можно менять только для релиза на модерации или одобренного', 'error')
        return redirect(url_for('moderation.view', id=release_id))
    track = Track.query.get_or_404(track_id)
    if track.release_id != release_id:
        flash('Трек не принадлежит этому релизу', 'error')
        return redirect(url_for('moderation.view', id=release_id))
    from app.utils.validators import normalize_isrc

    raw = request.form.get('isrc', '')
    if len(raw.strip()) > 128:
        flash(f'ISRC для трека «{track.title}» сокращён до 128 символов.', 'warning')
    track.isrc = normalize_isrc(raw)
    db.session.commit()
    flash('ISRC код сохранён', 'success')
    return redirect(url_for('moderation.view', id=release_id))


@moderation_bp.route('/moderation/<int:release_id>/download-track/<int:track_id>')
@login_required
@admin_required
def download_track(release_id, track_id):
    """Скачивание или предпрослушивание трека"""
    release = Release.query.get_or_404(release_id)
    track = Track.query.get_or_404(track_id)
    
    if track.release_id != release_id:
        flash('Трек не принадлежит этому релизу', 'error')
        return redirect(url_for('moderation.view', id=release_id))
    
    if not track.wav_file:
        flash('Файл не найден', 'error')
        return redirect(url_for('moderation.view', id=release_id))
    
    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', 'tracks')
    file_path = os.path.join(upload_folder, track.wav_file)
    
    if not os.path.exists(file_path):
        flash('Файл не найден', 'error')
        return redirect(url_for('moderation.view', id=release_id))
    
    want_play = request.args.get('play') in ('1', 'true', 'yes')
    if want_play:
        return send_file(file_path, mimetype='audio/wav', conditional=True, max_age=3600)
    return send_file(file_path, as_attachment=True, download_name=f'{track.title}.wav')
