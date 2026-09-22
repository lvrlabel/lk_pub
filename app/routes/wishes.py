"""
Раздел пожеланий
"""

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app import db
from app.models.auto_form import AutoFormRequest

wishes_bp = Blueprint('wishes', __name__)


@wishes_bp.route('/wishes', methods=['GET', 'POST'])
@login_required
def index():
    """Форма пожеланий по личному кабинету."""
    error = None
    sent = False
    wish_text = ''

    if request.method == 'POST':
        wish_text = (request.form.get('wish_text') or '').strip()
        if len(wish_text) < 10:
            error = 'Опишите пожелание подробнее (минимум 10 символов).'
        elif len(wish_text) > 4000:
            error = 'Слишком длинное сообщение. Максимум 4000 символов.'
        else:
            req = AutoFormRequest(
                user_id=current_user.id,
                request_type='cabinet_wish',
                topic_urls=wish_text,
                status='pending'
            )
            db.session.add(req)
            db.session.commit()
            sent = True
            wish_text = ''

    return render_template('wishes/index.html', error=error, sent=sent, wish_text=wish_text)
