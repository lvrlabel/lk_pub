"""
Миграция базы знаний: старая схема (category + глобальный slug) → разделы + статьи.
"""

from flask import current_app
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from app import db


def _column_names(engine, table: str):
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return None
    return {c['name'] for c in insp.get_columns(table)}


def _seed_default_sections():
    from app.models.knowledge_section import KnowledgeSection

    defaults = [
        dict(
            slug='platforms',
            title='Требования площадок',
            summary='Требования площадок по официальным источникам с учётом изменений законодательства с 1 марта 2026',
            icon='apps',
            sort_order=20,
            static_fallback='platforms',
            highlight_index=False,
        ),
        dict(
            slug='distribution',
            title='Дистрибуция',
            summary='Как работает дистрибуция, сроки, роялти и распространение музыки',
            icon='published_with_changes',
            sort_order=30,
            static_fallback='distribution',
            highlight_index=False,
        ),
        dict(
            slug='general',
            title='Общие вопросы',
            summary='Ответы на частые вопросы: договоры, сроки, статусы релизов и работа с кабинетом',
            icon='quiz',
            sort_order=40,
            static_fallback=None,
            highlight_index=False,
        ),
    ]
    for row in defaults:
        if not KnowledgeSection.query.filter_by(slug=row['slug']).first():
            db.session.add(KnowledgeSection(**row))
    db.session.commit()


def run_knowledge_migrations(app):
    """Вызывать после db.create_all()."""
    engine = db.engine
    dialect = engine.dialect.name

    cols = _column_names(engine, 'knowledge_articles')
    if cols is None:
        _seed_default_sections()
        return

    if 'section_id' in cols:
        _seed_default_sections()
        return

    if 'category' not in cols:
        current_app.logger.warning('knowledge_articles без section_id и без category — пропуск миграции')
        return

    current_app.logger.info('Миграция knowledge_articles → разделы + section_id')
    _seed_default_sections()

    from app.models.knowledge_section import KnowledgeSection

    with engine.begin() as conn:
        if dialect == 'sqlite':
            conn.execute(text('PRAGMA foreign_keys=OFF'))
            conn.execute(
                text("""
                CREATE TABLE knowledge_articles_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    section_id INTEGER NOT NULL,
                    slug VARCHAR(120) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    summary VARCHAR(500),
                    body_html TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    is_published BOOLEAN NOT NULL DEFAULT 1,
                    is_landing BOOLEAN NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME,
                    FOREIGN KEY(section_id) REFERENCES knowledge_sections (id) ON DELETE CASCADE,
                    CONSTRAINT uq_knowledge_article_section_slug UNIQUE (section_id, slug)
                )
                """)
            )
            conn.execute(
                text("""
                INSERT INTO knowledge_articles_new (
                    id, section_id, slug, title, summary, body_html, sort_order, is_published,
                    is_landing, created_at, updated_at
                )
                SELECT
                    ka.id,
                    ks.id,
                    ka.slug,
                    ka.title,
                    ka.summary,
                    ka.body_html,
                    ka.sort_order,
                    ka.is_published,
                    CASE
                        WHEN ka.category IN ('cabinet', 'platforms', 'distribution')
                             AND ka.slug = ka.category THEN 1
                        ELSE 0
                    END,
                    ka.created_at,
                    COALESCE(ka.updated_at, ka.created_at)
                FROM knowledge_articles ka
                JOIN knowledge_sections ks ON ks.slug = ka.category
                """)
            )
            conn.execute(text('DROP TABLE knowledge_articles'))
            conn.execute(text('ALTER TABLE knowledge_articles_new RENAME TO knowledge_articles'))
            conn.execute(text('CREATE INDEX ix_knowledge_articles_section_id ON knowledge_articles (section_id)'))
            conn.execute(text('CREATE INDEX ix_knowledge_articles_slug ON knowledge_articles (slug)'))
            conn.execute(text('PRAGMA foreign_keys=ON'))
        else:
            try:
                conn.execute(text('ALTER TABLE knowledge_articles ADD COLUMN section_id INT NULL'))
            except OperationalError as e:
                if 'duplicate column' not in str(e).lower():
                    raise
            conn.execute(
                text("""
                UPDATE knowledge_articles ka
                INNER JOIN knowledge_sections ks ON ks.slug = ka.category
                SET ka.section_id = ks.id
                WHERE ka.section_id IS NULL
                """)
            )
            try:
                conn.execute(text('ALTER TABLE knowledge_articles ADD COLUMN is_landing BOOL NOT NULL DEFAULT 0'))
            except OperationalError as e:
                if 'duplicate column' not in str(e).lower():
                    raise
            conn.execute(
                text("""
                UPDATE knowledge_articles ka
                INNER JOIN knowledge_sections ks ON ks.slug = ka.category
                SET ka.is_landing = 1
                WHERE ka.category IN ('cabinet', 'platforms', 'distribution') AND ka.slug = ka.category
                """)
            )
            for idx in inspect(engine).get_indexes('knowledge_articles'):
                name = idx.get('name') or ''
                cols = list(idx.get('column_names') or [])
                if len(cols) == 1 and cols[0] == 'slug' and idx.get('unique'):
                    try:
                        conn.execute(text(f'DROP INDEX `{name}` ON knowledge_articles'))
                    except OperationalError:
                        try:
                            conn.execute(text(f'ALTER TABLE knowledge_articles DROP INDEX `{name}`'))
                        except OperationalError:
                            pass
            try:
                conn.execute(text('ALTER TABLE knowledge_articles DROP COLUMN category'))
            except OperationalError:
                pass
            try:
                conn.execute(
                    text('ALTER TABLE knowledge_articles MODIFY section_id INT NOT NULL')
                )
            except OperationalError:
                pass
            try:
                conn.execute(
                    text(
                        'ALTER TABLE knowledge_articles ADD CONSTRAINT uq_knowledge_article_section_slug '
                        'UNIQUE (section_id, slug)'
                    )
                )
            except OperationalError as e:
                if 'duplicate' not in str(e).lower():
                    current_app.logger.warning('uq_knowledge_article_section_slug: %s', e)

    db.session.remove()
    _seed_default_sections()
