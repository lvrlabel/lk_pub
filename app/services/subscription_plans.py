"""Тарифы подписки Toolls (ЮKassa Simple Pay)."""

from decimal import Decimal

SUBSCRIPTION_PLANS = {
    'start': {
        'code': 'start',
        'name': 'Старт',
        'amount': Decimal('500.00'),
        'currency': 'RUB',
        'subject': 'Оплата тарифа Старт',
        'yookassa_text': 'Старт',
        'yookassa_price': '500',
        'customer_number': 'Оплата подписки Старт',
    },
    'premium': {
        'code': 'premium',
        'name': 'Премиум',
        'amount': Decimal('1000.00'),
        'currency': 'RUB',
        'subject': 'Оплата тарифа Премиум',
        'yookassa_text': 'Премиум',
        'yookassa_price': '1000',
        'customer_number': 'Оплата подписки Премиум',
    },
}


def get_plan(code):
    if not code:
        return None
    return SUBSCRIPTION_PLANS.get(str(code).strip().lower())


def plan_choices():
    return [(k, v['name']) for k, v in SUBSCRIPTION_PLANS.items()]
