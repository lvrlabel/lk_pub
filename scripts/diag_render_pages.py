# -*- coding: utf-8 -*-
"""Временный скрипт: рендер страниц сообщества в статические HTML-файлы."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.models.user import User  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'diag_render')
os.makedirs(OUT_DIR, exist_ok=True)

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
client = app.test_client()

with app.app_context():
    admin = User.query.filter_by(login='admin').first()

with client.session_transaction() as sess:
    sess['_user_id'] = str(admin.id)
    sess['_fresh'] = True


def fix_links(html):
    html = html.replace('href="/static/', 'href="http://127.0.0.1:5000/static/')
    html = html.replace("src='/static/", "src='http://127.0.0.1:5000/static/")
    html = html.replace('src="/static/', 'src="http://127.0.0.1:5000/static/')
    html = re.sub(r"url\((['\"]?)/static/", r"url(\1http://127.0.0.1:5000/static/", html)
    return html


pages = {
    'chat': '/community',
    'stories': '/community/stories',
    'profile': '/community/user/%d' % admin.id,
}
for name, url in pages.items():
    resp = client.get(url)
    html = fix_links(resp.get_data(as_text=True))
    with open(os.path.join(OUT_DIR, name + '.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    print(name, resp.status_code)

print('DONE')