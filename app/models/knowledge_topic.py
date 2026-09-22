"""
Подразделы базы знаний (вкладки внутри раздела, напр. «Отчёты», «YouTube»).
"""

from datetime import datetime
from app import db


class KnowledgeTopic(db.Model):
    __tablename__ = 'knowledge_topics'
    __table_args__ = (
        db.UniqueConstraint('section_id', 'slug', name='uq_knowledge_topic_section_slug'),
    )

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(
        db.Integer,
        db.ForeignKey('knowledge_sections.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    slug = db.Column(db.String(120), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    articles = db.relationship(
        'KnowledgeArticle',
        backref='topic',
        lazy='dynamic',
        foreign_keys='KnowledgeArticle.topic_id',
    )

    def __repr__(self):
        return f'<KnowledgeTopic {self.slug}>'
