"""
Сообщество артистов: сторис с реакциями/комментариями и общий чат.
"""

from datetime import datetime, timedelta

from app import db


class Story(db.Model):
    """Сторис артиста (медиа + подпись, живёт 24 часа)."""

    __tablename__ = 'stories'

    STORY_TTL_HOURS = 24

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    media = db.Column(db.String(256), nullable=False)          # файл в uploads/stories/
    media_type = db.Column(db.String(16), nullable=False, default='image')  # image | video
    caption = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    is_hidden = db.Column(db.Boolean, default=False, nullable=False)  # скрыто модератором

    author = db.relationship('User', backref='stories')

    reactions = db.relationship(
        'StoryReaction',
        backref='story',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    comments = db.relationship(
        'StoryComment',
        backref='story',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    @staticmethod
    def default_expires_at():
        return datetime.utcnow() + timedelta(hours=Story.STORY_TTL_HOURS)

    @property
    def media_url(self):
        return f'/uploads/stories/{self.media}'

    @property
    def is_expired(self):
        return self.expires_at <= datetime.utcnow()

    @property
    def reactions_count(self):
        return self.reactions.count()

    @property
    def comments_count(self):
        return self.comments.count()

    @property
    def time_formatted(self):
        delta = datetime.utcnow() - self.created_at
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            return 'только что'
        if mins < 60:
            return f'{mins} мин назад'
        hours = mins // 60
        if hours < 24:
            return f'{hours} ч назад'
        days = hours // 24
        return f'{days} дн назад'

    def reacted_by_user(self, user_id):
        return self.reactions.filter_by(user_id=user_id).first() is not None

    @classmethod
    def active_query(cls):
        now = datetime.utcnow()
        return (
            cls.query
            .filter(cls.is_hidden.is_(False), cls.expires_at > now)
            .order_by(cls.created_at.desc())
        )


class StoryReaction(db.Model):
    """Реакция («сердечко») на сторис."""

    __tablename__ = 'story_reactions'
    __table_args__ = (
        db.UniqueConstraint('story_id', 'user_id', name='uq_story_reaction'),
    )

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('stories.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reaction = db.Column(db.String(16), nullable=False, default='heart')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User')


class StoryComment(db.Model):
    """Комментарий к сторис."""

    __tablename__ = 'story_comments'

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('stories.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User')

    @property
    def time_formatted(self):
        return self.created_at.strftime('%d.%m.%Y %H:%M')


class CommunityMessage(db.Model):
    """Сообщение в общем чате сообщества."""

    __tablename__ = 'community_messages'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    text = db.Column(db.String(1000), nullable=False, default='')
    media = db.Column(db.String(256), nullable=True)
    media_type = db.Column(db.String(16), nullable=True)  # audio | video
    reply_to_id = db.Column(db.Integer, db.ForeignKey('community_messages.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User')
    reply_to = db.relationship('CommunityMessage', remote_side=[id], backref='replies')

    @property
    def time_formatted(self):
        delta = datetime.utcnow() - self.created_at
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            return 'только что'
        if mins < 60:
            return f'{mins} мин назад'
        hours = mins // 60
        if hours < 24:
            return f'{hours} ч назад'
        return self.created_at.strftime('%d.%m.%Y %H:%M')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'author': (self.user.display_name if self.user else '—'),
            'avatar': (self.user.avatar_url if self.user else '/static/img/default-avatar.png'),
            'is_admin': bool(self.user and self.user.is_admin),
            'text': self.text,
            'media_url': f'/uploads/community/{self.media}' if self.media else None,
            'media_type': self.media_type,
            'reply_to': {
                'id': self.reply_to.id,
                'author': self.reply_to.user.display_name if self.reply_to.user else '—',
                'text': self.reply_to.text or ('Голосовое сообщение' if self.reply_to.media_type == 'audio' else 'Видео-сообщение'),
            } if self.reply_to else None,
            'time': self.time_formatted,
        }