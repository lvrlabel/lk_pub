# -*- coding: utf-8 -*-
"""Временный скрипт: создать/удалить визуального тест-пользователя."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402
from app.models.user import User  # noqa: E402

app = create_app()

with app.app_context():
    if 'remove' in sys.argv:
        u = User.query.filter_by(login='visual_test').first()
        if u:
            db.session.delete(u)
            db.session.commit()
            print('removed visual_test')
        else:
            print('no visual_test')
    else:
        u = User.query.filter_by(login='visual_test').first()
        if not u:
            u = User(
                login='visual_test',
                email='visual_test@example.invalid',
                name='Visual Test',
                role='artist',
                copyright='© 2026 Visual Test',
            )
            u.set_password('Visual123!')
            db.session.add(u)
            db.session.commit()
            print('created visual_test id=%s' % u.id)
        else:
            print('exists visual_test id=%s' % u.id)