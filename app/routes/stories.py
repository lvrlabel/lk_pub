"""
Новости
"""

import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user
from app import db
from app.models.news import News
from app.utils.decorators import admin_required
from app.utils.files import save_file, delete_file, allowed_file

stories_bp = Blueprint('stories', __name__)


@stories_bp.route('/stories')
@login_required
def index():
    """Список новостей"""
    page = request.args.get('page', 1, type=int)
    
    news = News.query.order_by(News.created_at.desc()).paginate(
        page=page,
        per_page=current_app.config.get('NEWS_PER_PAGE', 10),
        error_out=False
    )
    
    return render_template('stories/index.html', news=news)


@stories_bp.route('/stories/<int:id>')
@login_required
def view(id):
    """Просмотр новости"""
    news = News.query.get_or_404(id)
    return render_template('stories/view.html', news=news)


@stories_bp.route('/stories/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    """Создание новости"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        
        # Валидация
        if not title or not content:
            flash('Заполните все обязательные поля', 'error')
            return render_template('stories/create.html')
        
        # Создание новости
        news = News(
            title=title,
            content=content,
            author_id=current_user.id
        )
        
        # Загрузка обложки
        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            if allowed_file(cover_file.filename, current_app.config['ALLOWED_NEWS_COVER_EXTENSIONS']):
                filename = save_file(cover_file, 'news_covers')
                if filename:
                    news.cover_image = filename
            else:
                flash('Недопустимый формат обложки. Разрешены: JPG, PNG, GIF, WebP', 'error')
        
        db.session.add(news)
        db.session.commit()
        
        flash('Новость создана', 'success')
        return redirect(url_for('stories.view', id=news.id))
    
    return render_template('stories/create.html')


@stories_bp.route('/stories/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    """Редактирование новости"""
    news = News.query.get_or_404(id)
    
    if request.method == 'POST':
        news.title = request.form.get('title', '').strip()
        news.content = request.form.get('content', '').strip()
        
        # Валидация
        if not news.title or not news.content:
            flash('Заполните все обязательные поля', 'error')
            return render_template('stories/edit.html', news=news)
        
        # Обновление обложки
        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            if allowed_file(cover_file.filename, current_app.config['ALLOWED_NEWS_COVER_EXTENSIONS']):
                # Удаление старой обложки
                if news.cover_image:
                    delete_file(news.cover_image, 'news_covers')
                
                filename = save_file(cover_file, 'news_covers')
                if filename:
                    news.cover_image = filename
            else:
                flash('Недопустимый формат обложки', 'error')
        
        db.session.commit()
        flash('Новость обновлена', 'success')
        return redirect(url_for('stories.view', id=news.id))
    
    return render_template('stories/edit.html', news=news)


@stories_bp.route('/stories/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    """Удаление новости"""
    news = News.query.get_or_404(id)
    
    # Удаление обложки
    if news.cover_image:
        delete_file(news.cover_image, 'news_covers')
    
    db.session.delete(news)
    db.session.commit()
    
    flash('Новость удалена', 'success')
    return redirect(url_for('stories.index'))


@stories_bp.route('/uploads/news_covers/<filename>')
@login_required
def serve_cover(filename):
    """Отдача файла обложки"""
    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', 'news_covers')
    return send_file(os.path.join(upload_folder, filename))
