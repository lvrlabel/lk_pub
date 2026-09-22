"""
Личное рабочее пространство артиста: заметки, задачи, идеи, планы, календарь, layout.
Контекст может быть привязан к sessionId (SML).
"""

from datetime import datetime, timedelta, timezone
import json

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

from app import db


def _to_local_msk(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        if ZoneInfo is not None:
            return dt.astimezone(ZoneInfo('Europe/Moscow'))
    except Exception:
        pass
    return dt.astimezone(timezone(timedelta(hours=3)))


DEFAULT_WORKSPACE_BLOCKS = [
    {'id': 'next_release', 'title': 'Мой следующий релиз', 'visible': True, 'order': 0, 'tint': 'default'},
    {'id': 'tasks', 'title': 'Мои задачи', 'visible': True, 'order': 1, 'tint': 'default'},
    {'id': 'ideas', 'title': 'Мои идеи', 'visible': True, 'order': 2, 'tint': 'default'},
    {'id': 'plans', 'title': 'Мои планы', 'visible': True, 'order': 3, 'tint': 'default'},
    {'id': 'notes', 'title': 'Заметки', 'visible': True, 'order': 4, 'tint': 'default'},
    {'id': 'calendar', 'title': 'Календарь', 'visible': True, 'order': 5, 'tint': 'default'},
    {'id': 'stats', 'title': 'Моя статистика', 'visible': True, 'order': 6, 'tint': 'default'},
]

DEFAULT_WORKSPACE_THEME = {
    'accent': '#0d9488',
    'gradient': 'none',
    'cover': None,
}

BLOCK_TINTS = {
    'default': {'label': 'По умолчанию', 'color': None},
    'teal': {'label': 'Бирюза', 'color': '#0d9488'},
    'blue': {'label': 'Синий', 'color': '#2563eb'},
    'violet': {'label': 'Фиолет', 'color': '#7c3aed'},
    'rose': {'label': 'Розовый', 'color': '#e11d48'},
    'amber': {'label': 'Янтарный', 'color': '#d97706'},
    'slate': {'label': 'Серый', 'color': '#64748b'},
}

THEME_GRADIENTS = {
    'none': {'label': 'Без фона', 'css': 'none'},
    'mist': {'label': 'Туман', 'css': 'linear-gradient(145deg, #f8fafc 0%, #e2e8f0 100%)'},
    'teal': {'label': 'Мята', 'css': 'linear-gradient(145deg, #f0fdfa 0%, #ccfbf1 100%)'},
    'sunset': {'label': 'Закат', 'css': 'linear-gradient(145deg, #fff7ed 0%, #fed7aa 100%)'},
    'lilac': {'label': 'Сирень', 'css': 'linear-gradient(145deg, #f5f3ff 0%, #ddd6fe 100%)'},
    'ocean': {'label': 'Океан', 'css': 'linear-gradient(145deg, #eff6ff 0%, #bfdbfe 100%)'},
}


class WorkspaceLayout(db.Model):
    """Настройки блоков кабинета пользователя."""

    __tablename__ = 'workspace_layouts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True, index=True)
    blocks_json = db.Column(db.Text, nullable=False, default='[]')
    theme_json = db.Column(db.Text, nullable=True)
    last_session_id = db.Column(db.String(64), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('workspace_layout', uselist=False))

    def get_blocks(self):
        try:
            data = json.loads(self.blocks_json or '[]')
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
        return [dict(b) for b in DEFAULT_WORKSPACE_BLOCKS]

    def set_blocks(self, blocks):
        self.blocks_json = json.dumps(blocks, ensure_ascii=False)
        self.updated_at = datetime.utcnow()

    def get_theme(self):
        theme = dict(DEFAULT_WORKSPACE_THEME)
        try:
            data = json.loads(self.theme_json or '{}')
            if isinstance(data, dict):
                theme.update({k: data[k] for k in ('accent', 'gradient', 'cover') if k in data})
        except Exception:
            pass
        return theme

    def set_theme(self, theme: dict):
        self.theme_json = json.dumps(theme, ensure_ascii=False)
        self.updated_at = datetime.utcnow()

    @property
    def cover_url(self):
        theme = self.get_theme()
        cover = theme.get('cover')
        if not cover:
            return None
        from flask import url_for
        try:
            return url_for('workspace.serve_cover', filename=cover)
        except Exception:
            return None

    @staticmethod
    def for_user(user_id):
        row = WorkspaceLayout.query.filter_by(user_id=user_id).first()
        if row:
            return row
        row = WorkspaceLayout(
            user_id=user_id,
            blocks_json=json.dumps(DEFAULT_WORKSPACE_BLOCKS, ensure_ascii=False),
            theme_json=json.dumps(DEFAULT_WORKSPACE_THEME, ensure_ascii=False),
        )
        db.session.add(row)
        db.session.commit()
        return row


class WorkspaceNote(db.Model):
    __tablename__ = 'workspace_notes'
    __table_args__ = (db.Index('ix_workspace_notes_user_updated', 'user_id', 'updated_at'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False, default='')
    body = db.Column(db.Text, nullable=False, default='')
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    session_id = db.Column(db.String(64), nullable=True)

    @property
    def updated_display(self):
        dt = _to_local_msk(self.updated_at)
        return dt.strftime('%d.%m.%Y %H:%M') if dt else ''


class WorkspaceTask(db.Model):
    """Задачи / to-do с опциональным дедлайном."""

    __tablename__ = 'workspace_tasks'
    __table_args__ = (db.Index('ix_workspace_tasks_user_done', 'user_id', 'is_done'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    is_done = db.Column(db.Boolean, default=False, nullable=False)
    due_at = db.Column(db.DateTime, nullable=True, index=True)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    list_name = db.Column(db.String(100), nullable=True)  # имя to-do листа
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    session_id = db.Column(db.String(64), nullable=True)

    @property
    def due_display(self):
        if not self.due_at:
            return ''
        dt = _to_local_msk(self.due_at)
        return dt.strftime('%d.%m.%Y') if dt else ''

    @property
    def is_overdue(self):
        if self.is_done or not self.due_at:
            return False
        return self.due_at.date() < datetime.utcnow().date()


class WorkspaceIdea(db.Model):
    __tablename__ = 'workspace_ideas'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='inbox')  # inbox|active|done
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    session_id = db.Column(db.String(64), nullable=True)

    @property
    def status_label(self):
        return {'inbox': 'Идея', 'active': 'В работе', 'done': 'Готово'}.get(self.status, self.status)


class WorkspaceReleasePlan(db.Model):
    __tablename__ = 'workspace_release_plans'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    target_date = db.Column(db.Date, nullable=True)
    release_id = db.Column(db.Integer, db.ForeignKey('releases.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='planned')  # planned|in_progress|done
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    session_id = db.Column(db.String(64), nullable=True)

    release = db.relationship('Release', foreign_keys=[release_id])

    @property
    def target_display(self):
        if not self.target_date:
            return ''
        return self.target_date.strftime('%d.%m.%Y')

    @property
    def status_label(self):
        return {
            'planned': 'План',
            'in_progress': 'В работе',
            'done': 'Готово',
        }.get(self.status, self.status)


class WorkspaceCalendarEvent(db.Model):
    __tablename__ = 'workspace_calendar_events'
    __table_args__ = (db.Index('ix_workspace_cal_user_starts', 'user_id', 'starts_at'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=True)
    all_day = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    session_id = db.Column(db.String(64), nullable=True)

    @property
    def starts_display(self):
        dt = _to_local_msk(self.starts_at)
        if not dt:
            return ''
        if self.all_day:
            return dt.strftime('%d.%m.%Y')
        return dt.strftime('%d.%m.%Y %H:%M')
