"""Выставление счетов ЮKassa через API."""

import uuid
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app


def create_invoice(*, amount, currency, subject, invoice_number, due_date=None):
    """Создаёт счет ЮKassa и возвращает (invoice_id, payment_url)."""
    shop_id = current_app.config.get('YOOKASSA_SHOP_ID')
    secret_key = current_app.config.get('YOOKASSA_SECRET_KEY')
    if not shop_id or not secret_key:
        raise RuntimeError('Не настроен секретный ключ API ЮKassa')

    expires_at = datetime.combine(
        due_date,
        datetime.max.time().replace(microsecond=0),
        tzinfo=timezone.utc,
    ) if due_date else datetime.now(timezone.utc) + timedelta(days=30)
    value = f'{Decimal(str(amount)):.2f}'
    payload = {
        'payment_data': {
            'amount': {'value': value, 'currency': currency},
            'capture': True,
            'description': subject[:128],
            'metadata': {'invoice_number': invoice_number},
        },
        'cart': [{
            'description': subject[:128],
            'price': {'value': value, 'currency': currency},
            'quantity': 1,
        }],
        'delivery_method_data': {'type': 'self'},
        'locale': 'ru_RU',
        'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
        'description': f'Счёт {invoice_number}: {subject}'[:128],
    }
    credentials = f'{shop_id}:{secret_key}'.encode('utf-8')
    import base64
    auth_header = base64.b64encode(credentials).decode('ascii')
    request = Request(
        f"{current_app.config.get('YOOKASSA_API_URL').rstrip('/')}/invoices",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/json',
            'Idempotence-Key': str(uuid.uuid4()),
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, ValueError) as exc:
        details = getattr(exc, 'read', lambda: b'')()
        current_app.logger.error('YooKassa invoice failed: %s %s', exc, details[:1000])
        raise RuntimeError('ЮKassa не смогла создать счет') from exc
    url = (data.get('delivery_method') or {}).get('url')
    if not data.get('id') or not url:
        raise RuntimeError('ЮKassa вернула счет без ссылки на оплату')
    return data['id'], url