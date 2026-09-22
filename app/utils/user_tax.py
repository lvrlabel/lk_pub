"""Поля налоговой и платёжной информации пользователя."""

import re


def apply_tax_fields_from_request(user, form, valid_statuses=None):
    """Заполнить модель User из request.form (ключи tax_*)."""
    raw_status = (form.get('tax_status') or '').strip()
    allowed = valid_statuses
    if allowed is None:
        from app.models.user import User

        allowed = {k for k, _ in User.TAX_STATUS_CHOICES if k}
    if raw_status and raw_status not in allowed:
        raw_status = ''
    user.tax_status = raw_status or None
    user.tax_legal_name = (form.get('tax_legal_name') or '').strip()[:512] or None
    inn = re.sub(r'\D', '', form.get('tax_inn') or '')
    user.tax_inn = inn[:12] if inn else None
    acc = re.sub(r'\D', '', form.get('tax_bank_account') or '')
    user.tax_bank_account = acc[:32] if acc else None
    user.tax_bank_name = (form.get('tax_bank_name') or '').strip()[:256] or None
    bik = re.sub(r'\D', '', form.get('tax_bank_bik') or '')
    user.tax_bank_bik = bik[:9] if bik else None
