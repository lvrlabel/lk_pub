"""
Финансы
"""

import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from app import db
from app.models.finance import Finance, FinanceApproval, FinancePlatformLine
from app.models.user import User
from app.models.release import Platform
from app.utils.decorators import admin_required
from app.utils.files import save_file, delete_file, allowed_file

money_bp = Blueprint('money', __name__)


def _parse_platform_lines_from_request():
    """Строки площадок из формы загрузки отчёта (только админ)."""
    names = request.form.getlist('line_platform')
    royalties = request.form.getlist('line_royalty')
    penalties = request.form.getlist('line_penalty')
    n = max(len(names), len(royalties), len(penalties))
    out = []
    for i in range(n):
        raw = (names[i] or '').strip() if i < len(names) else ''
        if not raw:
            continue
        rs = str(royalties[i]).strip().replace(',', '.') if i < len(royalties) and royalties[i] is not None else ''
        ps = str(penalties[i]).strip().replace(',', '.') if i < len(penalties) and penalties[i] is not None else ''
        try:
            r = float(rs) if rs else 0.0
        except ValueError:
            r = 0.0
        try:
            p = float(ps) if ps else 0.0
        except ValueError:
            p = 0.0
        if r < 0 or p < 0:
            continue
        out.append(
            {
                'platform_name': raw[:128],
                'royalty_amount': round(r, 2),
                'penalty_amount': round(p, 2),
            }
        )
    return out


def _platform_name_suggestions(platforms) -> list[str]:
    """Подсказки для ввода названия площадки (datalist)."""
    defaults = [
        'Spotify',
        'Apple Music',
        'YouTube Music',
        'VK Music',
        'Яндекс Музыка',
        'Deezer',
        'Amazon Music',
        'Tidal',
        'SoundCloud',
        'YouTube Content ID',
        'YouTube Shorts',
        'TikTok',
        'TikTok Music',
        'Shazam',
        'iTunes',
        'Apple iTunes',
        'Instagram / Facebook',
        'Meta (Facebook/Instagram)',
        'Facebook',
        'Instagram',
        'Boom',
        'Одноклассники',
        'Zvooq',
        'SberZvuk',
        'MTS Music',
        'Tencent Music',
        'NetEase Cloud Music',
        'Joox',
        'Anghami',
        'Pandora',
        'Napster',
        'Audiomack',
        'Trebel',
        'Line Music',
        'AWA',
        'KKBOX',
        'Claro Musica',
        'Saavn',
        'Gaana',
        'Hungama',
    ]
    names = []
    if platforms:
        for p in platforms:
            name = (getattr(p, 'name', None) or '').strip()
            if name:
                names.append(name)
    # Добавляем площадки, которые уже использовались в финансовых отчётах.
    used_names = db.session.scalars(
        select(FinancePlatformLine.platform_name)
        .where(FinancePlatformLine.platform_name.isnot(None))
        .distinct()
        .order_by(FinancePlatformLine.platform_name.asc())
    ).all()
    for name in used_names:
        clean = (name or '').strip()
        if clean:
            names.append(clean)
    names.extend(defaults)
    # unique, keep order, case-insensitive
    seen = set()
    out = []
    for n in names:
        key = n.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def _user_finance_totals(user_id: int):
    """Начислено по отчётам, выплачено по одобренным заявкам, баланс."""
    accrued = db.session.scalar(
        select(func.coalesce(func.sum(Finance.amount), 0)).where(Finance.user_id == user_id)
    )
    accrued = float(accrued or 0)
    paid = db.session.scalar(
        select(func.coalesce(func.sum(FinanceApproval.amount), 0))
        .select_from(FinanceApproval)
        .join(Finance, FinanceApproval.finance_id == Finance.id)
        .where(Finance.user_id == user_id, FinanceApproval.status == 'approved')
    )
    paid = float(paid or 0)
    bal = round(accrued - paid, 2)
    return {'accrued': round(accrued, 2), 'paid_out': round(paid, 2), 'balance': bal}


def _format_money_rub(value: float) -> str:
    return f'{float(value):,.2f} ₽'.replace(',', ' ')


@money_bp.route('/money')
@login_required
def index():
    """Страница финансов"""
    q = Finance.query.options(
        joinedload(Finance.platform_lines),
        joinedload(Finance.user),
        joinedload(Finance.approval),
    )
    if current_user.is_admin:
        finances = q.order_by(Finance.year.desc(), Finance.quarter.desc(), Finance.id.desc()).all()
    else:
        finances = (
            q.filter_by(user_id=current_user.id)
            .order_by(Finance.year.desc(), Finance.quarter.desc())
            .all()
        )

    finances_by_year = {}
    for finance in finances:
        if finance.year not in finances_by_year:
            finances_by_year[finance.year] = []
        finances_by_year[finance.year].append(finance)

    totals = _user_finance_totals(current_user.id)

    return render_template(
        'money/index.html',
        finances=finances,
        finances_by_year=finances_by_year,
        finance_totals=totals,
        format_money=_format_money_rub,
    )


@money_bp.route('/money/<int:id>/detail')
@login_required
def finance_detail(id):
    """Детализация отчёта по площадкам (роялти и штрафы)."""
    finance = Finance.query.options(
        joinedload(Finance.platform_lines),
        joinedload(Finance.user),
        joinedload(Finance.approval),
    ).get_or_404(id)
    if not current_user.is_admin and finance.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('money.index'))
    return render_template(
        'money/finance_detail.html',
        finance=finance,
        format_money=_format_money_rub,
    )


@money_bp.route('/money/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def finance_edit(id):
    """Редактирование финансового отчёта и разбивки по площадкам (администратор)."""
    finance = Finance.query.options(joinedload(Finance.platform_lines)).get_or_404(id)
    platforms = Platform.query.filter_by(is_active=True).order_by(Platform.sort_order, Platform.name).all()
    platform_name_suggestions = _platform_name_suggestions(platforms)
    current_year = datetime.now().year
    years = list(range(current_year, current_year - 5, -1))

    if request.method == 'POST':
        quarter = request.form.get('quarter', type=int)
        year = request.form.get('year', type=int)
        amount_manual = request.form.get('amount', type=float)
        lines_data = _parse_platform_lines_from_request()

        if lines_data:
            amount = round(sum(d['royalty_amount'] - d['penalty_amount'] for d in lines_data), 2)
        else:
            if amount_manual is None:
                flash('Укажите сумму или добавьте строки по площадкам', 'error')
                return redirect(url_for('money.finance_edit', id=id))
            amount = round(float(amount_manual), 2)

        if quarter and year:
            other = Finance.query.filter(
                Finance.user_id == finance.user_id,
                Finance.quarter == quarter,
                Finance.year == year,
                Finance.id != finance.id,
            ).first()
            if other:
                flash('У этого пользователя уже есть отчёт за выбранный квартал и год', 'error')
                return redirect(url_for('money.finance_edit', id=id))

        csv_file = request.files.get('file')
        filename = finance.file_path
        if csv_file and csv_file.filename:
            if allowed_file(csv_file.filename, current_app.config['ALLOWED_FINANCE_EXTENSIONS']):
                if finance.file_path:
                    delete_file(finance.file_path, 'finances')
                filename = save_file(csv_file, 'finances')
            else:
                flash('Разрешены только CSV файлы', 'error')
                return redirect(url_for('money.finance_edit', id=id))

        finance.amount = amount
        finance.file_path = filename
        if quarter and year:
            finance.quarter = quarter
            finance.year = year

        FinancePlatformLine.query.filter_by(finance_id=finance.id).delete()
        for order, row in enumerate(lines_data):
            db.session.add(
                FinancePlatformLine(
                    finance_id=finance.id,
                    sort_order=order,
                    platform_name=row['platform_name'],
                    royalty_amount=row['royalty_amount'],
                    penalty_amount=row['penalty_amount'],
                )
            )
        db.session.commit()
        flash('Отчёт обновлён', 'success')
        return redirect(url_for('money.finance_detail', id=finance.id))

    return render_template(
        'money/finance_edit.html',
        finance=finance,
        platforms=platforms,
        platform_name_suggestions=platform_name_suggestions,
        years=years,
        format_money=_format_money_rub,
    )


@money_bp.route('/money/upload', methods=['GET', 'POST'])
@login_required
@admin_required
def upload():
    """Загрузка финансового отчёта (только администратор)."""
    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        quarter = request.form.get('quarter', type=int)
        year = request.form.get('year', type=int)
        amount_manual = request.form.get('amount', type=float)

        if not user_id or not quarter or not year:
            flash('Заполните все обязательные поля', 'error')
            return redirect(url_for('money.upload'))

        user = User.query.get(user_id)
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('money.upload'))

        existing = Finance.query.filter_by(user_id=user_id, quarter=quarter, year=year).first()
        if existing:
            flash('Отчет за этот период уже существует', 'error')
            return redirect(url_for('money.upload'))

        lines_data = _parse_platform_lines_from_request()
        if lines_data:
            amount = round(sum(d['royalty_amount'] - d['penalty_amount'] for d in lines_data), 2)
        else:
            if amount_manual is None:
                flash('Укажите сумму или добавьте строки по площадкам', 'error')
                return redirect(url_for('money.upload'))
            amount = round(float(amount_manual), 2)

        csv_file = request.files.get('file')
        filename = None
        if csv_file and csv_file.filename:
            if allowed_file(csv_file.filename, current_app.config['ALLOWED_FINANCE_EXTENSIONS']):
                filename = save_file(csv_file, 'finances')
            else:
                flash('Разрешены только CSV файлы', 'error')
                return redirect(url_for('money.upload'))

        finance = Finance(
            user_id=user_id,
            quarter=quarter,
            year=year,
            amount=amount,
            file_path=filename,
            uploaded_by=current_user.id,
        )
        db.session.add(finance)
        db.session.flush()

        for order, row in enumerate(lines_data):
            db.session.add(
                FinancePlatformLine(
                    finance_id=finance.id,
                    sort_order=order,
                    platform_name=row['platform_name'],
                    royalty_amount=row['royalty_amount'],
                    penalty_amount=row['penalty_amount'],
                )
            )

        db.session.commit()

        flash('Отчет загружен', 'success')
        return redirect(url_for('money.index'))

    users = User.query.filter(User.role != 'admin').order_by(User.name).all()
    current_year = datetime.now().year
    years = list(range(current_year, current_year - 5, -1))
    platforms = Platform.query.filter_by(is_active=True).order_by(Platform.sort_order, Platform.name).all()
    platform_name_suggestions = _platform_name_suggestions(platforms)

    return render_template(
        'money/upload.html',
        users=users,
        years=years,
        platforms=platforms,
        platform_name_suggestions=platform_name_suggestions,
    )


@money_bp.route('/money/<int:id>/download')
@login_required
def download(id):
    """Скачивание отчета"""
    finance = Finance.query.get_or_404(id)

    if not current_user.is_admin and finance.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('money.index'))

    if not finance.file_path:
        flash('Файл не найден', 'error')
        return redirect(url_for('money.index'))

    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', 'finances')
    file_path = os.path.join(upload_folder, finance.file_path)

    if not os.path.exists(file_path):
        flash('Файл не найден', 'error')
        return redirect(url_for('money.index'))

    return send_file(
        file_path,
        as_attachment=True,
        download_name=f'report_Q{finance.quarter}_{finance.year}.csv',
    )


@money_bp.route('/money/<int:id>/request-approval', methods=['GET', 'POST'])
@login_required
def request_approval(id):
    """Запрос на согласование выплаты"""
    finance = Finance.query.get_or_404(id)

    if finance.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('money.index'))

    if finance.has_approval_request:
        flash('Заявка на согласование уже подана', 'info')
        return redirect(url_for('money.index'))

    if request.method == 'POST':
        contact_info = request.form.get('contact_info', '').strip()
        amount = request.form.get('amount', finance.amount, type=float)
        card_number = request.form.get('card_number', '').strip()
        account_number = request.form.get('account_number', '').strip()

        if not card_number and not account_number:
            flash('Укажите номер карты или счета', 'error')
            return render_template('money/request_approval.html', finance=finance)

        approval = FinanceApproval(
            finance_id=finance.id,
            user_id=current_user.id,
            contact_info=contact_info,
            amount=amount,
            card_number=card_number.replace(' ', '') if card_number else None,
            account_number=account_number if account_number else None,
            status='pending',
        )

        db.session.add(approval)
        db.session.commit()

        flash('Заявка на согласование отправлена', 'success')
        return redirect(url_for('money.index'))

    return render_template('money/request_approval.html', finance=finance)


@money_bp.route('/money/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    """Удаление отчета"""
    finance = Finance.query.options(
        joinedload(Finance.platform_lines),
        joinedload(Finance.approval),
    ).get_or_404(id)

    file_path = finance.file_path
    try:
        # Явно убираем связанные записи — надёжнее, чем полагаться только на cascade
        FinancePlatformLine.query.filter_by(finance_id=finance.id).delete(synchronize_session=False)
        FinanceApproval.query.filter_by(finance_id=finance.id).delete(synchronize_session=False)
        db.session.delete(finance)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception('money.delete finance #%s: %s', id, e)
        flash('Не удалось удалить отчёт. Возможно, есть связанные данные.', 'error')
        return redirect(url_for('money.finance_detail', id=id))

    if file_path:
        try:
            delete_file(file_path, 'finances')
        except Exception as e:
            current_app.logger.warning('money.delete file %s: %s', file_path, e)

    flash('Отчёт удалён', 'success')
    return redirect(url_for('money.index'))


@money_bp.route('/finance_approvals')
@login_required
@admin_required
def approvals():
    """Список заявок на согласование"""
    status = request.args.get('status', 'pending')

    query = FinanceApproval.query
    if status:
        query = query.filter_by(status=status)

    approvals_list = query.order_by(FinanceApproval.created_at.desc()).all()

    counts = {
        'pending': FinanceApproval.query.filter_by(status='pending').count(),
        'approved': FinanceApproval.query.filter_by(status='approved').count(),
        'rejected': FinanceApproval.query.filter_by(status='rejected').count(),
    }

    return render_template(
        'money/approvals.html',
        approvals=approvals_list,
        status=status,
        counts=counts,
    )


@money_bp.route('/finance_approvals/<int:id>')
@login_required
@admin_required
def view_approval(id):
    """Просмотр заявки"""
    approval = FinanceApproval.query.get_or_404(id)
    return render_template('money/view_approval.html', approval=approval)


@money_bp.route('/finance_approvals/<int:id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_approval(id):
    """Одобрение заявки"""
    approval = FinanceApproval.query.get_or_404(id)

    if approval.status != 'pending':
        flash('Заявка уже обработана', 'error')
        return redirect(url_for('money.view_approval', id=id))

    comment = request.form.get('comment', '').strip()

    approval.status = 'approved'
    approval.admin_comment = comment or None
    approval.processed_at = datetime.utcnow()

    db.session.commit()

    flash('Заявка одобрена', 'success')
    return redirect(url_for('money.approvals'))


@money_bp.route('/finance_approvals/<int:id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_approval(id):
    """Отклонение заявки"""
    approval = FinanceApproval.query.get_or_404(id)

    if approval.status != 'pending':
        flash('Заявка уже обработана', 'error')
        return redirect(url_for('money.view_approval', id=id))

    comment = request.form.get('comment', '').strip()
    if not comment:
        flash('Укажите причину отклонения', 'error')
        return redirect(url_for('money.view_approval', id=id))

    approval.status = 'rejected'
    approval.admin_comment = comment
    approval.processed_at = datetime.utcnow()

    db.session.commit()

    flash('Заявка отклонена', 'success')
    return redirect(url_for('money.approvals'))
