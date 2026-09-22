"""Ограничение создания и отправки релизов для пользователя."""


def user_releases_restricted(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return bool(getattr(user, 'is_releases_restricted', False))


def releases_restriction_flash_message(user):
    popup = user.releases_restriction_popup() if user else None
    if popup and popup.get('lead'):
        return popup['lead']
    return 'Создание и отправка новых релизов временно ограничены администратором.'
