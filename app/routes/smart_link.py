"""
Смарт-ссылки
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.release import Release
from app.models.smart_link import SmartLink, LinkVisit, LinkClick

smart_link_bp = Blueprint('smart_link', __name__)


@smart_link_bp.route('/smart-links')
@login_required
def index():
    """Список смарт-ссылок"""
    from sqlalchemy.orm import joinedload

    links = (
        SmartLink.query.options(joinedload(SmartLink.release))
        .filter_by(user_id=current_user.id)
        .order_by(SmartLink.created_at.desc())
        .all()
    )

    return render_template('smart_link/index.html', links=links)


@smart_link_bp.route('/smart-link/create', methods=['GET', 'POST'])
@login_required
def create():
    """Создание смарт-ссылки"""
    if request.method == 'POST':
        release_id = request.form.get('release_id', type=int)
        custom_name = request.form.get('custom_name', '').strip()
        theme = request.form.get('theme', 'dark')
        
        # Получение ссылок на платформы
        platform_links = {}
        platforms = ['spotify', 'apple_music', 'yandex_music', 'vk_music',
                     'youtube_music', 'deezer', 'zvooq', 'wink']
        
        for platform in platforms:
            link = request.form.get(f'link_{platform}', '').strip()
            if link:
                platform_links[platform] = link
        
        # Валидация
        if not release_id:
            flash('Выберите релиз', 'error')
            return redirect(url_for('smart_link.create'))
        
        release = Release.query.get(release_id)
        if not release or release.user_id != current_user.id:
            flash('Релиз не найден', 'error')
            return redirect(url_for('smart_link.create'))
        
        if not platform_links:
            flash('Добавьте хотя бы одну ссылку на платформу', 'error')
            return redirect(url_for('smart_link.create'))
        
        # Создание ссылки
        link_code = SmartLink.generate_link_code()
        
        smart_link = SmartLink(
            user_id=current_user.id,
            release_id=release_id,
            link_code=link_code,
            custom_name=custom_name or None,
            platform_links=platform_links,
            theme=theme
        )
        
        db.session.add(smart_link)
        db.session.commit()
        
        flash('Смарт-ссылка создана', 'success')
        return redirect(url_for('smart_link.view', id=smart_link.id))
    
    # GET - форма
    releases = Release.query.filter_by(
        user_id=current_user.id, status='approved'
    ).order_by(Release.created_at.desc()).all()
    
    return render_template('smart_link/create.html', releases=releases)


@smart_link_bp.route('/smart-link/<int:id>')
@login_required
def view(id):
    """Просмотр смарт-ссылки"""
    link = SmartLink.query.get_or_404(id)
    
    # Проверка доступа
    if link.user_id != current_user.id and not current_user.is_admin:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('smart_link.index'))
    
    # Статистика
    total_visits = link.visits.count()
    total_clicks = link.clicks.count()
    
    # Клики по платформам
    platform_clicks = db.session.query(
        LinkClick.platform,
        db.func.count(LinkClick.id).label('count')
    ).filter_by(link_code=link.link_code).group_by(LinkClick.platform).all()
    
    return render_template('smart_link/view.html',
                          link=link,
                          total_visits=total_visits,
                          total_clicks=total_clicks,
                          platform_clicks=platform_clicks)


@smart_link_bp.route('/smart-link/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Редактирование смарт-ссылки"""
    link = SmartLink.query.get_or_404(id)
    
    # Проверка доступа
    if link.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('smart_link.index'))
    
    if request.method == 'POST':
        link.custom_name = request.form.get('custom_name', '').strip() or None
        link.theme = request.form.get('theme', 'dark')
        
        # Обновление ссылок на платформы
        platform_links = {}
        platforms = ['spotify', 'apple_music', 'yandex_music', 'vk_music',
                     'youtube_music', 'deezer', 'zvooq', 'wink']
        
        for platform in platforms:
            url = request.form.get(f'link_{platform}', '').strip()
            if url:
                platform_links[platform] = url
        
        link.platform_links = platform_links
        db.session.commit()
        
        flash('Смарт-ссылка обновлена', 'success')
        return redirect(url_for('smart_link.view', id=id))
    
    return render_template('smart_link/edit.html', link=link)


@smart_link_bp.route('/smart-link/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Удаление смарт-ссылки"""
    link = SmartLink.query.get_or_404(id)
    
    # Проверка доступа
    if link.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('smart_link.index'))
    
    db.session.delete(link)
    db.session.commit()
    
    flash('Смарт-ссылка удалена', 'success')
    return redirect(url_for('smart_link.index'))


# Публичная страница смарт-ссылки
@smart_link_bp.route('/link/<link_code>')
def public_view(link_code):
    """Публичная страница смарт-ссылки"""
    link = SmartLink.query.filter_by(link_code=link_code).first_or_404()
    release = link.release
    
    # Запись посещения
    visit = LinkVisit(
        link_code=link_code,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:512] if request.user_agent else None
    )
    db.session.add(visit)
    db.session.commit()
    
    return render_template('smart_link/public.html', link=link, release=release)


@smart_link_bp.route('/link/<link_code>/click/<platform>')
def track_click(link_code, platform):
    """Отслеживание клика по платформе"""
    link = SmartLink.query.filter_by(link_code=link_code).first_or_404()
    
    # Запись клика
    click = LinkClick(
        link_code=link_code,
        platform=platform,
        ip_address=request.remote_addr
    )
    db.session.add(click)
    db.session.commit()
    
    # Получение URL платформы
    platform_url = link.platform_links.get(platform) if link.platform_links else None
    
    if platform_url:
        return redirect(platform_url)
    
    return redirect(url_for('smart_link.public_view', link_code=link_code))


@smart_link_bp.route('/smart-link/<int:id>/stats')
@login_required
def stats(id):
    """Детальная статистика смарт-ссылки"""
    link = SmartLink.query.get_or_404(id)
    
    # Проверка доступа
    if link.user_id != current_user.id and not current_user.is_admin:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('smart_link.index'))
    
    # Посещения по дням
    visits_by_day = db.session.query(
        db.func.date(LinkVisit.visited_at).label('date'),
        db.func.count(LinkVisit.id).label('count')
    ).filter_by(link_code=link.link_code).group_by(
        db.func.date(LinkVisit.visited_at)
    ).order_by(db.func.date(LinkVisit.visited_at).desc()).limit(30).all()
    
    # Клики по платформам
    clicks_by_platform = db.session.query(
        LinkClick.platform,
        db.func.count(LinkClick.id).label('count')
    ).filter_by(link_code=link.link_code).group_by(LinkClick.platform).all()
    
    return render_template('smart_link/stats.html',
                          link=link,
                          visits_by_day=visits_by_day,
                          clicks_by_platform=clicks_by_platform)
