"""
Личное рабочее пространство артиста.
"""

from datetime import datetime

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required

from app import db
from app.models.release import Release
from app.models.workspace import (
    BLOCK_TINTS,
    THEME_GRADIENTS,
    WorkspaceCalendarEvent,
    WorkspaceIdea,
    WorkspaceLayout,
    WorkspaceNote,
    WorkspaceReleasePlan,
    WorkspaceTask,
)
from app.services.workspace import (
    get_layout_blocks,
    get_workspace_theme,
    overview_payload,
    parse_date,
    parse_datetime_date,
    save_layout_settings,
    _sid,
)
from app.utils.files import allowed_file, save_file, delete_file

workspace_bp = Blueprint('workspace', __name__)


@workspace_bp.context_processor
def inject_workspace_theme():
    """Акцент и фон — на всех страницах пространства одинаково."""
    if not current_user.is_authenticated:
        return {}
    try:
        return {'theme': get_workspace_theme(current_user.id)}
    except Exception:
        return {}


@workspace_bp.route('/workspace')
@login_required
def index():
    """Главный экран личного пространства."""
    data = overview_payload(current_user)
    return render_template('workspace/index.html', **data, section='home')


@workspace_bp.route('/workspace/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Настройка блоков и оформления пространства."""
    if request.method == 'POST':
        visible = set(request.form.getlist('visible'))
        order_raw = (request.form.get('order') or '').strip()
        order_ids = [x for x in order_raw.split(',') if x] if order_raw else [
            b['id'] for b in get_layout_blocks(current_user.id)
        ]
        tints = {}
        for bid in order_ids:
            tints[bid] = (request.form.get(f'tint_{bid}') or 'default').strip()

        layout = WorkspaceLayout.for_user(current_user.id)
        theme = layout.get_theme()
        cover_filename = None
        clear_cover = bool(request.form.get('clear_cover'))
        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            if allowed_file(cover_file.filename, current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'jpg', 'jpeg', 'png'})):
                old = theme.get('cover')
                cover_filename = save_file(cover_file, 'workspace')
                if cover_filename and old:
                    try:
                        delete_file(old, 'workspace')
                    except Exception:
                        pass
            else:
                flash('Обложка: только JPG или PNG', 'error')
                return redirect(url_for('workspace.settings'))

        save_layout_settings(
            current_user.id,
            visible_ids=visible,
            order_ids=order_ids,
            tints=tints,
            accent=(request.form.get('accent') or '').strip(),
            gradient=(request.form.get('gradient') or 'none').strip(),
            cover_filename=cover_filename,
            clear_cover=clear_cover and not cover_filename,
        )
        flash('Оформление пространства сохранено', 'success')
        return redirect(url_for('workspace.index'))

    blocks = get_layout_blocks(current_user.id)
    theme = get_workspace_theme(current_user.id)
    return render_template(
        'workspace/settings.html',
        blocks=blocks,
        theme=theme,
        block_tints=BLOCK_TINTS,
        gradients=THEME_GRADIENTS,
        section='settings',
    )


@workspace_bp.route('/workspace/uploads/<path:filename>')
@login_required
def serve_cover(filename):
    """Отдать обложку пространства текущего пользователя."""
    import os

    layout = WorkspaceLayout.for_user(current_user.id)
    if layout.get_theme().get('cover') != filename:
        abort(404)
    upload_dir = os.path.abspath(os.path.join(current_app.root_path, '..', 'uploads', 'workspace'))
    return send_from_directory(upload_dir, filename)


@workspace_bp.route('/workspace/notes', methods=['GET', 'POST'])
@login_required
def notes():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:200] or 'Без названия'
        body = (request.form.get('body') or '').strip()
        note = WorkspaceNote(
            user_id=current_user.id,
            title=title,
            body=body,
            is_pinned=bool(request.form.get('is_pinned')),
            session_id=_sid(),
        )
        db.session.add(note)
        db.session.commit()
        flash('Заметка сохранена', 'success')
        return redirect(url_for('workspace.notes'))
    items = (
        WorkspaceNote.query.filter_by(user_id=current_user.id)
        .order_by(WorkspaceNote.is_pinned.desc(), WorkspaceNote.updated_at.desc())
        .all()
    )
    return render_template('workspace/notes.html', notes=items, section='notes')


@workspace_bp.route('/workspace/notes/<int:note_id>/delete', methods=['POST'])
@login_required
def note_delete(note_id):
    note = WorkspaceNote.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    db.session.delete(note)
    db.session.commit()
    flash('Заметка удалена', 'info')
    return redirect(url_for('workspace.notes'))


@workspace_bp.route('/workspace/notes/<int:note_id>/edit', methods=['POST'])
@login_required
def note_edit(note_id):
    note = WorkspaceNote.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    note.title = (request.form.get('title') or '').strip()[:200] or note.title
    note.body = (request.form.get('body') or '').strip()
    note.is_pinned = bool(request.form.get('is_pinned'))
    note.updated_at = datetime.utcnow()
    note.session_id = _sid()
    db.session.commit()
    flash('Заметка обновлена', 'success')
    return redirect(url_for('workspace.notes'))


@workspace_bp.route('/workspace/tasks', methods=['GET', 'POST'])
@login_required
def tasks():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:300]
        if not title:
            flash('Введите текст задачи', 'error')
            return redirect(url_for('workspace.tasks'))
        due = parse_date(request.form.get('due_at') or '')
        task = WorkspaceTask(
            user_id=current_user.id,
            title=title,
            notes=(request.form.get('notes') or '').strip() or None,
            due_at=datetime.combine(due, datetime.min.time()) if due else None,
            list_name=(request.form.get('list_name') or '').strip()[:100] or None,
            session_id=_sid(),
        )
        db.session.add(task)
        db.session.commit()
        flash('Задача добавлена', 'success')
        return redirect(url_for('workspace.tasks'))

    show_done = request.args.get('done') == '1'
    q = WorkspaceTask.query.filter_by(user_id=current_user.id)
    if not show_done:
        q = q.filter_by(is_done=False)
    items = q.order_by(WorkspaceTask.is_done.asc(), WorkspaceTask.due_at.asc(), WorkspaceTask.id.desc()).all()
    lists = sorted({t.list_name for t in items if t.list_name})
    return render_template(
        'workspace/tasks.html',
        tasks=items,
        lists=lists,
        show_done=show_done,
        section='tasks',
    )


@workspace_bp.route('/workspace/tasks/<int:task_id>/toggle', methods=['POST'])
@login_required
def task_toggle(task_id):
    task = WorkspaceTask.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    task.is_done = not task.is_done
    task.updated_at = datetime.utcnow()
    task.session_id = _sid()
    db.session.commit()
    return redirect(request.referrer or url_for('workspace.tasks'))


@workspace_bp.route('/workspace/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def task_delete(task_id):
    task = WorkspaceTask.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    flash('Задача удалена', 'info')
    return redirect(url_for('workspace.tasks'))


@workspace_bp.route('/workspace/ideas', methods=['GET', 'POST'])
@login_required
def ideas():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:200]
        if not title:
            flash('Введите название идеи', 'error')
            return redirect(url_for('workspace.ideas'))
        idea = WorkspaceIdea(
            user_id=current_user.id,
            title=title,
            body=(request.form.get('body') or '').strip() or None,
            status='inbox',
            session_id=_sid(),
        )
        db.session.add(idea)
        db.session.commit()
        flash('Идея сохранена', 'success')
        return redirect(url_for('workspace.ideas'))
    items = (
        WorkspaceIdea.query.filter_by(user_id=current_user.id)
        .order_by(WorkspaceIdea.updated_at.desc())
        .all()
    )
    return render_template('workspace/ideas.html', ideas=items, section='ideas')


@workspace_bp.route('/workspace/ideas/<int:idea_id>/status', methods=['POST'])
@login_required
def idea_status(idea_id):
    idea = WorkspaceIdea.query.filter_by(id=idea_id, user_id=current_user.id).first_or_404()
    status = (request.form.get('status') or '').strip()
    if status in ('inbox', 'active', 'done'):
        idea.status = status
        idea.updated_at = datetime.utcnow()
        idea.session_id = _sid()
        db.session.commit()
    return redirect(url_for('workspace.ideas'))


@workspace_bp.route('/workspace/ideas/<int:idea_id>/delete', methods=['POST'])
@login_required
def idea_delete(idea_id):
    idea = WorkspaceIdea.query.filter_by(id=idea_id, user_id=current_user.id).first_or_404()
    db.session.delete(idea)
    db.session.commit()
    flash('Идея удалена', 'info')
    return redirect(url_for('workspace.ideas'))


@workspace_bp.route('/workspace/plans', methods=['GET', 'POST'])
@login_required
def plans():
    releases = []
    if current_user.is_admin:
        releases = Release.query.order_by(Release.id.desc()).limit(50).all()
    else:
        releases = (
            Release.query.filter_by(user_id=current_user.id)
            .order_by(Release.id.desc())
            .limit(50)
            .all()
        )
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:200]
        if not title:
            flash('Введите название плана', 'error')
            return redirect(url_for('workspace.plans'))
        release_id = request.form.get('release_id') or None
        rid = int(release_id) if release_id and str(release_id).isdigit() else None
        if rid:
            if current_user.is_admin:
                own = Release.query.filter_by(id=rid).first()
            else:
                own = Release.query.filter_by(id=rid, user_id=current_user.id).first()
            if not own:
                rid = None
        plan = WorkspaceReleasePlan(
            user_id=current_user.id,
            title=title,
            notes=(request.form.get('notes') or '').strip() or None,
            target_date=parse_date(request.form.get('target_date') or ''),
            release_id=rid,
            status='planned',
            session_id=_sid(),
        )
        db.session.add(plan)
        db.session.commit()
        flash('План по релизу добавлен', 'success')
        return redirect(url_for('workspace.plans'))
    items = (
        WorkspaceReleasePlan.query.filter_by(user_id=current_user.id)
        .order_by(WorkspaceReleasePlan.target_date.asc(), WorkspaceReleasePlan.id.desc())
        .all()
    )
    return render_template('workspace/plans.html', plans=items, releases=releases, section='plans')


@workspace_bp.route('/workspace/plans/<int:plan_id>/status', methods=['POST'])
@login_required
def plan_status(plan_id):
    plan = WorkspaceReleasePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    status = (request.form.get('status') or '').strip()
    if status in ('planned', 'in_progress', 'done'):
        plan.status = status
        plan.updated_at = datetime.utcnow()
        plan.session_id = _sid()
        db.session.commit()
    return redirect(url_for('workspace.plans'))


@workspace_bp.route('/workspace/plans/<int:plan_id>/delete', methods=['POST'])
@login_required
def plan_delete(plan_id):
    plan = WorkspaceReleasePlan.query.filter_by(id=plan_id, user_id=current_user.id).first_or_404()
    db.session.delete(plan)
    db.session.commit()
    flash('План удалён', 'info')
    return redirect(url_for('workspace.plans'))


@workspace_bp.route('/workspace/calendar', methods=['GET', 'POST'])
@login_required
def calendar():
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:200]
        starts = parse_datetime_date(request.form.get('starts_at') or '')
        if not title or not starts:
            flash('Укажите название и дату', 'error')
            return redirect(url_for('workspace.calendar'))
        event = WorkspaceCalendarEvent(
            user_id=current_user.id,
            title=title,
            notes=(request.form.get('notes') or '').strip() or None,
            starts_at=starts,
            all_day=True,
            session_id=_sid(),
        )
        db.session.add(event)
        db.session.commit()
        flash('Событие добавлено', 'success')
        return redirect(url_for('workspace.calendar'))
    items = (
        WorkspaceCalendarEvent.query.filter_by(user_id=current_user.id)
        .order_by(WorkspaceCalendarEvent.starts_at.asc())
        .limit(100)
        .all()
    )
    return render_template('workspace/calendar.html', events=items, section='calendar')


@workspace_bp.route('/workspace/calendar/<int:event_id>/delete', methods=['POST'])
@login_required
def calendar_delete(event_id):
    event = WorkspaceCalendarEvent.query.filter_by(
        id=event_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(event)
    db.session.commit()
    flash('Событие удалено', 'info')
    return redirect(url_for('workspace.calendar'))
