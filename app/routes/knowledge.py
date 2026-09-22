"""
База знаний для пользователей
"""

import os
import re
from flask import Blueprint, render_template, abort, current_app, send_from_directory, Response, url_for, redirect, request
from sqlalchemy import and_, func
from app import db
from app.models.knowledge_article import KnowledgeArticle
from app.models.knowledge_section import KnowledgeSection
from app.models.knowledge_topic import KnowledgeTopic

knowledge_bp = Blueprint('knowledge', __name__)

_STATIC_TEMPLATES = {
    'platforms': 'platforms.html',
    'distribution': 'distribution.html',
}


def _published_sections():
    return (
        KnowledgeSection.query.filter_by(is_published=True)
        .order_by(KnowledgeSection.sort_order.asc(), KnowledgeSection.title.asc())
        .all()
    )


def _published_articles_in_section(section: KnowledgeSection):
    q = (
        KnowledgeArticle.query.filter_by(section_id=section.id, is_published=True)
        .order_by(KnowledgeArticle.sort_order.asc(), KnowledgeArticle.title.asc())
        .all()
    )
    return [a for a in q if a.has_body]


def _published_topics(section_id: int):
    return (
        KnowledgeTopic.query.filter_by(section_id=section_id, is_published=True)
        .order_by(KnowledgeTopic.sort_order.asc(), KnowledgeTopic.id.asc())
        .all()
    )


def _sql_article_has_body():
    return and_(
        KnowledgeArticle.body_html.isnot(None),
        func.length(func.trim(KnowledgeArticle.body_html)) > 0,
    )


def _siblings_same_topic(article: KnowledgeArticle, section: KnowledgeSection):
    return [
        a
        for a in _published_articles_in_section(section)
        if a.id != article.id and (a.topic_id == article.topic_id)
    ]


def _section_tabbed_view(section: KnowledgeSection, topics: list):
    page = request.args.get('page', 1, type=int) or 1
    qsearch = (request.args.get('q') or '').strip()

    has_other = (
        KnowledgeArticle.query.filter_by(
            section_id=section.id,
            is_published=True,
            topic_id=None,
        )
        .filter(_sql_article_has_body())
        .first()
        is not None
    )

    tab_slugs = {t.slug for t in topics}
    topic_param = (request.args.get('topic') or '').strip()

    if topic_param == '_other' and not has_other:
        topic_param = ''
    if topic_param and topic_param != '_other' and topic_param not in tab_slugs:
        topic_param = ''

    if not topic_param:
        current_slug = topics[0].slug
    else:
        current_slug = topic_param

    base = KnowledgeArticle.query.filter_by(section_id=section.id, is_published=True).filter(
        _sql_article_has_body()
    )
    if qsearch:
        qsafe = ''.join(c for c in qsearch[:200] if c not in '%_\\')
        if qsafe:
            base = base.filter(KnowledgeArticle.title.ilike(f'%{qsafe}%'))

    if current_slug == '_other':
        base = base.filter(KnowledgeArticle.topic_id.is_(None))
    elif current_slug:
        tid = next((t.id for t in topics if t.slug == current_slug), None)
        if tid is not None:
            base = base.filter_by(topic_id=tid)

    per_page = 10
    pagination = base.order_by(
        KnowledgeArticle.sort_order.asc(),
        KnowledgeArticle.title.asc(),
    ).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'knowledge/section_hub_tabs.html',
        section=section,
        topics=topics,
        topics_other=has_other,
        current_topic_slug=current_slug,
        articles=pagination.items,
        pagination=pagination,
        search_q=qsearch,
    )


def _build_index_sections():
    out = []
    for sec in _published_sections():
        out.append({
            'href': url_for('knowledge.section', slug=sec.slug),
            'icon': sec.icon or 'menu_book',
            'title': sec.title,
            'desc': (sec.summary or '').strip() or 'Материалы раздела',
            'is_main': bool(sec.highlight_index),
        })
    return out


def _global_search(query: str):
    """Поиск по всем разделам базы знаний."""
    if not query or not query.strip():
        return None
    qsafe = ''.join(c for c in query.strip()[:200] if c not in '%_\\')
    if not qsafe:
        return None

    articles = (
        KnowledgeArticle.query
        .join(KnowledgeSection)
        .filter(
            KnowledgeArticle.is_published.is_(True),
            KnowledgeSection.is_published.is_(True),
            _sql_article_has_body(),
            KnowledgeArticle.title.ilike(f'%{qsafe}%'),
        )
        .order_by(KnowledgeArticle.title.asc())
        .limit(20)
        .all()
    )

    results = []
    for a in articles:
        results.append({
            'href': url_for('knowledge.article_page', section_slug=a.section.slug, article_slug=a.slug),
            'icon': a.section.icon or 'description',
            'section': a.section.title,
            'title': a.title,
            'summary': a.summary or '',
        })
    return results


def _render_static(key: str):
    tpl = _STATIC_TEMPLATES.get(key)
    if not tpl:
        abort(404)
    return render_template(f'knowledge/{tpl}')


def _section_view(section: KnowledgeSection):
    arts = _published_articles_in_section(section)
    topics = _published_topics(section.id)
    # Если в разделе есть подразделы (вкладки) — всегда хаб с табами, а не прямой переход к статье
    # (иначе «главная статья» или одна статья скрывали бы вкладки).
    if topics:
        return _section_tabbed_view(section, topics)

    landing = next((a for a in arts if a.is_landing), None)
    if not landing and len(arts) == 1:
        landing = arts[0]
    if landing:
        others = [a for a in arts if a.id != landing.id]
        others = [a for a in others if a.topic_id == landing.topic_id]
        return render_template(
            'knowledge/dynamic.html',
            article=landing,
            section=section,
            sibling_articles=others,
        )
    if arts:
        return render_template('knowledge/section_hub.html', section=section, articles=arts)
    if section.static_fallback and section.static_fallback in _STATIC_TEMPLATES:
        return _render_static(section.static_fallback)
    return render_template('knowledge/section_hub.html', section=section, articles=[])


@knowledge_bp.route('/knowledge')
def index():
    """Главная страница базы знаний (доступна без входа)"""
    search_q = (request.args.get('q') or '').strip()
    search_results = _global_search(search_q) if search_q else None
    return render_template(
        'knowledge/index.html',
        sections=_build_index_sections(),
        search_q=search_q,
        search_results=search_results,
    )


@knowledge_bp.route('/knowledge/img/<filename>')
def knowledge_img(filename):
    """Скриншоты инструкции"""
    if not re.match(r'^cabinet-\d{2}(\.\d)?\.(png|jpg|jpeg|webp)$', filename):
        abort(404)
    folder = os.path.join(current_app.static_folder, 'img', 'knowledge')
    path = os.path.join(folder, filename)
    if os.path.isfile(path):
        return send_from_directory(folder, filename)
    return Response(status=204)


@knowledge_bp.route('/knowledge/<section_slug>/<article_slug>')
def article_page(section_slug, article_slug):
    """Статья внутри раздела"""
    section = KnowledgeSection.query.filter_by(slug=section_slug, is_published=True).first_or_404()
    article = KnowledgeArticle.query.filter_by(
        section_id=section.id,
        slug=article_slug,
        is_published=True,
    ).first_or_404()
    if not article.has_body:
        abort(404)
    siblings = _siblings_same_topic(article, section)
    return render_template(
        'knowledge/dynamic.html',
        article=article,
        section=section,
        sibling_articles=siblings,
    )


@knowledge_bp.route('/knowledge/<slug>')
def section(slug):
    """
    Раздел по одному сегменту URL: /knowledge/<раздел>
    Либо редирект со старого адреса /knowledge/<slug-статьи> → /knowledge/<раздел>/<статья>
    """
    if slug == 'img':
        abort(404)

    section = KnowledgeSection.query.filter_by(slug=slug, is_published=True).first()
    if section:
        return _section_view(section)

    article = (
        KnowledgeArticle.query.join(KnowledgeSection)
        .filter(
            KnowledgeArticle.slug == slug,
            KnowledgeArticle.is_published.is_(True),
            KnowledgeSection.is_published.is_(True),
        )
        .first()
    )
    if article:
        return redirect(
            url_for(
                'knowledge.article_page',
                section_slug=article.section.slug,
                article_slug=article.slug,
            ),
            code=301,
        )

    if slug in _STATIC_TEMPLATES:
        return _render_static(slug)

    abort(404)
