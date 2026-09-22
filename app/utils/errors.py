"""
Обработчики ошибок
"""

from flask import render_template, request, jsonify, flash, redirect, url_for
import logging

try:
    from werkzeug.routing.exceptions import BuildError as WerkzeugBuildError
except ImportError:
    WerkzeugBuildError = type('BuildError', (Exception,), {})


def register_error_handlers(app):
    """Регистрация обработчиков ошибок"""
    
    @app.errorhandler(400)
    def bad_request(error):
        """Неверный запрос"""
        if request.is_json:
            return jsonify({'error': 'Неверный запрос'}), 400
        return render_template('errors/400.html'), 400
    
    @app.errorhandler(403)
    def forbidden(error):
        """Доступ запрещён"""
        if request.is_json:
            return jsonify({'error': 'Доступ запрещён'}), 403
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(404)
    def not_found(error):
        """Страница не найдена"""
        if request.is_json:
            return jsonify({'error': 'Ресурс не найден'}), 404
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        """Файл слишком большой"""
        if request.is_json:
            return jsonify({'error': 'Файл слишком большой'}), 413
        return render_template('errors/413.html'), 413
    
    @app.errorhandler(WerkzeugBuildError)
    def build_error(error):
        """url_for на несуществующий endpoint — часто после деплоя без новых маршрутов stats."""
        if hasattr(app, 'logger') and app.logger:
            app.logger.warning('BuildError (url_for): %s', error)
        if request.is_json:
            return jsonify({'error': 'Маршрут недоступен', 'detail': str(error)}), 503
        flash('Раздел временно недоступен. Обновите приложение на сервере или зайдите позже.', 'warning')
        try:
            return redirect(url_for('dashboard.index'))
        except Exception:
            return render_template('errors/500.html'), 503

    @app.errorhandler(500)
    def internal_error(error):
        """Внутренняя ошибка сервера"""
        if hasattr(app, 'logger') and app.logger:
            app.logger.exception('500 Internal Error: %s', error)
        if request.is_json:
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
        return render_template('errors/500.html'), 500
    
    # Настройка логирования
    if not app.debug:
        import os as _os
        log_dir = _os.path.join(app.root_path, '..', 'logs')
        log_dir = _os.path.abspath(log_dir)
        _os.makedirs(log_dir, exist_ok=True)
        log_file = _os.path.join(log_dir, 'app.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        app.logger.addHandler(file_handler)
