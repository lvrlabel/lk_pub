"""
Декораторы
"""

from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def admin_required(f):
    """Декоратор для проверки прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('auth.login'))
        
        if not current_user.is_admin:
            flash('Доступ запрещён. Требуются права администратора.', 'error')
            return redirect(url_for('dashboard.index'))
        
        return f(*args, **kwargs)
    return decorated_function


def label_required(f):
    """Декоратор для проверки прав лейбла"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('auth.login'))
        
        if not (current_user.is_admin or current_user.is_label):
            flash('Доступ запрещён. Требуются права лейбла.', 'error')
            return redirect(url_for('dashboard.index'))
        
        return f(*args, **kwargs)
    return decorated_function


def active_user_required(f):
    """Декоратор для проверки активного пользователя"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('auth.login'))
        
        if not current_user.is_active:
            flash('Ваш аккаунт заблокирован', 'error')
            return redirect(url_for('auth.logout'))
        
        return f(*args, **kwargs)
    return decorated_function
