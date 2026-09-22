"""
Главная страница (Dashboard)
"""

import re
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, current_user

from app.models.finance import Finance
from app.models.news import News
from app.models.release import Release
from app.utils.dashboard_legal_notice import (
    DEFAULT_NOTICE_ITEM,
    load_dashboard_legal_notice,
    notices_for_template,
    save_dashboard_legal_notice,
)
from app.models.user import User
from app.utils.user_popup_notice import (
    DEFAULT_POPUP_ITEM,
    load_user_popup_notices,
    save_user_popup_notices,
)


def _form_checkbox_on(val):
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ('1', 'true', 'yes', 'on')
from app.utils.decorators import admin_required

dashboard_bp = Blueprint('dashboard', __name__)

_RU_MONTHS = (
    'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
    'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
)


def _build_quarter_cards(user, current_year, current_quarter):
    """Последние 4 квартала для переключателя на главной."""
    cards = []
    year, quarter = current_year, current_quarter
    for _ in range(4):
        amount = None
        has_data = False
        if not user.is_admin:
            finance = Finance.query.filter_by(
                user_id=user.id, year=year, quarter=quarter
            ).first()
            if finance:
                amount = finance.amount
                has_data = True
        cards.append({
            'year': year,
            'quarter': quarter,
            'label': f'{quarter}-й кв. {year}',
            'is_current': year == current_year and quarter == current_quarter,
            'amount': amount,
            'has_data': has_data,
        })
        quarter -= 1
        if quarter < 1:
            quarter = 4
            year -= 1
    return cards


def _quarter_month_tabs(year, quarter, current_month):
    start = (quarter - 1) * 3 + 1
    return [
        {
            'month': m,
            'label': _RU_MONTHS[m - 1],
            'is_current': year == datetime.now().year and m == current_month,
        }
        for m in range(start, start + 3)
    ]


@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Главная страница дашборда"""
    # Получение последней новости
    latest_news = News.query.order_by(News.created_at.desc()).first()
    
    # Получение финансовых данных по кварталам текущего года
    current_year = datetime.now().year
    quarters_data = []
    
    if not current_user.is_admin:
        # Для пользователей - их данные
        for quarter in range(1, 5):
            finance = Finance.query.filter_by(
                user_id=current_user.id,
                year=current_year,
                quarter=quarter
            ).first()
            
            quarters_data.append({
                'quarter': quarter,
                'quarter_roman': ['I', 'II', 'III', 'IV'][quarter - 1],
                'amount': finance.amount if finance else None,
                'has_data': finance is not None
            })
    else:
        # Для админов - пустые данные
        for quarter in range(1, 5):
            quarters_data.append({
                'quarter': quarter,
                'quarter_roman': ['I', 'II', 'III', 'IV'][quarter - 1],
                'amount': None,
                'has_data': False
            })
    
    # Определение текущего квартала
    current_quarter = (datetime.now().month - 1) // 3 + 1
    current_month = datetime.now().month
    quarter_cards = _build_quarter_cards(current_user, current_year, current_quarter)
    quarter_months = _quarter_month_tabs(current_year, current_quarter, current_month)
    
    # Статистика для артистов
    stats = {}
    admin_stats = {}
    if not current_user.is_admin:
        stats = {
            'total_releases': Release.query.filter_by(user_id=current_user.id).count(),
            'approved_releases': Release.query.filter_by(
                user_id=current_user.id, status='approved'
            ).count(),
            'pending_releases': Release.query.filter_by(
                user_id=current_user.id, status='moderation'
            ).count(),
            'rejected_releases': Release.query.filter_by(
                user_id=current_user.id, status='rejected'
            ).count(),
        }
    else:
        admin_stats = {
            'total_releases': Release.query.count(),
            'approved_releases': Release.query.filter_by(status='approved').count(),
            'pending_releases': Release.query.filter_by(status='moderation').count(),
            'rejected_releases': Release.query.filter_by(status='rejected').count(),
        }

    if current_user.is_admin:
        recent_releases = Release.query.order_by(Release.created_at.desc()).limit(6).all()
    else:
        recent_releases = Release.query.filter_by(
            user_id=current_user.id
        ).order_by(Release.created_at.desc()).limit(6).all()
    
    workspace_home = None
    try:
        from app.services.workspace import overview_payload
        workspace_home = overview_payload(current_user)
    except Exception:
        workspace_home = None

    return render_template(
        'dashboard/index.html',
        latest_news=latest_news,
        quarters_data=quarters_data,
        current_quarter=current_quarter,
        current_year=current_year,
        stats=stats,
        admin_stats=admin_stats,
        recent_releases=recent_releases,
        legal_notices=notices_for_template(),
        quarter_cards=quarter_cards,
        quarter_months=quarter_months,
        current_month=current_month,
        workspace_home=workspace_home,
    )


_NOTICE_FIELD_RE = re.compile(r'^notice_(\d+)_(enabled|tone|badge|title|lead|points|callout)$')


def _parse_notice_indices_from_form():
    indices = set()
    for k in request.form.keys():
        m = _NOTICE_FIELD_RE.match(k)
        if m:
            indices.add(int(m.group(1)))
    return sorted(indices)


@dashboard_bp.route('/dashboard/legal-notice', methods=['GET', 'POST'])
@login_required
@admin_required
def legal_notice_edit():
    """Редактирование одного или нескольких блоков уведомлений на главной (instance JSON)."""
    if request.method == 'POST':
        indices = _parse_notice_indices_from_form()
        if not indices:
            flash(
                'Не удалось сохранить: сервер не получил поля уведомлений. '
                'Обновите страницу и попробуйте снова.',
                'error',
            )
            return redirect(url_for('dashboard.legal_notice_edit'))
        notices = []
        for i in indices:
            tone = (request.form.get(f'notice_{i}_tone') or 'red').strip().lower()
            if tone not in ('red', 'orange'):
                tone = 'red'
            points_raw = request.form.get(f'notice_{i}_points', '') or ''
            points = [line.strip() for line in points_raw.splitlines() if line.strip()]
            badge = (request.form.get(f'notice_{i}_badge') or '').strip()
            title = (request.form.get(f'notice_{i}_title') or '').strip()
            notices.append(
                {
                    'enabled': _form_checkbox_on(request.form.get(f'notice_{i}_enabled')),
                    'tone': tone,
                    'badge': badge or DEFAULT_NOTICE_ITEM['badge'],
                    'title': title or DEFAULT_NOTICE_ITEM['title'],
                    'lead': (request.form.get(f'notice_{i}_lead') or '').strip(),
                    'points': points,
                    'callout': (request.form.get(f'notice_{i}_callout') or '').strip(),
                }
            )
        save_dashboard_legal_notice({'notices': notices})
        flash('Уведомления на главной сохранены', 'success')
        return redirect(url_for('dashboard.legal_notice_edit'))

    data = load_dashboard_legal_notice()
    notices = data.get('notices') or [dict(DEFAULT_NOTICE_ITEM)]
    rows = []
    for n in notices:
        nn = dict(n) if isinstance(n, dict) else dict(DEFAULT_NOTICE_ITEM)
        rows.append(
            {
                'notice': nn,
                'points_text': '\n'.join(nn.get('points') or []),
            }
        )
    return render_template('dashboard/legal_notice_edit.html', notice_rows=rows)


_POPUP_FIELD_RE = re.compile(
    r'^popup_(\d+)_(id|enabled|tone|badge|title|lead|points|callout)$'
)


def _parse_popup_indices_from_form():
    indices = set()
    for k in request.form.keys():
        m = _POPUP_FIELD_RE.match(k)
        if m:
            indices.add(int(m.group(1)))
    return sorted(indices)


@dashboard_bp.route('/dashboard/popup-notice', methods=['GET', 'POST'])
@login_required
@admin_required
def popup_notice_edit():
    """Редактирование всплывающих уведомлений (instance JSON)."""
    if request.method == 'POST':
        indices = _parse_popup_indices_from_form()
        if not indices:
            flash(
                'Не удалось сохранить: сервер не получил поля уведомлений. '
                'Обновите страницу и попробуйте снова.',
                'error',
            )
            return redirect(url_for('dashboard.popup_notice_edit'))

        popups = []
        for i in indices:
            tone = (request.form.get(f'popup_{i}_tone') or 'red').strip().lower()
            if tone not in ('red', 'orange'):
                tone = 'red'
            points_raw = request.form.get(f'popup_{i}_points', '') or ''
            points = [line.strip() for line in points_raw.splitlines() if line.strip()]
            user_ids = request.form.getlist(f'popup_{i}_user_ids')
            pages = request.form.getlist(f'popup_{i}_pages')
            enabled = _form_checkbox_on(request.form.get(f'popup_{i}_enabled'))
            badge = (request.form.get(f'popup_{i}_badge') or '').strip()
            title = (request.form.get(f'popup_{i}_title') or '').strip()
            if enabled and not user_ids:
                flash(
                    f'Уведомление #{i + 1}: выберите хотя бы одного пользователя или отключите показ.',
                    'error',
                )
                return redirect(url_for('dashboard.popup_notice_edit'))
            popups.append(
                {
                    'id': (request.form.get(f'popup_{i}_id') or '').strip(),
                    'enabled': enabled,
                    'tone': tone,
                    'badge': badge or DEFAULT_POPUP_ITEM['badge'],
                    'title': title or DEFAULT_POPUP_ITEM['title'],
                    'lead': (request.form.get(f'popup_{i}_lead') or '').strip(),
                    'points': points,
                    'callout': (request.form.get(f'popup_{i}_callout') or '').strip(),
                    'user_ids': user_ids,
                    'pages': pages,
                }
            )
        save_user_popup_notices({'popups': popups})
        flash('Всплывающие уведомления сохранены', 'success')
        return redirect(url_for('dashboard.popup_notice_edit'))

    data = load_user_popup_notices()
    popups = data.get('popups') or [dict(DEFAULT_POPUP_ITEM)]
    rows = []
    for p in popups:
        pp = dict(p) if isinstance(p, dict) else dict(DEFAULT_POPUP_ITEM)
        rows.append(
            {
                'popup': pp,
                'points_text': '\n'.join(pp.get('points') or []),
            }
        )
    cabinet_users = (
        User.query.filter_by(is_active=True)
        .order_by(User.name.asc(), User.login.asc())
        .all()
    )
    return render_template(
        'dashboard/popup_notice_edit.html',
        popup_rows=rows,
        cabinet_users=cabinet_users,
    )
