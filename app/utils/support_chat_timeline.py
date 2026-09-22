"""
Сборка ленты чата поддержки с разделителями дат.
"""


def _should_skip_first_duplicate(ticket, messages):
    if not messages or not ticket.message:
        return False
    first = messages[0]
    if first.message != ticket.message:
        return False
    if ticket.initiator == 'admin' and first.is_admin:
        return True
    if ticket.initiator != 'admin' and not first.is_admin:
        return True
    return False


def _from_me(viewer_is_admin, is_admin_message):
    return bool(is_admin_message) == bool(viewer_is_admin)


def build_support_chat_timeline(ticket, messages, viewer_is_admin):
    """Возвращает список элементов: date | message."""
    items = []
    last_date_key = None
    skip_first = _should_skip_first_duplicate(ticket, messages)

    def push_date(date_key, label):
        nonlocal last_date_key
        if not date_key or date_key == last_date_key:
            return
        last_date_key = date_key
        items.append({'type': 'date', 'label': label})

    if ticket.message:
        push_date(ticket.date_key, ticket.date_label)
        items.append({
            'type': 'message',
            'kind': 'initial',
            'text': ticket.message,
            'time': ticket.chat_time_formatted,
            'from_me': _from_me(viewer_is_admin, ticket.initiator == 'admin'),
            'is_admin': ticket.initiator == 'admin',
            'msg': None,
        })

    for index, msg in enumerate(messages):
        if skip_first and index == 0:
            continue
        push_date(msg.date_key, msg.date_label)
        items.append({
            'type': 'message',
            'kind': 'reply',
            'text': msg.message,
            'time': msg.chat_time_formatted,
            'from_me': _from_me(viewer_is_admin, msg.is_admin),
            'is_admin': msg.is_admin,
            'msg': msg,
        })

    return items
