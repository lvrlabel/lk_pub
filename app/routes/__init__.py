"""
Роуты (Blueprint'ы)
"""

from app.routes.auth import auth_bp
from app.routes.dashboard import dashboard_bp
from app.routes.releases import releases_bp
from app.routes.moderation import moderation_bp
from app.routes.money import money_bp
from app.routes.smart_link import smart_link_bp
from app.routes.stories import stories_bp
from app.routes.tickets import tickets_bp
from app.routes.contracts import contracts_bp
from app.routes.users import users_bp
from app.routes.labels import labels_bp
from app.routes.profile import profile_bp
from app.routes.admin import admin_bp
from app.routes.stats import stats_bp

__all__ = [
    'auth_bp',
    'dashboard_bp',
    'releases_bp',
    'moderation_bp',
    'money_bp',
    'smart_link_bp',
    'stories_bp',
    'tickets_bp',
    'contracts_bp',
    'users_bp',
    'labels_bp',
    'profile_bp',
    'admin_bp',
    'stats_bp',
]
