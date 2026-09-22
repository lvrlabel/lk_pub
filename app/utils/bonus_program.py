"""
Бонусная программа: каталог услуг и операции с балансом.
"""

from flask import current_app

from app import db
from app.models.bonus import BonusTransaction


DEFAULT_BONUS_SERVICES = {
    'single': {'title': 'Выпуск сингла', 'cost': 100},
    'ep': {'title': 'Выпуск EP', 'cost': 300},
    'album': {'title': 'Выпуск альбома', 'cost': 600},
    'lyrics': {'title': 'Текст на площадки', 'cost': 50},
}


def bonus_services_catalog():
    """Каталог услуг, на которые можно потратить бонусы."""
    configured = current_app.config.get('BONUS_SERVICES') or {}
    catalog = {}
    for key, defaults in DEFAULT_BONUS_SERVICES.items():
        override = configured.get(key) or {}
        catalog[key] = {
            'key': key,
            'title': (override.get('title') or defaults['title']).strip(),
            'cost': int(override.get('cost', defaults['cost'])),
        }
    return catalog


def bonus_services_for_user(balance):
    """Каталог с флагом доступности по текущему балансу."""
    items = []
    for key, item in bonus_services_catalog().items():
        cost = int(item['cost'])
        items.append({
            **item,
            'affordable': balance >= cost,
            'remaining': max(balance - cost, 0),
        })
    return items


def apply_bonus_credit(user, amount, admin, comment=None):
    """Начислить бонусы пользователю (только администратор)."""
    amount = int(amount)
    if amount <= 0:
        raise ValueError('Сумма начисления должна быть больше нуля')
    comment = (comment or '').strip() or None

    user.bonus_balance = int(user.bonus_balance or 0) + amount
    tx = BonusTransaction(
        user_id=user.id,
        amount=amount,
        transaction_type=BonusTransaction.TYPE_CREDIT,
        comment=comment,
        created_by_id=admin.id if admin else None,
    )
    db.session.add(tx)
    return tx


def apply_bonus_debit(user, amount, admin, comment=None, service_key=None):
    """Списать бонусы у пользователя (только администратор)."""
    amount = int(amount)
    if amount <= 0:
        raise ValueError('Сумма списания должна быть больше нуля')

    balance = int(user.bonus_balance or 0)
    if balance < amount:
        raise ValueError(f'Недостаточно бонусов: на счёте {balance}, нужно {amount}')

    service_key = (service_key or '').strip() or None
    if service_key:
        catalog = bonus_services_catalog()
        if service_key not in catalog:
            raise ValueError('Неизвестная услуга для списания')
        if not comment:
            comment = catalog[service_key]['title']
    comment = (comment or '').strip() or None

    user.bonus_balance = balance - amount
    tx = BonusTransaction(
        user_id=user.id,
        amount=amount,
        transaction_type=BonusTransaction.TYPE_DEBIT,
        comment=comment,
        service_key=service_key,
        created_by_id=admin.id if admin else None,
    )
    db.session.add(tx)
    return tx
