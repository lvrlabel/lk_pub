"""
Статьи базы знаний (внутри раздела).
"""

from datetime import datetime
from app import db


class KnowledgeArticle(db.Model):
    __tablename__ = 'knowledge_articles'
    __table_args__ = (
        db.UniqueConstraint('section_id', 'slug', name='uq_knowledge_article_section_slug'),
    )

    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey('knowledge_sections.id', ondelete='CASCADE'), nullable=False, index=True)
    topic_id = db.Column(
        db.Integer,
        db.ForeignKey('knowledge_topics.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    slug = db.Column(db.String(120), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    summary = db.Column(db.String(500), nullable=True)
    body_html = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    # Открывается по адресу /knowledge/<раздел> (если несколько статей — только одна может быть «главной»)
    is_landing = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def has_body(self):
        return bool(self.body_html and str(self.body_html).strip())

    def __repr__(self):
        return f'<KnowledgeArticle {self.slug}>'
