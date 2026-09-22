"""
Управление лейблами
"""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models.label import Label, Artist
from app.models.release import Release

labels_bp = Blueprint('labels', __name__)


@labels_bp.route('/labels')
@login_required
def index():
    """Список лейблов"""
    # Только для пользователей с ролью label или админов
    if not current_user.is_admin and not current_user.is_label:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('dashboard.index'))
    
    if current_user.is_admin:
        labels = Label.query.order_by(Label.created_at.desc()).all()
    else:
        labels = Label.query.filter_by(user_id=current_user.id).order_by(Label.created_at.desc()).all()
    
    return render_template('labels/index.html', labels=labels)


@labels_bp.route('/labels/create', methods=['GET', 'POST'])
@login_required
def create():
    """Создание лейбла"""
    if not current_user.is_admin and not current_user.is_label:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        copyright_text = request.form.get('copyright', '').strip()
        
        # Валидация
        if not name or not copyright_text:
            flash('Заполните все обязательные поля', 'error')
            return render_template('labels/create.html')
        
        # Создание лейбла
        label = Label(
            user_id=current_user.id,
            name=name,
            copyright=copyright_text
        )
        
        db.session.add(label)
        db.session.commit()
        
        flash('Лейбл создан', 'success')
        return redirect(url_for('labels.index'))
    
    # Предзаполнение копирайта
    default_copyright = f'© {datetime.now().year} '
    return render_template('labels/create.html', default_copyright=default_copyright)


@labels_bp.route('/labels/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Редактирование лейбла"""
    label = Label.query.get_or_404(id)
    
    # Проверка доступа
    if not current_user.is_admin and label.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('labels.index'))
    
    if request.method == 'POST':
        label.name = request.form.get('name', '').strip()
        label.copyright = request.form.get('copyright', '').strip()
        
        if not label.name or not label.copyright:
            flash('Заполните все обязательные поля', 'error')
            return render_template('labels/edit.html', label=label)
        
        db.session.commit()
        flash('Лейбл обновлён', 'success')
        return redirect(url_for('labels.index'))
    
    return render_template('labels/edit.html', label=label)


@labels_bp.route('/labels/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Удаление лейбла"""
    label = Label.query.get_or_404(id)
    
    # Проверка доступа
    if not current_user.is_admin and label.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('labels.index'))
    
    # Проверка использования
    releases_count = Release.query.filter_by(copyright=label.copyright).count()
    if releases_count > 0:
        flash(f'Нельзя удалить лейбл, он используется в {releases_count} релизах', 'error')
        return redirect(url_for('labels.index'))
    
    db.session.delete(label)
    db.session.commit()
    
    flash('Лейбл удалён', 'success')
    return redirect(url_for('labels.index'))


# Управление артистами
@labels_bp.route('/artists')
@login_required
def artists():
    """Список артистов пользователя"""
    artists = Artist.query.filter_by(user_id=current_user.id).order_by(Artist.name).all()
    return render_template('labels/artists.html', artists=artists)


@labels_bp.route('/artists/create', methods=['GET', 'POST'])
@login_required
def create_artist():
    """Создание артиста"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        role = request.form.get('role', 'Исполнитель')
        
        if not name:
            flash('Укажите имя артиста', 'error')
            return render_template('labels/create_artist.html', roles=Artist.get_roles())
        
        artist = Artist(
            user_id=current_user.id,
            name=name,
            role=role
        )
        
        db.session.add(artist)
        db.session.commit()
        
        flash('Артист добавлен', 'success')
        return redirect(url_for('labels.artists'))
    
    return render_template('labels/create_artist.html', roles=Artist.get_roles())


@labels_bp.route('/artists/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_artist(id):
    """Редактирование артиста"""
    artist = Artist.query.get_or_404(id)
    
    if artist.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('labels.artists'))
    
    if request.method == 'POST':
        artist.name = request.form.get('name', '').strip()
        artist.role = request.form.get('role', 'Исполнитель')
        
        if not artist.name:
            flash('Укажите имя артиста', 'error')
            return render_template('labels/edit_artist.html', artist=artist, roles=Artist.get_roles())
        
        db.session.commit()
        flash('Артист обновлён', 'success')
        return redirect(url_for('labels.artists'))
    
    return render_template('labels/edit_artist.html', artist=artist, roles=Artist.get_roles())


@labels_bp.route('/artists/<int:id>/delete', methods=['POST'])
@login_required
def delete_artist(id):
    """Удаление артиста"""
    artist = Artist.query.get_or_404(id)
    
    if artist.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('labels.artists'))
    
    db.session.delete(artist)
    db.session.commit()
    
    flash('Артист удалён', 'success')
    return redirect(url_for('labels.artists'))
