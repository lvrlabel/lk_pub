"""
Аналитика
"""

from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from app import db
from app.models.release import Release
from app.models.analytics import ReleaseAnalytics, DeviceAnalytics, PlatformAnalytics, PlatformDailyListen
from app.utils.decorators import admin_required
from sqlalchemy.exc import OperationalError, ProgrammingError

stats_bp = Blueprint('stats', __name__)


def _aggregate_platform_summary(analytics_data):
    """Суммарные стримы по площадкам за все периоды выбранного релиза."""
    totals = {}
    for item in analytics_data:
        for pa in item.platform_analytics:
            name = pa.platform_name
            if name not in totals:
                totals[name] = {'name': name, 'streams': 0, 'downloads': 0, 'revenue': 0.0}
            totals[name]['streams'] += pa.streams or 0
            totals[name]['downloads'] += pa.downloads or 0
            totals[name]['revenue'] += pa.revenue or 0.0
    return sorted(totals.values(), key=lambda x: x['streams'], reverse=True)


def _aggregate_device_summary(analytics_data):
    """Суммарные стримы по типам устройств."""
    totals = {}
    for item in analytics_data:
        for da in item.device_analytics:
            name = da.device_type
            if name not in totals:
                totals[name] = {'name': name, 'streams': 0, 'downloads': 0}
            totals[name]['streams'] += da.streams or 0
            totals[name]['downloads'] += da.downloads or 0
    return sorted(totals.values(), key=lambda x: x['streams'], reverse=True)


ANALYTICS_PLATFORM_TABS = [
    'Все', 'iTunes', 'Apple Music', 'Spotify', 'VK Музыка', 'VK Клипы',
    'Яндекс Музыка', 'КИОН Музыка', 'Звук', 'Одноклассники', 'Deezer', 'TikTok',
]


def _sync_analytics_children(analytics, request):
    """Дочерние строки по устройствам и платформам из формы (добавление и редактирование)."""
    DeviceAnalytics.query.filter_by(release_analytics_id=analytics.id).delete()
    PlatformAnalytics.query.filter_by(release_analytics_id=analytics.id).delete()

    for device_type in DeviceAnalytics.get_device_types():
        device_streams = request.form.get(f'device_{device_type.lower()}_streams', 0, type=int)
        device_downloads = request.form.get(f'device_{device_type.lower()}_downloads', 0, type=int)
        if device_streams or device_downloads:
            db.session.add(DeviceAnalytics(
                release_analytics_id=analytics.id,
                device_type=device_type,
                streams=device_streams,
                downloads=device_downloads,
            ))

    for idx, platform_name in enumerate(PlatformAnalytics.get_main_platforms()):
        platform_streams = request.form.get(f'platform_{idx}_streams', 0, type=int)
        platform_downloads = request.form.get(f'platform_{idx}_downloads', 0, type=int)
        platform_revenue = request.form.get(f'platform_{idx}_revenue', 0.0, type=float)
        if platform_streams or platform_downloads or platform_revenue:
            db.session.add(PlatformAnalytics(
                release_analytics_id=analytics.id,
                platform_name=platform_name,
                streams=platform_streams,
                downloads=platform_downloads,
                revenue=platform_revenue,
            ))

    extra_name = request.form.get('platform_extra_name', '').strip()
    if extra_name:
        extra_streams = request.form.get('platform_extra_streams', 0, type=int)
        extra_downloads = request.form.get('platform_extra_downloads', 0, type=int)
        extra_revenue = request.form.get('platform_extra_revenue', 0.0, type=float)
        if extra_streams or extra_downloads or extra_revenue:
            db.session.add(PlatformAnalytics(
                release_analytics_id=analytics.id,
                platform_name=extra_name,
                streams=extra_streams,
                downloads=extra_downloads,
                revenue=extra_revenue,
            ))


@stats_bp.route('/stats')
@login_required
def index():
    """Страница аналитики"""
    from flask import current_app
    from app.models.user import User
    current_app.logger.info('Stats index accessed')
    
    # Проверка режима технических работ
    if current_app.config.get('STATS_MAINTENANCE'):
        return render_template('stats/maintenance.html')
    
    releases = []
    selected_release = None
    analytics_data = []
    artists_for_filter = []
    selected_artist_id = request.args.get('artist_id', type=int) if current_user.is_admin else None
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    period = (request.args.get('period') or 'all').strip() or 'all'

    try:
        if current_user.is_admin:
            owner_ids = [
                row[0] for row in db.session.query(Release.user_id)
                .filter(Release.status == 'approved', Release.user_id.isnot(None))
                .distinct()
                .all()
            ]
            if owner_ids:
                artists_for_filter = (
                    User.query.filter(
                        User.id.in_(owner_ids),
                        User.role != 'admin',
                    )
                    .order_by(User.name.asc())
                    .all()
                )
            releases_q = Release.query.options(joinedload(Release.owner)).filter_by(status='approved')
            if selected_artist_id:
                releases_q = releases_q.filter_by(user_id=selected_artist_id)
            releases = releases_q.order_by(Release.created_at.desc()).all()
        else:
            releases = Release.query.filter_by(
                user_id=current_user.id, status='approved'
            ).order_by(Release.created_at.desc()).all()
    except (OperationalError, ProgrammingError) as e:
        current_app.logger.warning('stats.index releases query: %s', e)
        flash('Не удалось загрузить список релизов. Проверьте базу данных.', 'error')
    except Exception as e:
        current_app.logger.exception('stats.index releases: %s', e)
        flash('Ошибка загрузки аналитики.', 'error')

    release_id = request.args.get('release_id', type=int)
    # Если релиз один — сразу открываем его
    if not release_id and len(releases) == 1:
        release_id = releases[0].id

    if release_id:
        try:
            selected_release = db.session.get(Release, release_id)
        except Exception:
            selected_release = None
        # Релиз вне текущего фильтра артиста — сбрасываем выбор
        if (
            selected_release
            and selected_artist_id
            and selected_release.user_id != selected_artist_id
        ):
            selected_release = None
            release_id = None
        if selected_release and (current_user.is_admin or selected_release.user_id == current_user.id):
            try:
                analytics_data = ReleaseAnalytics.query.filter_by(
                    release_id=release_id
                ).order_by(
                    ReleaseAnalytics.year.desc(),
                    ReleaseAnalytics.month.desc(),
                ).all()
            except (OperationalError, ProgrammingError) as e:
                current_app.logger.warning('stats.index analytics query (нет таблицы release_analytics?): %s', e)
                flash('Таблица аналитики ещё не создана или недоступна. Обратитесь к администратору.', 'warning')
            except Exception as e:
                current_app.logger.exception('stats.index analytics: %s', e)

    platform_summary = _aggregate_platform_summary(analytics_data) if analytics_data else []
    device_summary = _aggregate_device_summary(analytics_data) if analytics_data else []

    try:
        return render_template('stats/index.html',
                              releases=releases,
                              selected_release=selected_release,
                              analytics_data=analytics_data,
                              platform_summary=platform_summary,
                              device_summary=device_summary,
                              artists_for_filter=artists_for_filter,
                              selected_artist_id=selected_artist_id,
                              date_from=date_from,
                              date_to=date_to,
                              period=period)
    except Exception as e:
        current_app.logger.exception('stats.index render: %s', e)
        flash('Ошибка отображения страницы аналитики.', 'error')
        return redirect(url_for('dashboard.index'))


@stats_bp.route('/stats/search')
@login_required
@admin_required
def search():
    """Поиск релиза по UPC"""
    upc = request.args.get('upc', '').strip()
    
    if not upc:
        return jsonify({'error': 'UPC не указан'}), 400
    
    release = Release.query.filter_by(upc=upc).first()
    
    if not release:
        return jsonify({'error': 'Релиз не найден'}), 404
    
    return jsonify({
        'id': release.id,
        'title': release.title,
        'artists': release.artists,
        'upc': release.upc,
        'cover_url': release.cover_url
    })


@stats_bp.route('/stats/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add():
    """Добавление аналитики"""
    from flask import current_app
    if current_app.config.get('STATS_MAINTENANCE'):
        flash('Раздел аналитики временно недоступен из-за технических работ. Ожидаемое восстановление: 28 апреля.', 'warning')
        return redirect(url_for('stats.index'))
    
    if request.method == 'POST':
        release_id = request.form.get('release_id', type=int)
        period_type = request.form.get('period_type')  # monthly, weekly
        year = request.form.get('year', type=int)
        month = request.form.get('month', type=int) if period_type == 'monthly' else None
        week = request.form.get('week', type=int) if period_type == 'weekly' else None
        streams = request.form.get('streams', 0, type=int)
        downloads = request.form.get('downloads', 0, type=int)
        revenue = request.form.get('revenue', 0.0, type=float)
        
        # Валидация
        if not release_id or not year:
            flash('Укажите релиз и год', 'error')
            return redirect(url_for('stats.add'))
        
        release = Release.query.get(release_id)
        if not release:
            flash('Релиз не найден', 'error')
            return redirect(url_for('stats.add'))
        
        # Проверка на дубликат
        existing = ReleaseAnalytics.query.filter_by(
            release_id=release_id,
            year=year,
            month=month,
            week=week
        ).first()
        
        if existing:
            flash('Аналитика за этот период уже существует', 'error')
            return redirect(url_for('stats.add'))
        
        # Создание записи
        analytics = ReleaseAnalytics(
            release_id=release_id,
            year=year,
            month=month,
            week=week,
            streams=streams,
            downloads=downloads,
            revenue=revenue
        )
        db.session.add(analytics)
        db.session.flush()  # Получаем ID
        _sync_analytics_children(analytics, request)

        db.session.commit()
        flash('Аналитика добавлена', 'success')
        return redirect(url_for('stats.index', release_id=release_id))
    
    # GET - форма
    releases = Release.query.filter_by(status='approved').order_by(Release.title).all()
    now = datetime.now()
    current_year = now.year
    years = list(range(current_year, current_year - 6, -1))

    return render_template(
        'stats/add.html',
        releases=releases,
        years=years,
        default_month=now.month,
        default_year=current_year,
        device_types=DeviceAnalytics.get_device_types(),
        platform_names=PlatformAnalytics.get_main_platforms(),
    )


@stats_bp.route('/stats/<int:id>')
@login_required
def view(id):
    """Просмотр детальной аналитики"""
    from flask import current_app
    if current_app.config.get('STATS_MAINTENANCE'):
        flash('Раздел аналитики временно недоступен из-за технических работ. Ожидаемое восстановление: 28 апреля.', 'warning')
        return redirect(url_for('stats.index'))
    
    analytics = ReleaseAnalytics.query.get_or_404(id)
    release = analytics.release
    
    # Проверка доступа
    if not current_user.is_admin and release.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('stats.index'))
    
    device_analytics = analytics.device_analytics.all()
    platform_analytics = analytics.platform_analytics.all()
    
    return render_template('stats/view.html',
                          analytics=analytics,
                          release=release,
                          device_analytics=device_analytics,
                          platform_analytics=platform_analytics)


@stats_bp.route('/stats/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    """Редактирование записи аналитики (администратор)."""
    from flask import current_app
    if current_app.config.get('STATS_MAINTENANCE'):
        flash('Раздел аналитики временно недоступен из-за технических работ. Ожидаемое восстановление: 28 апреля.', 'warning')
        return redirect(url_for('stats.index'))
    
    analytics = ReleaseAnalytics.query.get_or_404(id)
    release = analytics.release
    current_year = datetime.now().year
    years = list(range(current_year, current_year - 6, -1))
    platform_names = PlatformAnalytics.get_main_platforms()

    if request.method == 'POST':
        period_type = request.form.get('period_type')
        year = request.form.get('year', type=int)
        month = request.form.get('month', type=int) if period_type == 'monthly' else None
        week = request.form.get('week', type=int) if period_type == 'weekly' else None
        streams = request.form.get('streams', 0, type=int)
        downloads = request.form.get('downloads', 0, type=int)
        revenue = request.form.get('revenue', 0.0, type=float)
        if not year:
            flash('Укажите год', 'error')
            return redirect(url_for('stats.edit', id=id))
        dup = ReleaseAnalytics.query.filter(
            ReleaseAnalytics.release_id == analytics.release_id,
            ReleaseAnalytics.year == year,
            ReleaseAnalytics.month == month,
            ReleaseAnalytics.week == week,
            ReleaseAnalytics.id != analytics.id,
        ).first()
        if dup:
            flash('Запись за этот период уже существует', 'error')
            return redirect(url_for('stats.edit', id=id))
        analytics.year = year
        analytics.month = month
        analytics.week = week
        analytics.streams = streams or 0
        analytics.downloads = downloads or 0
        analytics.revenue = revenue if revenue is not None else 0.0
        _sync_analytics_children(analytics, request)
        db.session.commit()
        flash('Аналитика обновлена', 'success')
        return redirect(url_for('stats.view', id=analytics.id))

    pa_by_name = {p.platform_name: p for p in analytics.platform_analytics.all()}
    platform_prefill = []
    for name in platform_names:
        p = pa_by_name.pop(name, None)
        platform_prefill.append({
            'streams': p.streams if p else 0,
            'downloads': p.downloads if p else 0,
            'revenue': p.revenue if p else 0.0,
        })
    extra_platform = None
    if pa_by_name:
        ename, p = next(iter(pa_by_name.items()))
        extra_platform = {
            'name': ename,
            'streams': p.streams,
            'downloads': p.downloads,
            'revenue': p.revenue,
        }

    if analytics.month is not None:
        period_type = 'monthly'
    elif analytics.week is not None:
        period_type = 'weekly'
    else:
        period_type = 'monthly'

    return render_template(
        'stats/edit.html',
        analytics=analytics,
        release=release,
        years=years,
        platform_names=platform_names,
        platform_prefill=platform_prefill,
        extra_platform=extra_platform,
        period_type=period_type,
    )


@stats_bp.route('/stats/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    """Удаление аналитики"""
    from flask import current_app
    if current_app.config.get('STATS_MAINTENANCE'):
        flash('Раздел аналитики временно недоступен из-за технических работ. Ожидаемое восстановление: 28 апреля.', 'warning')
        return redirect(url_for('stats.index'))
    
    analytics = ReleaseAnalytics.query.get_or_404(id)
    release_id = analytics.release_id
    
    db.session.delete(analytics)
    db.session.commit()
    
    flash('Аналитика удалена', 'success')
    return redirect(url_for('stats.index', release_id=release_id))


@stats_bp.route('/stats/chart-data')
@login_required
def chart_data():
    """Данные для графиков"""
    from flask import current_app
    if current_app.config.get('STATS_MAINTENANCE'):
        return jsonify({'error': 'Раздел аналитики временно недоступен из-за технических работ. Ожидаемое восстановление: 28 апреля.'}), 503
    
    release_id = request.args.get('release_id', type=int)
    chart_type = request.args.get('type', 'monthly')  # monthly, weekly
    metric = request.args.get('metric', 'streams')  # streams, downloads, revenue
    year = request.args.get('year', datetime.now().year, type=int)
    
    if not release_id:
        return jsonify({'error': 'Релиз не указан'}), 400
    
    release = Release.query.get(release_id)
    if not release:
        return jsonify({'error': 'Релиз не найден'}), 404
    
    # Проверка доступа
    if not current_user.is_admin and release.user_id != current_user.id:
        return jsonify({'error': 'Доступ запрещён'}), 403
    
    # Получение данных
    query = ReleaseAnalytics.query.filter_by(release_id=release_id, year=year)
    
    if chart_type == 'monthly':
        query = query.filter(ReleaseAnalytics.month.isnot(None)).order_by(ReleaseAnalytics.month)
    else:
        query = query.filter(ReleaseAnalytics.week.isnot(None)).order_by(ReleaseAnalytics.week)
    
    analytics = query.all()
    
    # Формирование данных
    labels = []
    values = []
    
    months = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
              'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    
    for item in analytics:
        if chart_type == 'monthly':
            if item.month is not None and 1 <= item.month <= 12:
                labels.append(months[item.month - 1])
            else:
                labels.append(str(item.month or '?'))
        else:
            labels.append(f'Нед. {item.week}' if item.week is not None else '?')
        
        if metric == 'streams':
            values.append(item.streams)
        elif metric == 'downloads':
            values.append(item.downloads)
        else:
            values.append(item.revenue)
    
    return jsonify({
        'labels': labels,
        'values': values,
        'metric': metric
    })


def _release_access(release):
    if not release:
        return False
    return current_user.is_admin or release.user_id == current_user.id


@stats_bp.route('/stats/listens')
@login_required
def listens_chart():
    """График прослушиваний по площадкам по дням (как на дашборде)."""
    if current_user.is_admin:
        releases = Release.query.filter_by(status='approved').order_by(Release.created_at.desc()).all()
    else:
        releases = Release.query.filter_by(
            user_id=current_user.id, status='approved'
        ).order_by(Release.created_at.desc()).all()
    release_id = request.args.get('release_id', type=int)
    selected = None
    if release_id:
        selected = Release.query.get(release_id)
        if selected and not _release_access(selected):
            selected = None
    date_to = date.today()
    date_from = date_to - timedelta(days=30)
    return render_template('stats/listens.html',
                          releases=releases,
                          selected_release=selected,
                          date_from=date_from.isoformat(),
                          date_to=date_to.isoformat())


@stats_bp.route('/stats/listens-chart-data')
@login_required
def listens_chart_data():
    """JSON для мульти-площадочного графика по дням."""
    release_id = request.args.get('release_id', type=int)
    date_from_s = request.args.get('date_from', '')
    date_to_s = request.args.get('date_to', '')
    if not release_id:
        return jsonify({'error': 'Релиз не указан'}), 400
    release = Release.query.get(release_id)
    if not release or not _release_access(release):
        return jsonify({'error': 'Нет доступа'}), 403
    try:
        date_from = date.fromisoformat(date_from_s) if date_from_s else date.today() - timedelta(days=30)
        date_to = date.fromisoformat(date_to_s) if date_to_s else date.today()
    except ValueError:
        return jsonify({'error': 'Неверный формат даты'}), 400
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    try:
        rows = PlatformDailyListen.query.filter(
        PlatformDailyListen.release_id == release_id,
        PlatformDailyListen.stat_date >= date_from,
        PlatformDailyListen.stat_date <= date_to
    ).order_by(PlatformDailyListen.stat_date).all()
    except (OperationalError, ProgrammingError):
        return jsonify({'labels': [], 'labels_iso': [], 'datasets': []})

    # Собираем множество дат и платформ
    dates_set = set()
    platforms_set = set()
    raw = {}  # (date_iso, platform) -> listens
    for r in rows:
        d = r.stat_date.isoformat()
        dates_set.add(r.stat_date)
        platforms_set.add(r.platform_name)
        raw[(d, r.platform_name)] = r.listens

    # Все дни подряд в диапазоне (чтобы ось была непрерывной)
    labels = []
    d = date_from
    while d <= date_to:
        labels.append(d.isoformat())
        d += timedelta(days=1)

    # Платформы с ненулевыми данными + порядок как в default_platforms
    ordered = [p for p in PlatformDailyListen.default_platforms() if p in platforms_set]
    for p in sorted(platforms_set):
        if p not in ordered:
            ordered.append(p)

    # Цвета по имени платформы (как на скрине — разные оттенки)
    palette = [
        'rgba(234, 179, 8, 0.6)',   # yellow
        'rgba(239, 68, 68, 0.6)',   # red
        'rgba(34, 197, 94, 0.6)',   # green
        'rgba(168, 85, 247, 0.6)',  # purple
        'rgba(59, 130, 246, 0.6)',  # blue
        'rgba(56, 189, 248, 0.6)',  # light blue
        'rgba(99, 102, 241, 0.6)',
        'rgba(132, 204, 22, 0.6)',
        'rgba(249, 115, 22, 0.6)',
        'rgba(107, 114, 128, 0.6)',
        'rgba(14, 165, 233, 0.6)',
        'rgba(251, 146, 60, 0.6)',
        'rgba(250, 204, 21, 0.6)',
        'rgba(236, 72, 153, 0.6)',
        'rgba(30, 64, 175, 0.6)',
    ]
    border_palette = [c.replace('0.6', '1') for c in palette]

    datasets = []
    for i, platform in enumerate(ordered):
        data = []
        for label in labels:
            data.append(raw.get((label, platform), 0))
        if sum(data) == 0:
            continue
        c = palette[i % len(palette)]
        bc = border_palette[i % len(border_palette)]
        datasets.append({
            'label': platform,
            'data': data,
            'backgroundColor': c,
            'borderColor': bc,
            'fill': True,
            'tension': 0.35,
            'pointRadius': 0,
        })

    # Короткие подписи оси X (день.месяц)
    short_labels = []
    for label in labels:
        parts = label.split('-')
        if len(parts) == 3:
            short_labels.append('%d.%02d' % (int(parts[2]), int(parts[1])))
        else:
            short_labels.append(label)

    return jsonify({
        'labels': short_labels,
        'labels_iso': labels,
        'datasets': datasets,
    })


@stats_bp.route('/stats/listens-daily', methods=['GET', 'POST'])
@login_required
@admin_required
def listens_daily_add():
    """Ввод прослушиваний по площадкам за день (админ)."""
    releases = Release.query.filter_by(status='approved').order_by(Release.title).all()
    platform_list = PlatformDailyListen.default_platforms()

    if request.method == 'POST':
        release_id = request.form.get('release_id', type=int)
        stat_date_s = request.form.get('stat_date', '').strip()
        if not release_id or not stat_date_s:
            flash('Укажите релиз и дату', 'error')
            return redirect(url_for('stats.listens_daily_add'))
        try:
            stat_date = date.fromisoformat(stat_date_s)
        except ValueError:
            flash('Неверная дата', 'error')
            return redirect(url_for('stats.listens_daily_add'))
        release = Release.query.get(release_id)
        if not release:
            flash('Релиз не найден', 'error')
            return redirect(url_for('stats.listens_daily_add'))

        # Удаляем старые записи за этот день по этому релизу и пишем заново (проще чем upsert по каждой)
        try:
            PlatformDailyListen.query.filter_by(release_id=release_id, stat_date=stat_date).delete()
        except (OperationalError, ProgrammingError) as e:
            flash('Таблица platform_daily_listens не создана. Перезапустите приложение или выполните db.create_all().', 'error')
            current_app.logger.warning('listens_daily_add delete: %s', e)
            return redirect(url_for('stats.listens_daily_add'))

        for idx, platform_name in enumerate(platform_list):
            n = request.form.get(f'platform_{idx}_listens', 0, type=int) or 0
            if n > 0:
                db.session.add(PlatformDailyListen(
                    release_id=release_id,
                    stat_date=stat_date,
                    platform_name=platform_name,
                    listens=n
                ))
        extra_name = request.form.get('platform_extra_name', '').strip()
        if extra_name:
            n = request.form.get('platform_extra_listens', 0, type=int) or 0
            if n > 0:
                db.session.add(PlatformDailyListen(
                    release_id=release_id,
                    stat_date=stat_date,
                    platform_name=extra_name,
                    listens=n
                ))
        db.session.commit()
        flash('Данные за день сохранены', 'success')
        return redirect(url_for('stats.listens_chart', release_id=release_id))

    return render_template('stats/listens_daily_add.html',
                          releases=releases,
                          platform_list=platform_list,
                          today=date.today().isoformat())
