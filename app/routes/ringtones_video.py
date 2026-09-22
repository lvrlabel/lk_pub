"""
Рингтоны и видео — доп. услуги: загрузка видеоклипа во ВКонтакте, Яндекс.Музыку, Tidal, Amazon
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models.video_request import VideoRequest
from app.models.release import Release
from app.models.release import Track

ringtones_video_bp = Blueprint('ringtones_video', __name__, url_prefix='/marketing')

VIDEO_SERVICE_AMOUNT = 1000


def _get_user_tracks():
    """Треки из релизов пользователя (одобренные релизы) для выбора в форме."""
    return Track.query.join(Release).filter(
        Release.user_id == current_user.id,
        Release.status == 'approved',
    ).order_by(Release.created_at.desc(), Track.track_order).all()


@ringtones_video_bp.route('/ringtones-video')
@login_required
def index():
    """Страница «Рингтоны и видео»: карточка услуги и кнопка «Загрузить»"""
    tracks = _get_user_tracks()
    return render_template('ringtones_video/index.html', tracks=tracks)


@ringtones_video_bp.route('/ringtones-video/create', methods=['POST'])
@login_required
def create():
    """Создание заявки на видео или доставку текста: сохраняем, редирект на страницу оплаты"""
    service_type = (request.form.get('service_type') or 'video').strip()
    if service_type not in ('video', 'lyrics'):
        service_type = 'video'

    track_id = request.form.get('track_id', type=int)
    video_url = (request.form.get('video_url') or '').strip()
    lyrics_text = (request.form.get('lyrics_text') or '').strip()

    if not track_id:
        flash('Выберите трек', 'error')
        return redirect(url_for('ringtones_video.index'))

    if service_type == 'video':
        if not video_url:
            flash('Укажите ссылку на видеофайл', 'error')
            return redirect(url_for('ringtones_video.index'))
    else:  # lyrics
        if not lyrics_text:
            flash('Вставьте текст', 'error')
            return redirect(url_for('ringtones_video.index'))

    track = Track.query.join(Release).filter(
        Track.id == track_id,
        Release.user_id == current_user.id,
    ).first()
    if not track:
        flash('Трек не найден', 'error')
        return redirect(url_for('ringtones_video.index'))

    video_request = VideoRequest(
        user_id=current_user.id,
        track_id=track.id,
        service_type=service_type,
        video_url=video_url if service_type == 'video' else '',
        lyrics_text=lyrics_text if service_type == 'lyrics' else None,
        amount=VIDEO_SERVICE_AMOUNT,
        status='pending_payment',
    )
    db.session.add(video_request)
    db.session.commit()

    return redirect(url_for('ringtones_video.payment', request_id=video_request.id))


@ringtones_video_bp.route('/ringtones-video/payment/<int:request_id>')
@login_required
def payment(request_id):
    """Страница оплаты: форма ЮKassa (Simple Pay)"""
    video_request = VideoRequest.query.filter_by(
        id=request_id,
        user_id=current_user.id,
    ).first_or_404()

    if video_request.status != 'pending_payment':
        flash('Эта заявка уже оплачена или обработана', 'info')
        return redirect(url_for('ringtones_video.index'))

    success_url = url_for('ringtones_video.payment_success', request_id=video_request.id, _external=True)
    shop_id = current_app.config.get('YOOKASSA_SHOP_ID')

    return render_template(
        'ringtones_video/payment.html',
        video_request=video_request,
        success_url=success_url,
        shop_id=shop_id,
    )


@ringtones_video_bp.route('/ringtones-video/payment-success/<int:request_id>')
@login_required
def payment_success(request_id):
    """После возврата с ЮKassa: помечаем заявку как оплаченную, редирект в дашборд"""
    video_request = VideoRequest.query.filter_by(
        id=request_id,
        user_id=current_user.id,
    ).first_or_404()

    if video_request.status == 'pending_payment':
        from datetime import datetime
        video_request.status = 'paid'
        video_request.paid_at = datetime.utcnow()
        db.session.commit()

    flash('Оплата принята. Заявка передана в обработку.', 'success')
    return redirect(url_for('dashboard.index'))
