"""
Запись событий релиза в журнал модерации.
"""

from sqlalchemy.orm import joinedload

from app import db
from app.models.release import Release
from app.models.release_event import ReleaseEvent


def log_release_event(release, event_type, actor=None, comment=None, extra=None, *, commit=True):
    """Добавить событие в историю релиза."""
    event = ReleaseEvent(
        release_id=release.id,
        actor_user_id=actor.id if actor else None,
        event_type=event_type,
        comment=comment,
        extra=extra,
    )
    db.session.add(event)
    if commit:
        db.session.commit()
    return event


def _last_submitted_at(release_id):
    row = (
        ReleaseEvent.query.filter_by(release_id=release_id, event_type='submitted')
        .order_by(ReleaseEvent.created_at.desc())
        .first()
    )
    return row.created_at if row else None


def log_admin_viewed_if_needed(release, admin_user):
    """
    Зафиксировать первое открытие релиза модератором после последней отправки на модерацию.
    """
    if release.status != 'moderation':
        return None

    since = _last_submitted_at(release.id)
    q = ReleaseEvent.query.filter_by(release_id=release.id, event_type='admin_viewed')
    if since:
        q = q.filter(ReleaseEvent.created_at >= since)
    if q.first():
        return None

    return log_release_event(release, 'admin_viewed', actor=admin_user)


def get_release_events(release_id, viewer=None, release=None):
    """
    События релиза в хронологическом порядке (сначала старые).

    Администратор и владелец релиза видят полную историю, включая «Открыт модератором».
    """
    events = (
        ReleaseEvent.query.options(joinedload(ReleaseEvent.actor))
        .filter_by(release_id=release_id)
        .order_by(ReleaseEvent.created_at.asc())
        .all()
    )
    if not viewer or viewer.is_admin:
        return events

    owner_id = release.user_id if release else None
    if owner_id is None:
        owner_id = Release.query.with_entities(Release.user_id).filter_by(id=release_id).scalar()
    if owner_id and viewer.id == owner_id:
        return events

    return [event for event in events if event.event_type != 'admin_viewed']
