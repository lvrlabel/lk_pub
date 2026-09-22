"""
Управление пользователями (только админ)
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_
from app import db
from app.models.user import User
from app.utils.decorators import admin_required
from app.utils.user_tax import apply_tax_fields_from_request
from app.utils.validators import validate_password
from app.utils.bonus_program import (
    apply_bonus_credit,
    apply_bonus_debit,
    bonus_services_catalog,
)
from app.models.bonus import BonusTransaction

users_bp = Blueprint('users', __name__)


@users_bp.route('/users/<int:id>/cancel-subscription', methods=['POST'])
@login_required
@admin_required
def cancel_subscription(id):
    user = User.query.get_or_404(id)
    if user.role == 'admin':
        flash('У администратора нельзя отменить подписку', 'error')
        return redirect(url_for('users.view', id=id))
    user.subscription_plan = None
    user.subscription_expires_at = None
    user.subscription_reminder_sent_at = None
    user.releases_restricted = False
    user.releases_restriction_title = None
    user.releases_restriction_message = None
    db.session.commit()
    flash('Подписка пользователя отменена', 'success')
    return redirect(url_for('users.view', id=id))


def _releases_restricted_query():
    return db.and_(User.releases_restricted.is_(True), User.role != 'admin')


def _releases_allowed_query():
    return or_(User.releases_restricted.is_(False), User.role == 'admin')


@users_bp.route('/users')
@login_required
@admin_required
def index():
    """Список пользователей"""
    page = request.args.get('page', 1, type=int)
    role = request.args.get('role', '')
    status = request.args.get('status', '')
    releases = request.args.get('releases', '')
    search = request.args.get('search', '')
    
    query = User.query
    
    # Фильтрация по роли
    if role:
        query = query.filter_by(role=role)
    
    # Фильтрация по статусу
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'blocked':
        query = query.filter_by(is_active=False)

    # Ограничение отправки релизов на модерацию
    if releases == 'restricted':
        query = query.filter(_releases_restricted_query())
    elif releases == 'allowed':
        query = query.filter(_releases_allowed_query())
    
    # Поиск
    if search:
        query = query.filter(
            (User.login.ilike(f'%{search}%')) |
            (User.name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )

    if releases == 'restricted':
        query = query.order_by(User.name.asc(), User.login.asc())
    else:
        query = query.order_by(User.created_at.desc())
    
    users = query.paginate(
        page=page,
        per_page=current_app.config.get('USERS_PER_PAGE', 20),
        error_out=False
    )
    
    # Количество по ролям и ограничениям
    counts = {
        'all': User.query.count(),
        'admin': User.query.filter_by(role='admin').count(),
        'artist': User.query.filter_by(role='artist').count(),
        'label': User.query.filter_by(role='label').count(),
        'releases_restricted': User.query.filter(_releases_restricted_query()).count(),
        'releases_allowed': User.query.filter(_releases_allowed_query()).count(),
    }

    filter_args = {
        'role': role,
        'status': status,
        'search': search,
        'releases': releases,
    }
    
    return render_template('users/index.html',
                          users=users,
                          role=role,
                          status=status,
                          releases=releases,
                          search=search,
                          counts=counts,
                          filter_args=filter_args)


@users_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create():
    """Создание пользователя"""
    if request.method == 'POST':
        login = request.form.get('login', '').strip()
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        role = request.form.get('role', 'artist')
        password = request.form.get('password', '')
        copyright_text = request.form.get('copyright', '').strip()
        partner_code = request.form.get('partner_code', '').strip()
        
        # Валидация
        errors = []
        
        if not login:
            errors.append('Логин обязателен')
        elif User.query.filter_by(login=login).first():
            errors.append('Пользователь с таким логином уже существует')
        
        if not email:
            errors.append('Email обязателен')
        elif User.query.filter_by(email=email).first():
            errors.append('Пользователь с таким email уже существует')
        
        if not name:
            errors.append('Имя обязательно')
        
        if not password:
            errors.append('Пароль обязателен')
        else:
            password_errors = validate_password(password)
            errors.extend(password_errors)
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('users/create.html')
        
        # Создание пользователя
        user = User(
            login=login,
            email=email,
            name=name,
            role=role,
            copyright=copyright_text or None,
            partner_code=partner_code if role == 'label' else None
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()

        if role != 'admin':
            from app.models.contract import Contract
            from app.routes.contracts import _electronic_contract_body
            from app.utils.email import send_contract_uploaded_email
            contract = Contract(
                title='Договор с правообладателем',
                original_filename='generated.html',
                file_path='',
                user_id=user.id,
                admin_id=current_user.id,
                status='pending',
                contract_type='electronic',
                contract_body=_electronic_contract_body(user),
            )
            db.session.add(contract)
            db.session.commit()
            try:
                send_contract_uploaded_email(contract)
            except Exception as exc:
                current_app.logger.warning('Не удалось отправить уведомление о договоре: %s', exc)
        
        flash('Пользователь создан', 'success')
        return redirect(url_for('users.view', id=user.id))
    
    return render_template('users/create.html')


@users_bp.route('/users/<int:id>')
@login_required
@admin_required
def view(id):
    """Просмотр пользователя"""
    user = User.query.get_or_404(id)
    
    # Статистика
    stats = {
        'releases_count': user.releases.count(),
        'approved_releases': user.releases.filter_by(status='approved').count(),
        'tickets_count': user.tickets.count(),
        'contracts_count': user.contracts.count()
    }

    bonus_history = []
    bonus_catalog = bonus_services_catalog()
    if not user.is_admin:
        bonus_history = (
            BonusTransaction.query.filter_by(user_id=user.id)
            .order_by(BonusTransaction.created_at.desc())
            .limit(30)
            .all()
        )

    return render_template(
        'users/view.html',
        user=user,
        stats=stats,
        bonus_history=bonus_history,
        bonus_catalog=bonus_catalog,
    )


@users_bp.route('/users/<int:id>/bonus', methods=['POST'])
@login_required
@admin_required
def bonus_adjust(id):
    """Начисление или списание бонусов (только администратор)."""
    user = User.query.get_or_404(id)
    if user.is_admin:
        flash('Бонусы не начисляются администраторам', 'error')
        return redirect(url_for('users.view', id=id))

    action = (request.form.get('action') or '').strip().lower()
    amount_raw = (request.form.get('amount') or '').strip()
    comment = (request.form.get('comment') or '').strip()
    service_key = (request.form.get('service_key') or '').strip()

    try:
        amount = int(amount_raw)
    except (TypeError, ValueError):
        flash('Укажите корректное количество баллов', 'error')
        return redirect(url_for('users.view', id=id))

    try:
        if action == 'credit':
            apply_bonus_credit(user, amount, current_user, comment=comment)
            db.session.commit()
            flash(f'Начислено {amount} бонусов пользователю {user.display_name}', 'success')
        elif action == 'debit':
            apply_bonus_debit(
                user,
                amount,
                current_user,
                comment=comment,
                service_key=service_key or None,
            )
            db.session.commit()
            flash(f'Списано {amount} бонусов у пользователя {user.display_name}', 'success')
        else:
            flash('Неизвестное действие с бонусами', 'error')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')

    return redirect(url_for('users.view', id=id))


@users_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    """Редактирование пользователя"""
    user = User.query.get_or_404(id)
    
    if request.method == 'POST':
        # Обновление данных
        new_login = request.form.get('login', '').strip()
        new_email = request.form.get('email', '').strip()
        
        # Проверка уникальности
        if new_login != user.login:
            if User.query.filter_by(login=new_login).first():
                flash('Пользователь с таким логином уже существует', 'error')
                return render_template(
                    'users/edit.html', user=user, tax_choices=User.TAX_STATUS_CHOICES
                )

        if new_email != user.email:
            if User.query.filter_by(email=new_email).first():
                flash('Пользователь с таким email уже существует', 'error')
                return render_template(
                    'users/edit.html', user=user, tax_choices=User.TAX_STATUS_CHOICES
                )
        
        user.login = new_login
        user.email = new_email
        user.name = request.form.get('name', '').strip()
        user.role = request.form.get('role', 'artist')
        user.copyright = request.form.get('copyright', '').strip() or None
        user.partner_code = request.form.get('partner_code', '').strip() if user.role == 'label' else None

        apply_tax_fields_from_request(user, request.form)

        if user.role != 'admin':
            restrict = request.form.get('releases_restricted') == 'on'
            restriction_title = (request.form.get('releases_restriction_title') or '').strip()
            restriction_message = (request.form.get('releases_restriction_message') or '').strip()
            if restrict and len(restriction_message) < 5:
                flash(
                    'При ограничении релизов укажите текст уведомления для пользователя (не менее 5 символов).',
                    'error',
                )
                return render_template(
                    'users/edit.html', user=user, tax_choices=User.TAX_STATUS_CHOICES
                )
            user.releases_restricted = restrict
            user.releases_restriction_title = restriction_title or None
            user.releases_restriction_message = restriction_message or None
        else:
            user.releases_restricted = False
            user.releases_restriction_title = None
            user.releases_restriction_message = None

        # Смена пароля (если указан)
        new_password = request.form.get('password', '')
        if new_password:
            password_errors = validate_password(new_password)
            if password_errors:
                for error in password_errors:
                    flash(error, 'error')
                return render_template(
                    'users/edit.html', user=user, tax_choices=User.TAX_STATUS_CHOICES
                )
            user.set_password(new_password)

        db.session.commit()
        flash('Пользователь обновлён', 'success')
        return redirect(url_for('users.view', id=id))
    
    return render_template(
        'users/edit.html', user=user, tax_choices=User.TAX_STATUS_CHOICES
    )


@users_bp.route('/users/<int:id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_status(id):
    """Блокировка/разблокировка пользователя"""
    user = User.query.get_or_404(id)
    
    # Нельзя блокировать себя
    if user.id == current_user.id:
        flash('Вы не можете заблокировать себя', 'error')
        return redirect(url_for('users.view', id=id))
    
    if user.is_active:
        reason = (request.form.get('block_reason') or '').strip()
        if len(reason) < 5:
            flash(
                'Укажите причину блокировки (не менее 5 символов) — пользователь увидит её при входе.',
                'error',
            )
            return redirect(url_for('users.view', id=id))
        user.is_active = False
        user.block_reason = reason
    else:
        user.is_active = True
        user.block_reason = None

    db.session.commit()
    
    if user.is_active:
        flash('Пользователь разблокирован', 'success')
    else:
        flash('Пользователь заблокирован', 'success')
    
    return redirect(url_for('users.view', id=id))


@users_bp.route('/users/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    """Удаление пользователя"""
    user = User.query.get_or_404(id)
    
    # Нельзя удалить себя
    if user.id == current_user.id:
        flash('Вы не можете удалить себя', 'error')
        return redirect(url_for('users.view', id=id))
    
    # Проверка наличия связанных данных
    if user.releases.count() > 0:
        flash('Нельзя удалить пользователя с релизами', 'error')
        return redirect(url_for('users.view', id=id))
    
    db.session.delete(user)
    db.session.commit()
    
    flash('Пользователь удалён', 'success')
    return redirect(url_for('users.index'))
