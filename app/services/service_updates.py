"""
Синхронизация и чтение журнала обновлений сервиса.
"""

import json
import os
import uuid
from datetime import datetime

from app import db
from app.models.service_update import ServiceUpdate, ServiceUpdateRead


def _manifest_path(app):
    return os.path.join(app.root_path, 'data', 'service_updates.manifest.json')


def _parse_created_at(raw):
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def sync_service_updates_from_manifest(app):
    """Импортировать записи из манифеста (при деплое / старте приложения)."""
    path = _manifest_path(app)
    if not os.path.isfile(path):
        return 0

    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        app.logger.warning('service_updates manifest: %s', e)
        return 0

    items = data.get('updates') if isinstance(data, dict) else data
    if not isinstance(items, list):
        return 0

    synced = 0
    for raw in items:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get('slug') or '').strip()
        title = str(raw.get('title') or '').strip()
        content = str(raw.get('content') or '').strip()
        if not slug or not title or not content:
            continue

        priority = str(raw.get('priority') or 'normal').strip().lower()
        if priority not in ('normal', 'urgent'):
            priority = 'normal'

        created_at = _parse_created_at(raw.get('created_at'))
        existing = ServiceUpdate.query.filter_by(slug=slug).first()
        if existing:
            changed = (
                existing.title != title
                or existing.content != content
                or existing.priority != priority
            )
            if not changed:
                continue
            existing.title = title
            existing.content = content
            existing.priority = priority
            existing.updated_at = datetime.utcnow()
            ServiceUpdateRead.query.filter_by(update_id=existing.id).delete(synchronize_session=False)
            synced += 1
            continue

        row = ServiceUpdate(
            slug=slug,
            title=title,
            content=content,
            priority=priority,
            source='auto',
            created_at=created_at or datetime.utcnow(),
        )
        db.session.add(row)
        synced += 1

    if synced:
        db.session.commit()
    return synced


def unread_service_updates_count(user_id):
    read_ids = db.session.query(ServiceUpdateRead.update_id).filter_by(user_id=user_id)
    return ServiceUpdate.query.filter(~ServiceUpdate.id.in_(read_ids)).count()


def mark_service_updates_read(user, update_ids=None):
    """Отметить обновления прочитанными."""
    if update_ids is None:
        read_ids = {
            r.update_id
            for r in ServiceUpdateRead.query.filter_by(user_id=user.id).all()
        }
        update_ids = [
            row[0]
            for row in ServiceUpdate.query.with_entities(ServiceUpdate.id).all()
            if row[0] not in read_ids
        ]
    else:
        update_ids = [int(i) for i in update_ids if i]

    if not update_ids:
        return 0

    existing = {
        r.update_id
        for r in ServiceUpdateRead.query.filter(
            ServiceUpdateRead.user_id == user.id,
            ServiceUpdateRead.update_id.in_(update_ids),
        ).all()
    }
    added = 0
    for update_id in update_ids:
        if update_id in existing:
            continue
        db.session.add(ServiceUpdateRead(user_id=user.id, update_id=update_id))
        added += 1
    if added:
        db.session.commit()
    return added


def new_manual_slug():
    return f'manual-{uuid.uuid4().hex[:12]}'

