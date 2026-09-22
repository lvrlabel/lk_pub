"""
Обновления сервиса — журнал изменений кабинета.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app import db
from app.models.service_update import ServiceUpdate, ServiceUpdateRead
from app.utils.decorators import admin_required
from app.services.service_updates import (
    mark_service_updates_read,
    new_manual_slug,
)

service_updates_bp = Blueprint('service_updates', __name__)


@service_updates_bp.route('/service-updates')
@login_required
def index():
    """Список обновлений сервиса."""
    page = request.args.get('page', 1, type=int)
    updates = ServiceUpdate.query.order_by(ServiceUpdate.created_at.desc()).paginate(
        page=page,
        per_page=current_app.config.get('SERVICE_UPDATES_PER_PAGE', 15),
        error_out=False,
    )
    read_ids = {
        r.update_id
        for r in ServiceUpdateRead.query.filter_by(user_id=current_user.id).all()
    }

    mark_service_updates_read(current_user)

    return render_template(
        'service_updates/index.html',
        updates=updates,
        read_ids=read_ids,
    )


@service_updates_bp.route('/service-updates/<int:id>')
@login_required
def view(id):
    """Просмотр обновления."""
    item = ServiceUpdate.query.get_or_404(id)
    mark_service_updates_read(current_user, [item.id])
    return render_template('service_updates/view.html', item=item)


@service_updates_bp.route('/service-updates/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    """Ручное добавление обновления администратором."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        priority = request.form.get('priority', 'normal').strip().lower()
        if priority not in ('normal', 'urgent'):
            priority = 'normal'

        if not title or not content:
            flash('Заполните заголовок и текст обновления', 'error')
            return render_template('service_updates/form.html', item=None)

        item = ServiceUpdate(
            slug=new_manual_slug(),
            title=title,
            content=content,
            priority=priority,
            source='manual',
            author_id=current_user.id,
        )
        db.session.add(item)
        db.session.commit()
        flash('Обновление опубликовано', 'success')
        return redirect(url_for('service_updates.view', id=item.id))

    return render_template('service_updates/form.html', item=None)


@service_updates_bp.route('/service-updates/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    """Редактирование обновления."""
    item = ServiceUpdate.query.get_or_404(id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        priority = request.form.get('priority', 'normal').strip().lower()
        if priority not in ('normal', 'urgent'):
            priority = 'normal'

        if not title or not content:
            flash('Заполните заголовок и текст обновления', 'error')
            return render_template('service_updates/form.html', item=item)

        changed = item.title != title or item.content != content or item.priority != priority
        item.title = title
        item.content = content
        item.priority = priority
        if changed:
            ServiceUpdateRead.query.filter_by(update_id=item.id).delete(synchronize_session=False)
        db.session.commit()
        flash('Обновление сохранено', 'success')
        return redirect(url_for('service_updates.view', id=item.id))

    return render_template('service_updates/form.html', item=item)


@service_updates_bp.route('/service-updates/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    """Удаление обновления."""
    item = ServiceUpdate.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    flash('Запись удалена', 'success')
    return redirect(url_for('service_updates.index'))
