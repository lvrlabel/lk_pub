"""
Документооборот: счета, оплата ЮKassa, подтверждения, уведомления.
"""

import os
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from app import db
from app.models.invoice import DocNotification, Invoice, PaymentConfirmation
from app.models.user import User
from app.services.document_workflow_service import (
    add_payment_confirmation_and_pay,
    cancel_invoice_admin,
    create_invoice_with_notification,
    mark_invoice_paid_manual,
    refresh_invoices_overdue,
)
from app.services.subscription_plans import get_plan, plan_choices, SUBSCRIPTION_PLANS
from app.services.subscription_service import activate_subscription_from_invoice
from app.services.yookassa_invoices import create_invoice as create_yookassa_invoice
from app.utils.decorators import active_user_required, admin_required
from app.utils.documents_validation import (
    clean_short_text,
    normalize_currency,
    parse_optional_date,
    parse_positive_amount,
    validate_confirmation_number,
    validate_invoice_number,
)
from app.utils.files import allowed_file, save_file

documents_bp = Blueprint('documents', __name__, url_prefix='/documents')

DOC_CONFIRM_SUBFOLDER = 'documents/payment_confirmations'


def _invoice_query_for_user(user_id):
    return Invoice.query.filter_by(user_id=user_id).order_by(Invoice.created_at.desc())


def _invoice_bucket_counts(user_id):
    base = Invoice.query.filter_by(user_id=user_id)
    return {
        'active': base.filter(Invoice.status.in_((Invoice.STATUS_PENDING, Invoice.STATUS_OVERDUE))).count(),
        'paid': base.filter_by(status=Invoice.STATUS_PAID).count(),
        'cancelled': base.filter_by(status=Invoice.STATUS_CANCELLED).count(),
        'all': base.count(),
    }


def _filter_invoices_by_bucket(q, bucket):
    bucket = (bucket or 'active').strip().lower()
    if bucket == 'paid':
        return q.filter_by(status=Invoice.STATUS_PAID)
    if bucket == 'cancelled':
        return q.filter_by(status=Invoice.STATUS_CANCELLED)
    if bucket == 'all':
        return q
    return q.filter(Invoice.status.in_((Invoice.STATUS_PENDING, Invoice.STATUS_OVERDUE)))


def _next_invoice_number():
    year = datetime.utcnow().year
    prefix = f'INV-{year}-'
    last = (
        Invoice.query.filter(Invoice.invoice_number.like(f'{prefix}%'))
        .order_by(Invoice.id.desc())
        .first()
    )
    if not last:
        return f'{prefix}001'
    tail = last.invoice_number.rsplit('-', 1)[-1]
    try:
        n = int(tail) + 1
    except ValueError:
        n = 1
    return f'{prefix}{n:03d}'


def _set_invoice_payment_link(inv):
    inv.payment_link = url_for('documents.invoice_payment', id=inv.id, _external=True)


def _finalize_invoice_payment(inv):
  """Активировать подписку после оплаты (если ещё не сделано в сервисе)."""
  activate_subscription_from_invoice(inv)
  db.session.commit()


@documents_bp.route('/invoices')
@login_required
@active_user_required
def hub_invoices():
    bucket = request.args.get('bucket', 'active')
    q = _invoice_query_for_user(current_user.id)
    refresh_invoices_overdue(q.filter(Invoice.status == Invoice.STATUS_PENDING))
    q = _filter_invoices_by_bucket(_invoice_query_for_user(current_user.id), bucket)
    invoices = q.all()
    return render_template(
        'documents/invoices_user.html',
        invoices=invoices,
        bucket=bucket,
        counts=_invoice_bucket_counts(current_user.id),
    )


@documents_bp.route('/confirmations')
@login_required
@active_user_required
def hub_confirmations():
    items = (
        PaymentConfirmation.query.filter_by(user_id=current_user.id)
        .order_by(PaymentConfirmation.created_at.desc())
        .all()
    )
    return render_template('documents/confirmations_user.html', items=items)


@documents_bp.route('/messages')
@login_required
@active_user_required
def hub_messages():
    items = (
        DocNotification.query.filter_by(user_id=current_user.id)
        .order_by(DocNotification.created_at.desc())
        .limit(100)
        .all()
    )
    unread_count = DocNotification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return render_template('documents/messages_user.html', items=items, unread_count=unread_count)


@documents_bp.route('/messages/<int:id>/read', methods=['POST'])
@login_required
@active_user_required
def message_mark_read(id):
    note = DocNotification.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    note.is_read = True
    db.session.commit()
    return redirect(url_for('documents.hub_messages'))


@documents_bp.route('/messages/read-all', methods=['POST'])
@login_required
@active_user_required
def messages_mark_all_read():
    DocNotification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('Все уведомления отмечены прочитанными', 'success')
    return redirect(url_for('documents.hub_messages'))


@documents_bp.route('/invoices/<int:id>/pay')
@login_required
@active_user_required
def invoice_payment(id):
    inv = Invoice.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    if not inv.is_active_unpaid:
        flash('Этот счёт уже оплачен или отменён', 'info')
        return redirect(url_for('documents.hub_invoices'))

    plan = get_plan(inv.plan_code)
    if not plan:
        plan = {
            'name': inv.subject,
            'amount': inv.amount,
            'yookassa_text': inv.subject,
            'yookassa_price': str(inv.amount),
            'customer_number': f'Оплата счёта {inv.invoice_number}',
        }
    else:
        plan = dict(plan)
        plan['name'] = inv.subject
        plan['amount'] = inv.amount
        plan['yookassa_text'] = inv.subject
        plan['yookassa_price'] = str(inv.amount)
        plan['customer_number'] = f'Оплата счёта {inv.invoice_number}'

    success_url = url_for('documents.invoice_payment_success', id=inv.id, _external=True)
    shop_id = current_app.config.get('YOOKASSA_SHOP_ID')
    return render_template(
        'documents/invoice_payment.html',
        invoice=inv,
        plan=plan,
        success_url=success_url,
        shop_id=shop_id,
    )


@documents_bp.route('/webhooks/yookassa', methods=['POST'])
def yookassa_webhook():
    """Обновляет локальный счет после уведомления об успешном платеже."""
    payload = request.get_json(silent=True) or {}
    if payload.get('event') != 'payment.succeeded':
        return '', 200

    payment = payload.get('object') or {}
    yookassa_id = (payment.get('invoice_details') or {}).get('id')
    if not yookassa_id:
        return '', 200

    inv = Invoice.query.filter_by(yookassa_invoice_id=yookassa_id).first()
    if not inv or inv.status == Invoice.STATUS_PAID:
        return '', 200
    if inv.status not in (Invoice.STATUS_PENDING, Invoice.STATUS_OVERDUE):
        return '', 200

    inv.status = Invoice.STATUS_PAID
    inv.paid_at = datetime.utcnow()
    db.session.add(DocNotification(
        user_id=inv.user_id,
        type=DocNotification.TYPE_PAYMENT_CONFIRMED,
        title=f'Оплата по счёту {inv.invoice_number} получена',
        message='Оплата подтверждена ЮKassa. Подписка активирована.',
        is_read=False,
        related_invoice_id=inv.id,
    ))
    activate_subscription_from_invoice(inv)
    db.session.commit()
    return '', 200


@documents_bp.route('/invoices/<int:id>/payment-success')
@login_required
@active_user_required
def invoice_payment_success(id):
    inv = Invoice.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    if inv.status == Invoice.STATUS_PAID:
        flash('Счёт уже был обработан ранее', 'info')
    else:
        flash('Статус оплаты будет подтверждён ЮKassa автоматически.', 'info')
    return redirect(url_for('documents.hub_invoices'))


@documents_bp.route('/invoices/<int:id>/upload-confirmation', methods=['POST'])
@login_required
@active_user_required
def upload_confirmation(id):
    inv = Invoice.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    if not inv.is_active_unpaid:
        flash('Для этого счёта нельзя загрузить подтверждение', 'warning')
        return redirect(url_for('documents.hub_invoices'))

    pdf = request.files.get('document_file')
    if not pdf or not pdf.filename:
        flash('Выберите PDF-файл', 'error')
        return redirect(url_for('documents.hub_invoices'))

    if not allowed_file(pdf.filename, current_app.config['ALLOWED_DOC_CONFIRM_EXTENSIONS']):
        flash('Допустим только формат PDF', 'error')
        return redirect(url_for('documents.hub_invoices'))

    pdf.seek(0, os.SEEK_END)
    size = pdf.tell()
    pdf.seek(0)
    if size > current_app.config.get('MAX_DOC_CONFIRM_SIZE', 15 * 1024 * 1024):
        flash('Файл слишком большой', 'error')
        return redirect(url_for('documents.hub_invoices'))

    filename = save_file(pdf, DOC_CONFIRM_SUBFOLDER)
    if not filename:
        flash('Не удалось сохранить файл', 'error')
        return redirect(url_for('documents.hub_invoices'))

    conf_num, err = validate_confirmation_number(request.form.get('confirmation_number'))
    if err:
        flash(err, 'error')
        return redirect(url_for('documents.hub_invoices'))

    pay_date, err = parse_optional_date(request.form.get('payment_date'))
    if err:
        flash(err, 'error')
        return redirect(url_for('documents.hub_invoices'))

    amount_raw = request.form.get('amount')
    amount = None
    if amount_raw and str(amount_raw).strip():
        amount, err = parse_positive_amount(amount_raw)
        if err:
            flash(err, 'error')
            return redirect(url_for('documents.hub_invoices'))

    comment, err = clean_short_text(request.form.get('comment'), 2000, 'Комментарий')
    if err:
        flash(err, 'error')
        return redirect(url_for('documents.hub_invoices'))

    pc, err = add_payment_confirmation_and_pay(
        invoice_id=inv.id,
        user_id=current_user.id,
        document_filename=filename,
        confirmation_number=conf_num,
        payment_date=pay_date,
        amount=amount,
        comment=comment or None,
    )
    if err:
        flash(err, 'error')
        return redirect(url_for('documents.hub_invoices'))

    flash('Подтверждение загружено, счёт закрыт. Подписка активирована.', 'success')
    return redirect(url_for('documents.hub_invoices'))


@documents_bp.route('/confirmations/<int:id>/download')
@login_required
@active_user_required
def download_confirmation(id):
    pc = PaymentConfirmation.query.get_or_404(id)
    if not current_user.is_admin and pc.user_id != current_user.id:
        abort(403)
    if not pc.document_file:
        abort(404)
    folder = os.path.join(current_app.root_path, '..', 'uploads', DOC_CONFIRM_SUBFOLDER)
    return send_from_directory(folder, pc.document_file, as_attachment=True)


# --- Админ ---


@documents_bp.route('/admin/invoices')
@login_required
@admin_required
def admin_invoices():
    q = Invoice.query.order_by(Invoice.created_at.desc())
    refresh_invoices_overdue(Invoice.query.filter(Invoice.status == Invoice.STATUS_PENDING))

    filter_status = request.args.get('status', '').strip()
    filter_user_id = request.args.get('user_id', type=int)

    if filter_status:
        q = q.filter_by(status=filter_status)
    if filter_user_id:
        q = q.filter_by(user_id=filter_user_id)

    users = User.query.filter(User.role != 'admin').order_by(User.name, User.login).all()
    return render_template(
        'documents/admin/invoices.html',
        invoices=q.limit(200).all(),
        users=users,
        filter_status=filter_status,
        filter_user_id=filter_user_id,
    )


@documents_bp.route('/admin/invoices/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_invoice_create():
    users = User.query.filter(User.role != 'admin', User.is_active == True).order_by(User.name, User.login).all()  # noqa: E712
    suggested_number = _next_invoice_number()

    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        if not user_id or not User.query.filter_by(id=user_id).filter(User.role != 'admin').first():
            flash('Выберите пользователя', 'error')
            return render_template(
                'documents/admin/invoice_new.html',
                users=users,
                suggested_number=suggested_number,
                plan_choices=plan_choices(),
                plans=SUBSCRIPTION_PLANS,
            )

        plan_code = (request.form.get('plan_code') or '').strip().lower()
        plan = get_plan(plan_code)

        invoice_number, err = validate_invoice_number(request.form.get('invoice_number'))
        if err:
            flash(err, 'error')
            return render_template(
                'documents/admin/invoice_new.html',
                users=users,
                suggested_number=suggested_number,
                plan_choices=plan_choices(),
                plans=SUBSCRIPTION_PLANS,
            )

        amount, err = parse_positive_amount(request.form.get('amount'))
        if err:
            flash(err, 'error')
            return render_template(
                'documents/admin/invoice_new.html',
                users=users,
                suggested_number=suggested_number,
                plan_choices=plan_choices(),
                plans=SUBSCRIPTION_PLANS,
            )
        currency, err = normalize_currency(request.form.get('currency'))
        if err:
            flash(err, 'error')
            return render_template(
                'documents/admin/invoice_new.html',
                users=users,
                suggested_number=suggested_number,
                plan_choices=plan_choices(),
                plans=SUBSCRIPTION_PLANS,
            )
        subject, err = clean_short_text(request.form.get('subject'), 512, 'Тема')
        if err or not subject:
            flash(err or 'Укажите тему счёта', 'error')
            return render_template(
                'documents/admin/invoice_new.html',
                users=users,
                suggested_number=suggested_number,
                plan_choices=plan_choices(),
                plans=SUBSCRIPTION_PLANS,
            )

        description, err = clean_short_text(request.form.get('description'), 4000, 'Описание')
        if err:
            flash(err, 'error')
            return render_template(
                'documents/admin/invoice_new.html',
                users=users,
                suggested_number=suggested_number,
                plan_choices=plan_choices(),
                plans=SUBSCRIPTION_PLANS,
            )

        due_date, err = parse_optional_date(request.form.get('due_date'))
        if err:
            flash(err, 'error')
            return render_template(
                'documents/admin/invoice_new.html',
                users=users,
                suggested_number=suggested_number,
                plan_choices=plan_choices(),
                plans=SUBSCRIPTION_PLANS,
            )

        try:
            yookassa_id, yookassa_url = create_yookassa_invoice(
                amount=amount,
                currency=currency,
                subject=subject,
                invoice_number=invoice_number,
                due_date=due_date,
            )
        except Exception as e:
            current_app.logger.warning('YooKassa invoice creation failed: %s', e)
            flash(str(e), 'error')
            return render_template(
                'documents/admin/invoice_new.html',
                users=users,
                suggested_number=suggested_number,
                plan_choices=plan_choices(),
                plans=SUBSCRIPTION_PLANS,
            )

        inv, err = create_invoice_with_notification(
            user_id=user_id,
            invoice_number=invoice_number,
            amount=amount,
            currency=currency,
            subject=subject,
            description=description or None,
            payment_link=yookassa_url,
            due_date=due_date,
            created_by_admin_id=current_user.id,
            plan_code=plan_code if plan else None,
        )
        if err:
            flash(err, 'error')
            return render_template(
                'documents/admin/invoice_new.html',
                users=users,
                suggested_number=suggested_number,
                plan_choices=plan_choices(),
                plans=SUBSCRIPTION_PLANS,
            )

        if plan:
            inv.plan_code = plan_code
        inv.yookassa_invoice_id = yookassa_id
        inv.payment_link = yookassa_url
        db.session.commit()

        from app.utils.email import send_invoice_created_email
        from app.services.telegram_bot import send_invoice_created

        try:
            send_invoice_created_email(inv)
        except Exception as e:
            current_app.logger.warning('invoice created email failed: %s', e)

        try:
            send_invoice_created(inv)
        except Exception as e:
            current_app.logger.warning('invoice created telegram failed: %s', e)

        flash(f'Счёт {inv.invoice_number} создан', 'success')
        return redirect(url_for('documents.admin_invoices'))

    return render_template(
        'documents/admin/invoice_new.html',
        users=users,
        suggested_number=suggested_number,
        plan_choices=plan_choices(),
        plans=SUBSCRIPTION_PLANS,
    )


@documents_bp.route('/admin/invoices/<int:id>/pay', methods=['POST'])
@login_required
@admin_required
def admin_invoice_pay(id):
    ok, err = mark_invoice_paid_manual(id)
    if not ok:
        flash(err or 'Ошибка', 'error')
        return redirect(url_for('documents.admin_invoices'))
    flash('Счёт отмечен как оплаченный', 'success')
    return redirect(url_for('documents.admin_invoices'))


@documents_bp.route('/admin/invoices/<int:id>/cancel', methods=['POST'])
@login_required
@admin_required
def admin_invoice_cancel(id):
    ok, err = cancel_invoice_admin(id)
    if not ok:
        flash(err or 'Ошибка', 'error')
    else:
        flash('Счёт отменён', 'success')
    return redirect(url_for('documents.admin_invoices'))


@documents_bp.route('/admin/confirmations', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_confirmations():
    pending_invoices = (
        Invoice.query.filter(Invoice.status.in_((Invoice.STATUS_PENDING, Invoice.STATUS_OVERDUE)))
        .order_by(Invoice.created_at.desc())
        .all()
    )

    if request.method == 'POST':
        invoice_id = request.form.get('invoice_id', type=int)
        inv = Invoice.query.get(invoice_id) if invoice_id else None
        if not inv or not inv.is_active_unpaid:
            flash('Выберите счёт, ожидающий оплаты', 'error')
            return redirect(url_for('documents.admin_confirmations'))

        pdf = request.files.get('document')
        if not pdf or not pdf.filename:
            flash('Выберите PDF-файл', 'error')
            return redirect(url_for('documents.admin_confirmations'))

        if not allowed_file(pdf.filename, current_app.config['ALLOWED_DOC_CONFIRM_EXTENSIONS']):
            flash('Допустим только формат PDF', 'error')
            return redirect(url_for('documents.admin_confirmations'))

        filename = save_file(pdf, DOC_CONFIRM_SUBFOLDER)
        if not filename:
            flash('Не удалось сохранить файл', 'error')
            return redirect(url_for('documents.admin_confirmations'))

        conf_num, err = validate_confirmation_number(request.form.get('confirmation_number'))
        if err:
            flash(err, 'error')
            return redirect(url_for('documents.admin_confirmations'))

        pay_date, err = parse_optional_date(request.form.get('payment_date'))
        if err:
            flash(err, 'error')
            return redirect(url_for('documents.admin_confirmations'))

        amount = None
        amount_raw = request.form.get('amount')
        if amount_raw and str(amount_raw).strip():
            amount, err = parse_positive_amount(amount_raw)
            if err:
                flash(err, 'error')
                return redirect(url_for('documents.admin_confirmations'))

        comment, err = clean_short_text(request.form.get('comment'), 2000, 'Комментарий')
        if err:
            flash(err, 'error')
            return redirect(url_for('documents.admin_confirmations'))

        _, err = add_payment_confirmation_and_pay(
            invoice_id=inv.id,
            user_id=inv.user_id,
            document_filename=filename,
            confirmation_number=conf_num,
            payment_date=pay_date,
            amount=amount,
            comment=comment or None,
        )
        if err:
            flash(err, 'error')
        else:
            flash('Подтверждение сохранено, счёт закрыт', 'success')
        return redirect(url_for('documents.admin_confirmations'))

    confirmations = PaymentConfirmation.query.order_by(PaymentConfirmation.created_at.desc()).limit(200).all()
    return render_template(
        'documents/admin/confirmations.html',
        pending_invoices=pending_invoices,
        confirmations=confirmations,
    )
