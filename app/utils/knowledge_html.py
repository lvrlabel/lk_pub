"""Санитизация HTML для базы знаний (редактор в админке)."""

import bleach

_ALLOWED_TAGS = frozenset({
    'p', 'br', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li',
    'strong', 'em', 'b', 'i', 'u', 's', 'sub', 'sup',
    'blockquote', 'pre', 'code',
    'a', 'img',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
    'span', 'div',
})

_ALLOWED_ATTRS = {
    'a': ['href', 'title', 'rel', 'target'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
    '*': ['class'],
}


def sanitize_knowledge_html(fragment: str) -> str:
    if not fragment:
        return ''
    return bleach.clean(
        fragment,
        tags=list(_ALLOWED_TAGS),
        attributes=_ALLOWED_ATTRS,
        strip=True,
    )


def is_effectively_empty_html(fragment: str) -> bool:
    """Пустой Quill (<p><br></p>) считаем отсутствием текста — снова покажется встроенная страница."""
    if not fragment or not str(fragment).strip():
        return True
    text = bleach.clean(fragment or '', tags=[], strip=True)
    return not (text or '').strip()
