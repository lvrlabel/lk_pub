"""
Административные функции
"""

import re
from typing import Optional

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import inspect
from sqlalchemy.orm import joinedload
from app import db
from app.models.release import Platform
from app.models.user import User
from app.models.user_activity_log import UserActivityLog
from app.models.auth import RegistrationRequest
from app.models.knowledge_article import KnowledgeArticle
from app.models.knowledge_section import KnowledgeSection
from app.models.knowledge_topic import KnowledgeTopic
from app.utils.decorators import admin_required
from app.utils.knowledge_html import is_effectively_empty_html, sanitize_knowledge_html

admin_bp = Blueprint('admin', __name__)

_KB_SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
_KB_RESERVED_SECTION_SLUGS = frozenset({'img'})
_KB_TOPIC_RESERVED_SLUGS = frozenset({'_other'})
_KB_STATIC_FALLBACK_CHOICES = [
    ('', 'Нет — только статьи из базы'),
    ('platforms', 'Запасной вариант: «Требования площадок»'),
    ('distribution', 'Запасной вариант: «Дистрибуция»'),
]


def _kb_clear_landing_except(section_id: int, keep_id: Optional[int] = None):
    q = KnowledgeArticle.query.filter_by(section_id=section_id)
    if keep_id is not None:
        q = q.filter(KnowledgeArticle.id != keep_id)
    q.update({KnowledgeArticle.is_landing: False}, synchronize_session=False)


def _kb_section_topics_map():
    sections = KnowledgeSection.query.order_by(KnowledgeSection.sort_order.asc()).all()
    out = {}
    for s in sections:
        out[s.id] = (
            KnowledgeTopic.query.filter_by(section_id=s.id)
            .order_by(KnowledgeTopic.sort_order.asc(), KnowledgeTopic.id.asc())
            .all()
        )
    return out


def _kb_parse_topic_id_for_section(section_id: int):
    raw = (request.form.get('topic_id') or '').strip()
    if not raw:
        return None, None
    try:
        tid = int(raw)
    except ValueError:
        return None, 'Некорректный подраздел'
    top = KnowledgeTopic.query.filter_by(id=tid, section_id=section_id).first()
    if not top:
        return None, 'Подраздел не относится к выбранному разделу'
    return tid, None


# Управление платформами
@admin_bp.route('/admin/platforms')
@login_required
@admin_required
def platforms():
    """Список платформ"""
    platforms = Platform.query.order_by(Platform.sort_order, Platform.name).all()
    
    # Группировка по категориям
    platforms_by_category = {}
    for platform in platforms:
        category = platform.category
        if category not in platforms_by_category:
            platforms_by_category[category] = []
        platforms_by_category[category].append(platform)
    
    return render_template('admin/platforms.html',
                          platforms=platforms,
                          platforms_by_category=platforms_by_category)


@admin_bp.route('/admin/platforms/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_platform():
    """Создание платформы"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', 'streaming')
        warning_message = request.form.get('warning_message', '').strip()
        sort_order = request.form.get('sort_order', 0, type=int)
        
        if not name:
            flash('Укажите название платформы', 'error')
            return render_template('admin/create_platform.html')
        
        # Проверка уникальности
        if Platform.query.filter_by(name=name).first():
            flash('Платформа с таким названием уже существует', 'error')
            return render_template('admin/create_platform.html')
        
        platform = Platform(
            name=name,
            category=category,
            warning_message=warning_message or None,
            sort_order=sort_order,
            is_active=True
        )
        
        db.session.add(platform)
        db.session.commit()
        
        flash('Платформа создана', 'success')
        return redirect(url_for('admin.platforms'))
    
    categories = [
        ('streaming', 'Стриминговые сервисы'),
        ('social', 'Социальные сети'),
        ('video', 'Видео платформы'),
        ('database', 'Музыкальные базы'),
        ('store', 'Магазины'),
        ('radio', 'Радио'),
        ('dj', 'DJ платформы'),
        ('international', 'Международные')
    ]
    return render_template('admin/create_platform.html', categories=categories)


@admin_bp.route('/admin/platforms/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_platform(id):
    """Активация/деактивация платформы"""
    platform = Platform.query.get_or_404(id)
    platform.is_active = not platform.is_active
    db.session.commit()
    
    flash('Платформа обновлена', 'success')
    return redirect(url_for('admin.platforms'))


@admin_bp.route('/admin/platforms/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_platform(id):
    """Редактирование платформы"""
    platform = Platform.query.get_or_404(id)
    
    if request.method == 'POST':
        platform.name = request.form.get('name', '').strip()
        platform.category = request.form.get('category', 'streaming')
        platform.warning_message = request.form.get('warning_message', '').strip() or None
        platform.sort_order = request.form.get('sort_order', 0, type=int)
        
        db.session.commit()
        flash('Платформа обновлена', 'success')
        return redirect(url_for('admin.platforms'))
    
    categories = [
        ('streaming', 'Стриминговые сервисы'),
        ('social', 'Социальные сети'),
        ('video', 'Видео платформы'),
        ('database', 'Музыкальные базы'),
        ('store', 'Магазины'),
        ('radio', 'Радио'),
        ('dj', 'DJ платформы'),
        ('international', 'Международные')
    ]
    return render_template('admin/edit_platform.html', platform=platform, categories=categories)


@admin_bp.route('/admin/platforms/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_platform(id):
    """Удаление платформы"""
    platform = Platform.query.get_or_404(id)
    db.session.delete(platform)
    db.session.commit()
    
    flash('Платформа удалена', 'success')
    return redirect(url_for('admin.platforms'))


# Управление системой (БД)
@admin_bp.route('/bd')
@login_required
@admin_required
def bd():
    """Управление базой данных"""
    # Получение статистики БД
    stats = {
        'users': User.query.count(),
        'releases': db.session.execute(db.text('SELECT COUNT(*) FROM releases')).scalar(),
        'tracks': db.session.execute(db.text('SELECT COUNT(*) FROM tracks')).scalar(),
        'platforms': Platform.query.count()
    }
    
    # Список таблиц (универсально для SQLite, MySQL, PostgreSQL)
    inspector = inspect(db.engine)
    tables = [(name,) for name in sorted(inspector.get_table_names())]
    
    return render_template('admin/bd.html', stats=stats, tables=tables)


@admin_bp.route('/bd/query', methods=['POST'])
@login_required
@admin_required
def bd_query():
    """Выполнение SQL запроса (только SELECT)"""
    query = request.form.get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'Запрос не указан'}), 400
    
    # Проверка на безопасность (только SELECT)
    query_upper = query.upper().strip()
    if not query_upper.startswith('SELECT'):
        return jsonify({'error': 'Разрешены только SELECT запросы'}), 400
    
    # Запрещённые операции
    forbidden = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
    for word in forbidden:
        if word in query_upper:
            return jsonify({'error': f'Операция {word} запрещена'}), 400
    
    try:
        result = db.session.execute(db.text(query))
        columns = list(result.keys())
        rows = [list(row) for row in result.fetchall()]
        
        return jsonify({
            'columns': columns,
            'rows': rows,
            'count': len(rows)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400


# Управление фирмой
@admin_bp.route('/management')
@login_required
@admin_required
def management():
    """Управление фирмой"""
    try:
        stats = {
            'total_users': User.query.count(),
            'active_users': User.query.filter_by(is_active=True).count(),
            'total_releases': db.session.execute(db.text('SELECT COUNT(*) FROM releases')).scalar(),
            'approved_releases': db.session.execute(
                db.text("SELECT COUNT(*) FROM releases WHERE status='approved'")
            ).scalar(),
            'pending_releases': db.session.execute(
                db.text("SELECT COUNT(*) FROM releases WHERE status='moderation'")
            ).scalar()
        }
    except Exception as e:
        current_app.logger.exception('Ошибка загрузки статистики management: %s', e)
        stats = {
            'total_users': 0,
            'active_users': 0,
            'total_releases': 0,
            'approved_releases': 0,
            'pending_releases': 0
        }
    return render_template('admin/management.html', stats=stats)


# Заявки на регистрацию
@admin_bp.route('/admin/registrations')
@login_required
@admin_required
def registrations():
    """Заявки на регистрацию"""
    status = request.args.get('status', 'pending')
    
    query = RegistrationRequest.query
    if status:
        query = query.filter_by(status=status)
    
    requests = query.order_by(RegistrationRequest.created_at.desc()).all()
    
    counts = {
        'pending': RegistrationRequest.query.filter_by(status='pending').count(),
        'approved': RegistrationRequest.query.filter_by(status='approved').count(),
        'rejected': RegistrationRequest.query.filter_by(status='rejected').count()
    }
    
    return render_template('admin/registrations.html',
                          requests=requests,
                          status=status,
                          counts=counts)


@admin_bp.route('/admin/registrations/<int:id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_registration(id):
    """Одобрение заявки на регистрацию"""
    reg_request = RegistrationRequest.query.get_or_404(id)
    
    if reg_request.status != 'pending':
        flash('Заявка уже обработана', 'error')
        return redirect(url_for('admin.registrations'))
    
    from datetime import datetime
    
    reg_request.status = 'approved'
    reg_request.processed_at = datetime.utcnow()
    reg_request.processed_by = current_user.id
    
    db.session.commit()
    
    flash('Заявка одобрена', 'success')
    return redirect(url_for('admin.registrations'))


@admin_bp.route('/admin/registrations/<int:id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_registration(id):
    """Отклонение заявки на регистрацию"""
    reg_request = RegistrationRequest.query.get_or_404(id)
    
    if reg_request.status != 'pending':
        flash('Заявка уже обработана', 'error')
        return redirect(url_for('admin.registrations'))
    
    from datetime import datetime
    
    notes = request.form.get('notes', '').strip()
    
    reg_request.status = 'rejected'
    reg_request.processed_at = datetime.utcnow()
    reg_request.processed_by = current_user.id
    reg_request.notes = notes or None
    
    db.session.commit()
    
    flash('Заявка отклонена', 'success')
    return redirect(url_for('admin.registrations'))


# Проверка почты (SMTP)
@admin_bp.route('/admin/test-email', methods=['GET', 'POST'])
@login_required
@admin_required
def test_email():
    """Проверка настройки SMTP — отправка тестового письма"""
    try:
        from app.utils.email import is_email_configured, send_test_email
        configured = is_email_configured()
        result = None
        if request.method == 'POST':
            recipient = request.form.get('email', '').strip() or (current_user.email if current_user else '')
            if recipient:
                ok, msg = send_test_email(recipient)
                result = {'ok': ok, 'message': msg}
            else:
                result = {'ok': False, 'message': 'Укажите email'}
        return render_template('admin/test_email.html',
                              configured=configured,
                              result=result,
                              mail_server=current_app.config.get('MAIL_SERVER', ''))
    except Exception as e:
        current_app.logger.exception('Ошибка в test_email: %s', e)
        flash(f'Ошибка: {e}', 'error')
        return redirect(url_for('admin.management'))


# Инициализация платформ по умолчанию
@admin_bp.route('/admin/init-platforms', methods=['POST'])
@login_required
@admin_required
def init_platforms():
    """Инициализация платформ по умолчанию"""
    if Platform.query.count() > 0:
        flash('Платформы уже существуют', 'info')
        return redirect(url_for('admin.platforms'))
    
    for platform_data in Platform.get_default_platforms():
        platform = Platform(**platform_data, is_active=True)
        db.session.add(platform)
    
    db.session.commit()
    flash('Платформы инициализированы', 'success')
    return redirect(url_for('admin.platforms'))


# --- База знаний: разделы и статьи ---


def _kb_render_article_form(**ctx):
    ctx.setdefault('static_fallback_choices', _KB_STATIC_FALLBACK_CHOICES)
    ctx.setdefault('section_topics', _kb_section_topics_map())
    ctx.setdefault('form_topic_id', None)
    return render_template('admin/knowledge_article_form.html', **ctx)


@admin_bp.route('/admin/knowledge')
@login_required
@admin_required
def knowledge_list():
    sections = (
        KnowledgeSection.query.order_by(KnowledgeSection.sort_order.asc(), KnowledgeSection.id.asc()).all()
    )
    return render_template('admin/knowledge_list.html', sections=sections)


@admin_bp.route('/admin/knowledge/sections/new', methods=['GET', 'POST'])
@login_required
@admin_required
def knowledge_section_new():
    if request.method == 'POST':
        slug = request.form.get('slug', '').strip().lower()
        title = request.form.get('title', '').strip()
        summary = request.form.get('summary', '').strip() or None
        icon = request.form.get('icon', '').strip() or 'menu_book'
        sort_order = request.form.get('sort_order', type=int) or 0
        is_published = request.form.get('is_published') == 'on'
        highlight = request.form.get('highlight_index') == 'on'
        fb = request.form.get('static_fallback', '').strip() or None
        allowed_fb = {k for k, _ in _KB_STATIC_FALLBACK_CHOICES}
        if fb and fb not in allowed_fb:
            fb = None

        if not slug or not _KB_SLUG_RE.match(slug):
            flash('Адрес раздела (slug): латиница, цифры и дефисы, например platezhi', 'error')
            return render_template(
                'admin/knowledge_section_form.html',
                section=None,
                form_slug=slug,
                form_title=title,
                form_summary=summary or '',
                form_icon=icon,
                form_sort_order=sort_order,
                form_published=is_published,
                form_highlight=highlight,
                form_static_fallback=fb or '',
                static_fallback_choices=_KB_STATIC_FALLBACK_CHOICES,
            )
        if slug in _KB_RESERVED_SECTION_SLUGS or KnowledgeSection.query.filter_by(slug=slug).first():
            flash('Такой адрес раздела уже занят или зарезервирован (нельзя «img»).', 'error')
            return render_template(
                'admin/knowledge_section_form.html',
                section=None,
                form_slug=slug,
                form_title=title,
                form_summary=summary or '',
                form_icon=icon,
                form_sort_order=sort_order,
                form_published=is_published,
                form_highlight=highlight,
                form_static_fallback=fb or '',
                static_fallback_choices=_KB_STATIC_FALLBACK_CHOICES,
            )
        if not title:
            flash('Укажите название раздела', 'error')
            return render_template(
                'admin/knowledge_section_form.html',
                section=None,
                form_slug=slug,
                form_title=title,
                form_summary=summary or '',
                form_icon=icon,
                form_sort_order=sort_order,
                form_published=is_published,
                form_highlight=highlight,
                form_static_fallback=fb or '',
                static_fallback_choices=_KB_STATIC_FALLBACK_CHOICES,
            )

        sec = KnowledgeSection(
            slug=slug,
            title=title,
            summary=summary,
            icon=icon,
            sort_order=sort_order,
            is_published=is_published,
            highlight_index=highlight,
            static_fallback=fb,
        )
        db.session.add(sec)
        db.session.commit()
        flash('Раздел создан. Добавьте в него статьи.', 'success')
        return redirect(url_for('admin.knowledge_list'))

    return render_template(
        'admin/knowledge_section_form.html',
        section=None,
        form_slug='',
        form_title='',
        form_summary='',
        form_icon='menu_book',
        form_sort_order=0,
        form_published=True,
        form_highlight=False,
        form_static_fallback='',
        static_fallback_choices=_KB_STATIC_FALLBACK_CHOICES,
    )


@admin_bp.route('/admin/knowledge/sections/<int:sid>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def knowledge_section_edit(sid):
    sec = KnowledgeSection.query.get_or_404(sid)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        summary = request.form.get('summary', '').strip() or None
        icon = request.form.get('icon', '').strip() or 'menu_book'
        sort_order = request.form.get('sort_order', type=int) or 0
        is_published = request.form.get('is_published') == 'on'
        highlight = request.form.get('highlight_index') == 'on'
        fb = request.form.get('static_fallback', '').strip() or None
        allowed_fb = {k for k, _ in _KB_STATIC_FALLBACK_CHOICES}
        if fb and fb not in allowed_fb:
            fb = None
        if not title:
            flash('Укажите название раздела', 'error')
            return render_template(
                'admin/knowledge_section_form.html',
                section=sec,
                form_slug=sec.slug,
                form_title=title,
                form_summary=summary or '',
                form_icon=icon,
                form_sort_order=sort_order,
                form_published=is_published,
                form_highlight=highlight,
                form_static_fallback=fb or '',
                static_fallback_choices=_KB_STATIC_FALLBACK_CHOICES,
            )
        sec.title = title
        sec.summary = summary
        sec.icon = icon
        sec.sort_order = sort_order
        sec.is_published = is_published
        sec.highlight_index = highlight
        sec.static_fallback = fb
        db.session.commit()
        flash('Раздел сохранён', 'success')
        return redirect(url_for('admin.knowledge_list'))

    return render_template(
        'admin/knowledge_section_form.html',
        section=sec,
        form_slug=sec.slug,
        form_title=sec.title,
        form_summary=sec.summary or '',
        form_icon=sec.icon or 'menu_book',
        form_sort_order=sec.sort_order,
        form_published=sec.is_published,
        form_highlight=sec.highlight_index,
        form_static_fallback=sec.static_fallback or '',
        static_fallback_choices=_KB_STATIC_FALLBACK_CHOICES,
    )


@admin_bp.route('/admin/knowledge/sections/<int:sid>/delete', methods=['POST'])
@login_required
@admin_required
def knowledge_section_delete(sid):
    sec = KnowledgeSection.query.get_or_404(sid)
    db.session.delete(sec)
    db.session.commit()
    flash('Раздел, подразделы и статьи удалены', 'success')
    return redirect(url_for('admin.knowledge_list'))


@admin_bp.route('/admin/knowledge/sections/<int:sid>/topics/new', methods=['GET', 'POST'])
@login_required
@admin_required
def knowledge_topic_new(sid):
    sec = KnowledgeSection.query.get_or_404(sid)
    if request.method == 'POST':
        slug = request.form.get('slug', '').strip().lower()
        title = request.form.get('title', '').strip()
        sort_order = request.form.get('sort_order', type=int) or 0
        is_published = request.form.get('is_published') == 'on'

        def _err():
            return render_template(
                'admin/knowledge_topic_form.html',
                section=sec,
                topic=None,
                form_slug=slug,
                form_title=title,
                form_sort_order=sort_order,
                form_published=is_published,
            )

        if not slug or not _KB_SLUG_RE.match(slug):
            flash('Адрес подраздела (slug): латиница, цифры и дефисы', 'error')
            return _err()
        if slug in _KB_TOPIC_RESERVED_SLUGS:
            flash('Этот адрес зарезервирован системой', 'error')
            return _err()
        if KnowledgeTopic.query.filter_by(section_id=sec.id, slug=slug).first():
            flash('В этом разделе уже есть подраздел с таким адресом', 'error')
            return _err()
        if not title:
            flash('Укажите название', 'error')
            return _err()

        top = KnowledgeTopic(
            section_id=sec.id,
            slug=slug,
            title=title,
            sort_order=sort_order,
            is_published=is_published,
        )
        db.session.add(top)
        db.session.commit()
        flash('Подраздел создан. Добавьте статьи и привяжите их к этой вкладке.', 'success')
        return redirect(url_for('admin.knowledge_list'))

    return render_template(
        'admin/knowledge_topic_form.html',
        section=sec,
        topic=None,
        form_slug='',
        form_title='',
        form_sort_order=0,
        form_published=True,
    )


@admin_bp.route('/admin/knowledge/topics/<int:tid>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def knowledge_topic_edit(tid):
    top = KnowledgeTopic.query.get_or_404(tid)
    sec = top.section
    if request.method == 'POST':
        slug = request.form.get('slug', '').strip().lower()
        title = request.form.get('title', '').strip()
        sort_order = request.form.get('sort_order', type=int) or 0
        is_published = request.form.get('is_published') == 'on'

        def _err():
            return render_template(
                'admin/knowledge_topic_form.html',
                section=sec,
                topic=top,
                form_slug=slug,
                form_title=title,
                form_sort_order=sort_order,
                form_published=is_published,
            )

        if not slug or not _KB_SLUG_RE.match(slug):
            flash('Адрес подраздела: латиница, цифры и дефисы', 'error')
            return _err()
        if slug in _KB_TOPIC_RESERVED_SLUGS:
            flash('Этот адрес зарезервирован системой', 'error')
            return _err()
        dup = (
            KnowledgeTopic.query.filter_by(section_id=sec.id, slug=slug)
            .filter(KnowledgeTopic.id != top.id)
            .first()
        )
        if dup:
            flash('Такой адрес уже занят в этом разделе', 'error')
            return _err()
        if not title:
            flash('Укажите название', 'error')
            return _err()

        top.slug = slug
        top.title = title
        top.sort_order = sort_order
        top.is_published = is_published
        db.session.commit()
        flash('Подраздел сохранён', 'success')
        return redirect(url_for('admin.knowledge_list'))

    return render_template(
        'admin/knowledge_topic_form.html',
        section=sec,
        topic=top,
        form_slug=top.slug,
        form_title=top.title,
        form_sort_order=top.sort_order,
        form_published=top.is_published,
    )


@admin_bp.route('/admin/knowledge/topics/<int:tid>/delete', methods=['POST'])
@login_required
@admin_required
def knowledge_topic_delete(tid):
    top = KnowledgeTopic.query.get_or_404(tid)
    db.session.delete(top)
    db.session.commit()
    flash('Подраздел удалён; статьи остались без вкладки (появятся в «Без подраздела», если опубликованы)', 'success')
    return redirect(url_for('admin.knowledge_list'))


@admin_bp.route('/admin/knowledge/articles/new', methods=['GET', 'POST'])
@login_required
@admin_required
def knowledge_article_new():
    sections = KnowledgeSection.query.order_by(KnowledgeSection.sort_order.asc()).all()
    if not sections:
        flash('Сначала создайте раздел.', 'error')
        return redirect(url_for('admin.knowledge_section_new'))

    if request.method == 'POST':
        section_id = request.form.get('section_id', type=int)
        title = request.form.get('title', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        summary = request.form.get('summary', '').strip() or None
        raw_body = request.form.get('body_html', '') or ''
        body_html = (
            None
            if is_effectively_empty_html(raw_body)
            else (sanitize_knowledge_html(raw_body) or None)
        )
        sort_order = request.form.get('sort_order', type=int) or 0
        is_published = request.form.get('is_published') == 'on'
        is_landing = request.form.get('is_landing') == 'on'

        sec = KnowledgeSection.query.get(section_id)
        if not sec:
            flash('Выберите раздел', 'error')
            return redirect(url_for('admin.knowledge_article_new'))

        tr = (request.form.get('topic_id') or '').strip()
        form_topic_try = int(tr) if tr.isdigit() else None

        def _err():
            return _kb_render_article_form(
                article=None,
                sections=sections,
                form_section_id=section_id,
                form_topic_id=form_topic_try,
                form_slug=slug,
                form_title=title,
                form_summary=summary or '',
                form_body=raw_body,
                form_sort_order=sort_order,
                form_published=is_published,
                form_landing=is_landing,
            )

        if not title:
            flash('Укажите заголовок', 'error')
            return _err()
        if not slug or not _KB_SLUG_RE.match(slug):
            flash('Адрес статьи: латиница, цифры и дефисы (уникален внутри раздела)', 'error')
            return _err()
        if KnowledgeArticle.query.filter_by(section_id=sec.id, slug=slug).first():
            flash('В этом разделе уже есть статья с таким адресом', 'error')
            return _err()

        tid, terr = _kb_parse_topic_id_for_section(sec.id)
        if terr:
            flash(terr, 'error')
            return _err()

        art = KnowledgeArticle(
            section_id=sec.id,
            topic_id=tid,
            slug=slug,
            title=title,
            summary=summary,
            body_html=body_html,
            sort_order=sort_order,
            is_published=is_published,
            is_landing=False,
        )
        db.session.add(art)
        db.session.flush()
        if is_landing:
            _kb_clear_landing_except(sec.id, art.id)
            art.is_landing = True
        db.session.commit()
        flash('Статья сохранена. Ссылка: /knowledge/%s/%s' % (sec.slug, slug), 'success')
        return redirect(url_for('admin.knowledge_list'))

    pre_sid = request.args.get('section_id', type=int)
    if pre_sid and not KnowledgeSection.query.get(pre_sid):
        pre_sid = None
    chosen_sid = pre_sid or sections[0].id
    pre_tid = request.args.get('topic_id', type=int)
    if pre_tid and not KnowledgeTopic.query.filter_by(id=pre_tid, section_id=chosen_sid).first():
        pre_tid = None
    return _kb_render_article_form(
        article=None,
        sections=sections,
        form_section_id=chosen_sid,
        form_topic_id=pre_tid,
        form_slug='',
        form_title='',
        form_summary='',
        form_body='',
        form_sort_order=0,
        form_published=True,
        form_landing=False,
    )


@admin_bp.route('/admin/knowledge/articles/<int:aid>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def knowledge_article_edit(aid):
    article = KnowledgeArticle.query.get_or_404(aid)
    sections = KnowledgeSection.query.order_by(KnowledgeSection.sort_order.asc()).all()

    if request.method == 'POST':
        section_id = request.form.get('section_id', type=int)
        title = request.form.get('title', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        summary = request.form.get('summary', '').strip() or None
        raw_body = request.form.get('body_html', '') or ''
        body_html = (
            None
            if is_effectively_empty_html(raw_body)
            else (sanitize_knowledge_html(raw_body) or None)
        )
        sort_order = request.form.get('sort_order', type=int) or 0
        is_published = request.form.get('is_published') == 'on'
        is_landing = request.form.get('is_landing') == 'on'

        tr = (request.form.get('topic_id') or '').strip()
        form_topic_try = int(tr) if tr.isdigit() else None

        sec = KnowledgeSection.query.get(section_id)
        if not sec:
            flash('Выберите раздел', 'error')
            return _kb_render_article_form(
                article=article,
                sections=sections,
                form_section_id=article.section_id,
                form_topic_id=article.topic_id,
                form_slug=slug,
                form_title=title,
                form_summary=summary or '',
                form_body=raw_body,
                form_sort_order=sort_order,
                form_published=is_published,
                form_landing=is_landing,
            )

        def _err():
            return _kb_render_article_form(
                article=article,
                sections=sections,
                form_section_id=section_id,
                form_topic_id=form_topic_try,
                form_slug=slug,
                form_title=title,
                form_summary=summary or '',
                form_body=raw_body,
                form_sort_order=sort_order,
                form_published=is_published,
                form_landing=is_landing,
            )

        if not title or not slug or not _KB_SLUG_RE.match(slug):
            flash('Проверьте заголовок и адрес статьи (латиница и дефисы)', 'error')
            return _err()
        dup = (
            KnowledgeArticle.query.filter_by(section_id=sec.id, slug=slug)
            .filter(KnowledgeArticle.id != article.id)
            .first()
        )
        if dup:
            flash('В выбранном разделе уже есть статья с таким адресом', 'error')
            return _err()

        tid, terr = _kb_parse_topic_id_for_section(sec.id)
        if terr:
            flash(terr, 'error')
            return _err()

        article.section_id = sec.id
        article.topic_id = tid
        article.slug = slug
        article.title = title
        article.summary = summary
        article.body_html = body_html
        article.sort_order = sort_order
        article.is_published = is_published
        if is_landing:
            _kb_clear_landing_except(sec.id, article.id)
            article.is_landing = True
        else:
            article.is_landing = False
        db.session.commit()
        flash('Статья обновлена', 'success')
        return redirect(url_for('admin.knowledge_list'))

    return _kb_render_article_form(
        article=article,
        sections=sections,
        form_section_id=article.section_id,
        form_topic_id=article.topic_id,
        form_slug=article.slug,
        form_title=article.title,
        form_summary=article.summary or '',
        form_body=article.body_html or '',
        form_sort_order=article.sort_order,
        form_published=article.is_published,
        form_landing=article.is_landing,
    )


@admin_bp.route('/admin/knowledge/articles/<int:aid>/delete', methods=['POST'])
@login_required
@admin_required
def knowledge_article_delete(aid):
    article = KnowledgeArticle.query.get_or_404(aid)
    db.session.delete(article)
    db.session.commit()
    flash('Статья удалена', 'success')
    return redirect(url_for('admin.knowledge_list'))


@admin_bp.route('/admin/user-activity')
@login_required
@admin_required
def user_activity():
    """Журнал действий пользователей (артисты и лейблы)."""
    page = request.args.get('page', 1, type=int)
    filter_user_id = request.args.get('user_id', type=int)
    per_page = 50

    q = (
        UserActivityLog.query.options(joinedload(UserActivityLog.user))
        .order_by(UserActivityLog.created_at.desc())
    )
    if filter_user_id:
        q = q.filter_by(user_id=filter_user_id)

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    users_for_filter = (
        User.query.filter(User.role != 'admin', User.is_active.is_(True))
        .order_by(User.name.asc())
        .limit(500)
        .all()
    )

    return render_template(
        'admin/user_activity.html',
        pagination=pagination,
        filter_user_id=filter_user_id,
        users_for_filter=users_for_filter,
    )
