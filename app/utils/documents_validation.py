"""
Валидация входных данных для документооборота (счета, подтверждения).
Без сырого SQL — только проверки перед ORM.
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

def parse_positive_amount(raw):
    """
    Сумма > 0, до 2 знаков после запятой, разумный максимум.
    Возвращает (Decimal|None, error_message|None).
    """
    if raw is None:
        return None, 'Укажите сумму'
    s = str(raw).strip().replace(',', '.').replace(' ', '')
    if not s:
        return None, 'Укажите сумму'
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None, 'Некорректная сумма'
    if d != d.quantize(Decimal('0.01')):
        return None, 'Сумма не более двух знаков после запятой'
    if d <= 0:
        return None, 'Сумма должна быть больше нуля'
    if d > Decimal('999999999999.99'):
        return None, 'Сумма слишком велика'
    return d, None


def normalize_currency(raw, default='RUB'):
    """Код валюты 3 буквы (ISO-подобно), верхний регистр."""
    if raw is None or not str(raw).strip():
        return default, None
    c = str(raw).strip().upper()
    if not re.match(r'^[A-Z]{3}$', c):
        return None, 'Код валюты — три латинские буквы (например, RUB)'
    return c, None


def parse_optional_date(raw):
    """Дата YYYY-MM-DD или пусто."""
    if raw is None or not str(raw).strip():
        return None, None
    s = str(raw).strip()
    try:
        return datetime.strptime(s, '%Y-%m-%d').date(), None
    except ValueError:
        return None, 'Некорректная дата (ожидается ГГГГ-ММ-ДД)'


def clean_short_text(raw, max_len, field_name='Поле'):
    if raw is None:
        return '', None
    t = str(raw).strip()
    if len(t) > max_len:
        return None, f'{field_name}: не более {max_len} символов'
    return t, None


def clean_optional_url(raw, max_len=2048):
    if raw is None or not str(raw).strip():
        return None, None
    u = str(raw).strip()
    if len(u) > max_len:
        return None, f'Ссылка не длиннее {max_len} символов'
    if not (u.startswith('http://') or u.startswith('https://')):
        return None, 'Ссылка на оплату должна начинаться с http:// или https://'
    return u, None


def validate_invoice_number(raw):
    """Номер счёта: буквы, цифры, дефис, подчёркивание, до 64 символов."""
    if raw is None or not str(raw).strip():
        return None, 'Укажите номер счёта'
    s = str(raw).strip()
    if len(s) > 64:
        return None, 'Номер счёта не длиннее 64 символов'
    if not re.match(r'^[\w\-./]+$', s, re.UNICODE):
        return None, 'Номер счёта: допустимы буквы, цифры, - _ . /'
    return s, None


def validate_confirmation_number(raw):
    if raw is None or not str(raw).strip():
        return None, None
    s = str(raw).strip()
    if len(s) > 128:
        return None, 'Номер подтверждения не длиннее 128 символов'
    return s, None
