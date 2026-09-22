"""
Разделы базы знаний (группы статей, карточка на главной БЗ).
"""

from datetime import datetime
from app import db


class KnowledgeSection(db.Model):
    __tablename__ = 'knowledge_sections'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.String(500), nullable=True)
    icon = db.Column(db.String(64), nullable=False, default='menu_book')
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    # Встроенный HTML-шаблон, если в разделе нет статей с текстом: cabinet | platforms | distribution
    static_fallback = db.Column(db.String(32), nullable=True)
    # Крупная карточка на главной базы знаний
    highlight_index = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    articles = db.relationship(
        'KnowledgeArticle',
        backref='section',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    topics = db.relationship(
        'KnowledgeTopic',
        backref='section',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='KnowledgeTopic.sort_order',
    )

    @property
    def topics_ordered(self):
        from app.models.knowledge_topic import KnowledgeTopic

        return self.topics.order_by(KnowledgeTopic.sort_order.asc(), KnowledgeTopic.id.asc()).all()

    @property
    def articles_ordered(self):
        from app.models.knowledge_article import KnowledgeArticle

        return (
            self.articles.order_by(KnowledgeArticle.sort_order.asc(), KnowledgeArticle.id.asc()).all()
        )

    def __repr__(self):
        return f'<KnowledgeSection {self.slug}>'
