"""
Управление релизами
"""

import os
import csv
import shutil
from io import StringIO
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, current_app, send_file, jsonify, abort)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.release import Release, Track, Platform
from app.models.notification import Notification
from app.utils.files import save_file, delete_file, allowed_file
from app.utils.validators import normalize_isrc
from app.utils.email import send_release_submitted_email
from app.utils.releases_restriction import user_releases_restricted, releases_restriction_flash_message
from app.services.release_events import (
    log_release_event,
    log_admin_viewed_if_needed,
    get_release_events,
)

releases_bp = Blueprint('releases', __name__)


def _release_docs_dir(release_id):
    return os.path.join(current_app.root_path, '..', 'uploads', 'release_docs', str(release_id))


def _list_release_documents(release_id):
    docs_dir = _release_docs_dir(release_id)
    if not os.path.isdir(docs_dir):
        return []
    docs = []
    for filename in sorted(os.listdir(docs_dir)):
        file_path = os.path.join(docs_dir, filename)
        if not os.path.isfile(file_path):
            continue
        docs.append({
            'filename': filename,
            'size': os.path.getsize(file_path),
        })
    return docs


def _cleanup_release_documents(release_id):
    docs_dir = _release_docs_dir(release_id)
    if os.path.isdir(docs_dir):
        shutil.rmtree(docs_dir, ignore_errors=True)


def hard_delete_release(release):
    """
    Полное удаление релиза: связанные строки + файлы.
    Нужно из‑за FK (события, уведомления, смарт-ссылки и т.д.) —
    иначе db.session.delete(release) даёт 502.
    """
    from app.models.release_event import ReleaseEvent
    from app.models.notification import Notification
    from app.models.smart_link import SmartLink
    from app.models.analytics import PlatformDailyListen
    from app.models.workspace import WorkspaceReleasePlan
    from app.models.pitch import Pitch
    from app.models.auto_form import AutoFormRequest

    release_id = release.id
    cover_name = release.cover
    track_files = [
        t.wav_file for t in release.tracks.order_by(Track.track_order).all()
        if t.wav_file
    ]

    # Nullable FK — обнуляем, записи оставляем
    Pitch.query.filter_by(release_id=release_id).update(
        {Pitch.release_id: None}, synchronize_session=False
    )
    AutoFormRequest.query.filter_by(release_id=release_id).update(
        {AutoFormRequest.release_id: None}, synchronize_session=False
    )
    WorkspaceReleasePlan.query.filter_by(release_id=release_id).update(
        {WorkspaceReleasePlan.release_id: None}, synchronize_session=False
    )
    Notification.query.filter_by(release_id=release_id).update(
        {Notification.release_id: None}, synchronize_session=False
    )

    # Обязательные FK — удаляем
    ReleaseEvent.query.filter_by(release_id=release_id).delete(synchronize_session=False)
    PlatformDailyListen.query.filter_by(release_id=release_id).delete(
        synchronize_session=False
    )
    for link in SmartLink.query.filter_by(release_id=release_id).all():
        db.session.delete(link)

    db.session.delete(release)
    db.session.commit()

    if cover_name:
        delete_file(cover_name, 'covers')
    for fname in track_files:
        delete_file(fname, 'tracks')
    _cleanup_release_documents(release_id)
    return release_id


def _iter_track_slot_indices(form):
    """Индексы слотов треков из полей tracks-{i}-title / tracks-{i}-artists."""
    indices = set()
    for key in form.keys():
        if key.startswith('tracks-') and key.endswith('-title'):
            mid = key[len('tracks-'):-len('-title')]
            if mid.isdigit():
                indices.add(int(mid))
        elif key.startswith('tracks-') and key.endswith('-artists'):
            mid = key[len('tracks-'):-len('-artists')]
            if mid.isdigit():
                indices.add(int(mid))
    return sorted(indices)


def _create_tracks_from_form(release, req):
    """
    Создать треки из one-screen формы.
    Возвращает (created_count, errors).
    """
    errors = []
    created = 0
    order = 0
    for idx in _iter_track_slot_indices(req.form):
        prefix = f'tracks-{idx}'
        title = (req.form.get(f'{prefix}-title') or '').strip()
        artists = (req.form.get(f'{prefix}-artists') or '').strip()
        wav_file = req.files.get(f'{prefix}-wav')

        # Пустой / незаполненный слот пропускаем (артисты могут быть предзаполнены)
        has_wav = bool(wav_file and wav_file.filename)
        if not title and not has_wav:
            continue

        if not title or not artists:
            errors.append(f'Трек #{idx + 1}: укажите название и артистов')
            continue
        if not has_wav:
            errors.append(f'Трек #{idx + 1}: нужен WAV-файл')
            continue
        if not allowed_file(wav_file.filename, current_app.config['ALLOWED_TRACK_EXTENSIONS']):
            errors.append(f'Трек #{idx + 1}: разрешены только WAV-файлы')
            continue

        filename = save_file(wav_file, 'tracks')
        if not filename:
            errors.append(f'Трек #{idx + 1}: не удалось сохранить файл')
            continue

        order += 1
        track = Track(
            release_id=release.id,
            wav_file=filename,
            title=title,
            version=(req.form.get(f'{prefix}-version') or '').strip() or None,
            artists=artists,
            composers=(req.form.get(f'{prefix}-composers') or '').strip() or None,
            authors=(req.form.get(f'{prefix}-authors') or '').strip() or None,
            explicit=req.form.get(f'{prefix}-explicit') == 'on',
            language=(req.form.get(f'{prefix}-language') or '').strip() or None,
            isrc=normalize_isrc(req.form.get(f'{prefix}-isrc', '')),
            lyrics=(req.form.get(f'{prefix}-lyrics') or '').strip() or None,
            track_order=order,
        )
        db.session.add(track)
        created += 1

    return created, errors


def _save_release_documents_from_request(release, req):
    """Сохранить PDF из формы создания/отправки. Возвращает (saved_count, error_message|None)."""
    files = req.files.getlist('release_documents')
    allowed_docs = current_app.config.get('ALLOWED_DOC_CONFIRM_EXTENSIONS', {'pdf'})
    max_doc_size = current_app.config.get('MAX_DOC_CONFIRM_SIZE', 15 * 1024 * 1024)
    docs_subfolder = f'release_docs/{release.id}'
    saved_docs = 0

    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename, allowed_docs):
            return saved_docs, 'Подтверждающие документы: разрешены только PDF-файлы'
        file.stream.seek(0, os.SEEK_END)
        file_size = file.stream.tell()
        file.stream.seek(0)
        if file_size > max_doc_size:
            max_mb = max_doc_size // (1024 * 1024)
            return saved_docs, f'Файл подтверждающего документа слишком большой (максимум {max_mb} МБ)'
        saved_filename = save_file(file, docs_subfolder)
        if not saved_filename:
            return saved_docs, 'Не удалось сохранить один из подтверждающих документов'
        saved_docs += 1

    return saved_docs, None


@releases_bp.route('/releases')
@login_required
def index():
    """Список релизов"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    
    # Базовый запрос
    query = Release.query.filter_by(user_id=current_user.id)
    
    # Фильтрация по статусу
    if status:
        query = query.filter_by(status=status)
    
    # Поиск по названию и артистам
    if search:
        query = query.filter(
            (Release.title.ilike(f'%{search}%')) |
            (Release.artists.ilike(f'%{search}%'))
        )
    
    # Сортировка и пагинация
    releases = query.order_by(Release.created_at.desc()).paginate(
        page=page,
        per_page=current_app.config.get('RELEASES_PER_PAGE', 12),
        error_out=False
    )
    
    # Статусы для фильтра (пользовательский каталог)
    statuses = [
        ('', 'Все'),
        ('draft', 'Черновик'),
        ('moderation', 'На модерации'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонён'),
        ('revoked', 'Снят'),
        ('deletion', 'На удалении'),
        ('deleted', 'Удалены'),
    ]
    
    return render_template('releases/index.html',
                          releases=releases,
                          statuses=statuses,
                          current_status=status,
                          search=search)


# Компактный список территорий для UI «Страны» (фаза 3)
RELEASE_TERRITORIES = [
    ('EU', 'Европа'),
    ('AS', 'Азия'),
    ('NA', 'Северная Америка'),
    ('SA', 'Южная Америка'),
    ('AF', 'Африка'),
    ('OC', 'Океания'),
    ('RU', 'Россия'),
    ('BY', 'Беларусь'),
    ('KZ', 'Казахстан'),
    ('UA', 'Украина'),
    ('US', 'США'),
    ('CA', 'Канада'),
    ('GB', 'Великобритания'),
    ('DE', 'Германия'),
    ('FR', 'Франция'),
    ('ES', 'Испания'),
    ('IT', 'Италия'),
    ('PL', 'Польша'),
    ('TR', 'Турция'),
    ('JP', 'Япония'),
    ('KR', 'Южная Корея'),
    ('CN', 'Китай'),
    ('IN', 'Индия'),
    ('BR', 'Бразилия'),
    ('MX', 'Мексика'),
    ('AR', 'Аргентина'),
    ('AU', 'Австралия'),
    ('NZ', 'Новая Зеландия'),
    ('AE', 'ОАЭ'),
    ('IL', 'Израиль'),
]


def _ensure_release_dist_settings_column():
    """Мягко добавить releases.dist_settings, если колонки ещё нет."""
    from sqlalchemy import inspect, text
    try:
        insp = inspect(db.engine)
        if 'releases' not in insp.get_table_names():
            return
        cols = {c['name'] for c in insp.get_columns('releases')}
        if 'dist_settings' in cols:
            return
        dialect = db.engine.dialect.name
        if dialect == 'sqlite':
            db.session.execute(text('ALTER TABLE releases ADD COLUMN dist_settings TEXT'))
        else:
            db.session.execute(text('ALTER TABLE releases ADD COLUMN dist_settings JSON NULL'))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning('ensure dist_settings column: %s', e)


def _ensure_default_platforms():
    """Добавить недостающие площадки из каталога (без удаления существующих)."""
    try:
        Platform.__table__.create(bind=db.engine, checkfirst=True)
    except Exception as e:
        current_app.logger.warning('ensure platforms table: %s', e)
        return
    try:
        existing = {p.name for p in Platform.query.all()}
        added = 0
        for row in Platform.get_default_platforms():
            if row['name'] in existing:
                continue
            db.session.add(Platform(
                name=row['name'],
                category=row['category'],
                sort_order=row.get('sort_order') or 0,
                is_active=True,
            ))
            added += 1
        if added:
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.warning('ensure default platforms: %s', e)


_PLATFORM_CATEGORY_ORDER = (
    'main', 'other', 'streaming', 'social', 'video', 'store',
    'database', 'radio', 'dj', 'international',
)


def _platforms_by_category_ordered(platform_rows):
    grouped = {}
    for p in platform_rows:
        grouped.setdefault(p.category, []).append(p)
    ordered = {}
    for cat in _PLATFORM_CATEGORY_ORDER:
        if cat in grouped:
            ordered[cat] = grouped.pop(cat)
    for cat in sorted(grouped.keys()):
        ordered[cat] = grouped[cat]
    return ordered


def _parse_platform_ids_from_form(req):
    """Выбранные площадки из формы; пустой список = ничего не выбрано."""
    raw = req.form.getlist('platform_ids')
    ids = []
    for item in raw:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    if not ids:
        return []
    valid = {
        p.id for p in Platform.query.filter(
            Platform.id.in_(ids), Platform.is_active.is_(True)
        ).all()
    }
    return [i for i in ids if i in valid]


def _parse_names_to_artist_objects(raw):
    """'Артист 1, Артист 2' -> [{"nickname": "Артист 1"}, ...] (формат API-доки)."""
    if not raw:
        return []
    names = [n.strip() for n in raw.split(',') if n and n.strip()]
    return [{'nickname': n} for n in names]


def _parse_royalties_from_form(req):
    """
    Одна строка — один получатель: 'Имя артиста : 50'.
    Возвращает список объектов вида [{"artist": "...", "share": 50}], как в API-доке.
    """
    raw = (req.form.get('royalties_text') or '').strip()
    if not raw:
        return []
    rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if ':' in line:
            name, _, share = line.rpartition(':')
        else:
            name, share = line, ''
        name = name.strip()
        share = share.strip().replace('%', '')
        if not name:
            continue
        entry = {'artist': name}
        try:
            entry['share'] = float(share) if share else None
        except ValueError:
            entry['share'] = None
        rows.append(entry)
    return rows


def _parse_dist_settings_from_form(req):
    """Территории, цены и доп. поля из формы создания/редактирования."""
    worldwide = req.form.get('territory_worldwide') == 'on'
    codes = [c.strip().upper() for c in req.form.getlist('territories') if c and c.strip()]
    allowed = {code for code, _ in RELEASE_TERRITORIES}
    codes = [c for c in codes if c in allowed]
    notes = (req.form.get('extra_notes') or '').strip()
    if len(notes) > 4000:
        notes = notes[:4000]
    comment = (req.form.get('comment') or '').strip()
    if len(comment) > 2000:
        comment = comment[:2000]

    def _date_or_none(field):
        val = (req.form.get(field) or '').strip()
        if not val:
            return None
        try:
            datetime.strptime(val, '%Y-%m-%d')
            return val
        except ValueError:
            return None

    return {
        'territories': 'worldwide' if worldwide or not codes else codes,
        'allow_preview_before_release': req.form.get('allow_preview_before_release') == 'on',
        'price_itunes_album': (req.form.get('price_itunes_album') or 'default').strip(),
        'price_itunes_track': (req.form.get('price_itunes_track') or 'default').strip(),
        'price_secondary': (req.form.get('price_secondary') or 'default').strip(),
        'price_ru': (req.form.get('price_ru') or 'default').strip(),
        'extra_notes': notes,
        # —— Поля по документации API (POST/PUT /releases) ——
        'subgenre': (req.form.get('subgenre') or '').strip() or None,
        'catalog_number': (req.form.get('catalog_number') or '').strip() or None,
        'itunes_price_category': (req.form.get('itunes_price_category') or '').strip() or None,
        'comment': comment or None,
        'language': (req.form.get('meta_language') or '').strip() or None,
        'featuring_artists': _parse_names_to_artist_objects(req.form.get('featuring_artists', '')),
        'royalties': _parse_royalties_from_form(req),
        'was_released_before': req.form.get('was_released_before') == 'on',
        'premiere_for_russia': req.form.get('premiere_for_russia') == 'on',
        'realtime': req.form.get('realtime') == 'on',
        'yandex_presave_enabled': req.form.get('yandex_presave') == 'on',
        'preorder_date': _date_or_none('preorder_date'),
        'original_release_date': _date_or_none('original_release_date'),
        'yandex_presave_date': _date_or_none('yandex_presave_date'),
    }


# Статусы доставки, которые выставляет администратор
DELIVERY_STATUS_OPTIONS = (
    'Выбрано · ждёт отправки',
    'В очереди на отгрузку',
    'Передан партнёрам',
    'В работе',
    'На витрине',
    'Доставлено',
    'Отменено',
    'Снятие с витрин',
)


def _platform_ids_ordered(release):
    raw = release.platforms if release else None
    if not raw or not isinstance(raw, list):
        return []
    ids = []
    for x in raw:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    return ids


def _default_delivery_for_release_status(release_status, date_str):
    status = (release_status or 'draft')
    if status == 'draft':
        return 'Выбрано · ждёт отправки', date_str, '—'
    if status == 'moderation':
        return 'В очереди на отгрузку', 'после одобрения', '—'
    if status == 'approved':
        return 'Передан партнёрам', date_str, 'В работе'
    if status in ('rejected', 'revoked'):
        return 'Отменено', '—', '—'
    if status == 'deletion':
        return 'Снятие с витрин', date_str, '—'
    return status, '—', '—'


def _delivery_rows_for_release(release):
    """
    Статусы доставки по площадкам.
    Админ может переопределить значения в dist_settings.delivery.
    """
    ids = _platform_ids_ordered(release)
    if not ids:
        return []
    rows_db = Platform.query.filter(Platform.id.in_(ids)).all()
    by_id = {r.id: r.name for r in rows_db}
    date_str = (
        release.release_date.strftime('%Y-%m-%d')
        if release and release.release_date
        else '—'
    )
    saved = {}
    ds = release.dist_settings if isinstance(release.dist_settings, dict) else {}
    raw_delivery = ds.get('delivery') or {}
    if isinstance(raw_delivery, dict):
        saved = raw_delivery

    def_status, def_planned, def_delivered = _default_delivery_for_release_status(
        release.status if release else 'draft', date_str
    )
    rows = []
    for pid in ids:
        name = by_id.get(pid)
        if not name:
            continue
        ov = saved.get(str(pid)) if isinstance(saved.get(str(pid)), dict) else {}
        rows.append({
            'platform_id': pid,
            'retailer': name,
            'content': (ov.get('content') or 'Аудио').strip() or 'Аудио',
            'status': (ov.get('status') or def_status).strip() or def_status,
            'urgent': (ov.get('urgent') if ov.get('urgent') is not None else '—') or '—',
            'planned': (ov.get('planned') if ov.get('planned') is not None else def_planned) or '—',
            'delivered': (ov.get('delivered') if ov.get('delivered') is not None else def_delivered) or '—',
            'custom': bool(ov),
        })
    return rows


def _save_delivery_from_form(release, req):
    """Сохранить статусы доставки из формы админа в dist_settings.delivery."""
    ids = set(_platform_ids_ordered(release))
    delivery = {}
    for pid in ids:
        key = str(pid)
        status = (req.form.get(f'delivery-{pid}-status') or '').strip()
        if status not in DELIVERY_STATUS_OPTIONS:
            continue
        urgent = (req.form.get(f'delivery-{pid}-urgent') or '—').strip() or '—'
        planned = (req.form.get(f'delivery-{pid}-planned') or '—').strip() or '—'
        delivered = (req.form.get(f'delivery-{pid}-delivered') or '—').strip() or '—'
        delivery[key] = {
            'content': 'Аудио',
            'status': status,
            'urgent': urgent,
            'planned': planned,
            'delivered': delivered,
        }
    ds = dict(release.dist_settings) if isinstance(release.dist_settings, dict) else {}
    ds['delivery'] = delivery
    release.dist_settings = ds
    return len(delivery)


def _create_page_context(form_data=None, default_artists=None):
    """Контекст шаблона «Новый релиз»."""
    _ensure_default_platforms()
    platform_rows = (
        Platform.query.filter_by(is_active=True)
        .order_by(Platform.sort_order, Platform.name)
        .all()
    )
    return {
        'genres': current_app.config.get('RELEASE_GENRES', []),
        'form_data': form_data,
        'default_artists': default_artists or current_user.display_name,
        'platform_names': [p.name for p in platform_rows],
        'platforms': platform_rows,
        'platforms_by_category': _platforms_by_category_ordered(platform_rows),
        'territories': RELEASE_TERRITORIES,
        'default_copyright': current_user.get_default_copyright(),
        'partner_code': current_user.partner_code or '',
    }


@releases_bp.route('/releases/create', methods=['GET', 'POST'])
@login_required
def create():
    """Создание релиза — один экран: метаданные, треки, черновик или отправка."""
    if user_releases_restricted(current_user):
        flash(releases_restriction_flash_message(current_user), 'error')
        return redirect(url_for('releases.index'))

    if request.method == 'POST':
        action = (request.form.get('action') or 'draft').strip()
        if action not in ('draft', 'submit'):
            action = 'draft'

        title = request.form.get('title', '').strip()
        version = request.form.get('version', '').strip()
        artists = request.form.get('artists', '').strip()
        release_type = request.form.get('type', 'Single')
        genre = request.form.get('genre', '').strip()
        release_date_str = request.form.get('release_date', '')
        yandex_presave = request.form.get('yandex_presave') == 'on'
        upc = request.form.get('upc', '').strip() or None
        partner_code = current_user.partner_code
        copyright_text = current_user.get_default_copyright()
        platforms = _parse_platform_ids_from_form(request)
        dist_settings = _parse_dist_settings_from_form(request)

        errors = []
        if not title:
            errors.append('Название релиза обязательно')
        if not artists:
            errors.append('Артисты обязательны')
        if not genre:
            errors.append('Жанр обязателен')

        release_date = None
        if release_date_str:
            try:
                release_date = datetime.strptime(release_date_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append('Неверный формат даты')
        elif action == 'submit':
            errors.append('Дата релиза обязательна — укажите в «Даты и цены»')
        else:
            # Черновик без даты: подставляем +14 дней, чтобы форма не ломалась
            from datetime import date, timedelta
            release_date = date.today() + timedelta(days=14)

        cover_file = request.files.get('cover')
        cover_filename = None
        if cover_file and cover_file.filename:
            if allowed_file(cover_file.filename, current_app.config['ALLOWED_COVER_EXTENSIONS']):
                cover_filename = save_file(cover_file, 'covers')
                if not cover_filename:
                    errors.append('Не удалось сохранить обложку')
            else:
                errors.append('Недопустимый формат обложки. Разрешены: JPG, PNG')

        if action == 'submit':
            if not cover_filename:
                errors.append('Для отправки на модерацию нужна обложка')
            if not platforms:
                errors.append('Выберите хотя бы одну площадку в разделе «Дистрибуция»')
            if request.form.get('confirm_no_drugs') != 'on':
                errors.append(
                    'Подтвердите отсутствие пропаганды наркотических средств перед отправкой'
                )
            if dist_settings.get('was_released_before') and not dist_settings.get('original_release_date'):
                errors.append(
                    'Укажите дату первого релиза («Даты и цены») — отмечено «релиз уже выходил ранее»'
                )

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template(
                'releases/create.html',
                **_create_page_context(
                    form_data=request.form,
                    default_artists=artists or current_user.display_name,
                ),
            )

        _ensure_release_dist_settings_column()
        release = Release(
            user_id=current_user.id,
            title=title,
            version=version or None,
            artists=artists,
            type=release_type,
            genre=genre,
            release_date=release_date,
            yandex_presave=yandex_presave,
            upc=upc,
            partner_code=partner_code or current_user.partner_code,
            copyright=copyright_text or current_user.get_default_copyright(),
            platforms=platforms if platforms else None,
            dist_settings=dist_settings,
            cover=cover_filename,
            status='draft',
        )
        db.session.add(release)
        db.session.flush()

        tracks_created, track_errors = _create_tracks_from_form(release, request)
        if track_errors:
            db.session.rollback()
            for error in track_errors:
                flash(error, 'error')
            return render_template(
                'releases/create.html',
                **_create_page_context(
                    form_data=request.form,
                    default_artists=artists or current_user.display_name,
                ),
            )

        if action == 'submit' and tracks_created < 1:
            db.session.rollback()
            flash('Для отправки на модерацию добавьте хотя бы один трек', 'error')
            return render_template(
                'releases/create.html',
                **_create_page_context(
                    form_data=request.form,
                    default_artists=artists or current_user.display_name,
                ),
            )

        saved_docs = 0
        if action == 'submit':
            saved_docs, doc_error = _save_release_documents_from_request(release, request)
            if doc_error:
                db.session.rollback()
                flash(doc_error, 'error')
                return render_template(
                    'releases/create.html',
                    **_create_page_context(
                        form_data=request.form,
                        default_artists=artists or current_user.display_name,
                    ),
                )
            release.status = 'moderation'
            release.moderator_comment = None
            log_release_event(release, 'submitted', actor=current_user, commit=False)

        db.session.commit()

        if action == 'submit':

            try:
                db.session.add(
                    Notification(
                        user_id=release.user_id,
                        kind='release_submitted',
                        title='Релиз отправлен на модерацию',
                        message=f'«{release.title}» передан на проверку.',
                        release_id=release.id,
                    )
                )
                db.session.commit()
            except Exception as e:
                current_app.logger.warning('in-app notification release_submitted: %s', e)

            try:
                ok = send_release_submitted_email(release)
                if not ok:
                    flash(
                        'Релиз отправлен на модерацию. Уведомление на почту не отправлено — '
                        'проверьте email в профиле и настройки SMTP в .env',
                        'warning',
                    )
            except Exception as e:
                current_app.logger.warning('Ошибка отправки уведомления о модерации: %s', e)
                flash(
                    'Релиз отправлен на модерацию. Не удалось отправить письмо на почту — '
                    'проверьте настройки SMTP.',
                    'warning',
                )

            if saved_docs:
                flash(f'Загружено подтверждающих документов: {saved_docs}', 'success')
            flash('Релиз создан и отправлен на модерацию', 'success')
        else:
            if tracks_created:
                flash(f'Черновик сохранён. Треков: {tracks_created}.', 'success')
            else:
                flash('Черновик сохранён. Можно добавить треки и отправить позже.', 'success')

        return redirect(url_for('releases.view', id=release.id))

    return render_template('releases/create.html', **_create_page_context())


@releases_bp.route('/releases/<int:id>')
@login_required
def view(id):
    """Просмотр релиза"""
    release = Release.query.get_or_404(id)
    
    # Проверка доступа
    if release.user_id != current_user.id and not current_user.is_admin:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('releases.index'))

    try:
        Notification.query.filter_by(
            user_id=current_user.id, release_id=release.id, is_read=False
        ).update({'is_read': True})
        db.session.commit()
    except Exception:
        db.session.rollback()

    if current_user.is_admin and release.status == 'moderation':
        try:
            log_admin_viewed_if_needed(release, current_user)
        except Exception as e:
            current_app.logger.warning('release event admin_viewed: %s', e)

    tracks = release.tracks.order_by(Track.track_order).all()
    release_documents = _list_release_documents(release.id)
    release_events = get_release_events(release.id, viewer=current_user, release=release)
    delivery_rows = _delivery_rows_for_release(release)

    return render_template(
        'releases/view.html',
        release=release,
        tracks=tracks,
        release_documents=release_documents,
        release_events=release_events,
        delivery_rows=delivery_rows,
        delivery_status_options=DELIVERY_STATUS_OPTIONS,
    )


@releases_bp.route('/releases/<int:id>/delivery', methods=['POST'])
@login_required
def update_delivery(id):
    """Админ обновляет статусы доставки по площадкам."""
    if not current_user.is_admin:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('releases.view', id=id))

    release = Release.query.get_or_404(id)
    _ensure_release_dist_settings_column()
    count = _save_delivery_from_form(release, request)
    db.session.commit()
    flash(f'Статусы доставки обновлены ({count} площадок)', 'success')

    next_url = (request.form.get('next') or '').strip()
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect(url_for('releases.view', id=id))


@releases_bp.route('/releases/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Редактирование релиза"""
    release = Release.query.get_or_404(id)
    
    # Проверка доступа
    if release.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('releases.index'))
    
    # Проверка возможности редактирования
    if not release.can_edit():
        flash('Этот релиз нельзя редактировать', 'error')
        return redirect(url_for('releases.view', id=id))
    
    if request.method == 'POST':
        # Обновление данных
        release.title = request.form.get('title', '').strip()
        release.version = request.form.get('version', '').strip() or None
        release.artists = request.form.get('artists', '').strip()
        release.type = request.form.get('type', 'Single')
        release.genre = request.form.get('genre', '').strip()
        release.yandex_presave = request.form.get('yandex_presave') == 'on'
        release.upc = request.form.get('upc', '').strip() or None

        release_date_str = request.form.get('release_date', '')
        if release_date_str:
            try:
                release.release_date = datetime.strptime(release_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Неверный формат даты', 'error')

        # Площадки и доп. настройки — можно править в черновике
        platforms = _parse_platform_ids_from_form(request)
        release.platforms = platforms if platforms else None
        dist_patch = _parse_dist_settings_from_form(request)
        prev = release.dist_settings if isinstance(release.dist_settings, dict) else {}
        merged = dict(prev)
        merged.update(dist_patch)
        release.dist_settings = merged

        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            if allowed_file(cover_file.filename, current_app.config['ALLOWED_COVER_EXTENSIONS']):
                if release.cover:
                    delete_file(release.cover, 'covers')
                filename = save_file(cover_file, 'covers')
                if filename:
                    release.cover = filename
            else:
                flash('Недопустимый формат обложки', 'error')

        if not release.title or not release.artists or not release.genre:
            flash('Название, артист и жанр обязательны', 'error')
            return redirect(url_for('releases.edit', id=id))

        db.session.commit()
        flash('Релиз обновлён', 'success')
        return redirect(url_for('releases.view', id=id))

    tracks = release.tracks.order_by(Track.track_order).all()
    ctx = _create_page_context(default_artists=release.artists)
    delivery_rows = _delivery_rows_for_release(release)
    release_events = get_release_events(release.id)
    selected_platform_ids = set(release.platforms or [])
    return render_template(
        'releases/edit.html',
        release=release,
        tracks=tracks,
        delivery_rows=delivery_rows,
        release_events=release_events,
        selected_platform_ids=selected_platform_ids,
        **ctx,
    )


@releases_bp.route('/releases/<int:id>/submit', methods=['POST'])
@login_required
def submit(id):
    """Отправка релиза на модерацию"""
    release = Release.query.get_or_404(id)

    if user_releases_restricted(current_user):
        flash(releases_restriction_flash_message(current_user), 'error')
        return redirect(url_for('releases.view', id=id))

    # Проверка доступа
    if release.user_id != current_user.id and not current_user.is_admin:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('releases.index'))
    
    # Проверка возможности отправки
    if not release.can_submit():
        if not release.cover:
            flash('Добавьте обложку релиза', 'error')
        elif release.tracks_count == 0:
            flash('Добавьте хотя бы один трек', 'error')
        else:
            flash('Этот релиз нельзя отправить на модерацию', 'error')
        return redirect(url_for('releases.view', id=id))

    confirm_no_drugs = request.form.get('confirm_no_drugs') == 'on'
    if not confirm_no_drugs:
        flash('Отметьте подтверждение об отсутствии пропаганды наркотических средств', 'error')
        return redirect(url_for('releases.view', id=id))

    if not release.platform_names_ordered():
        flash('Выберите хотя бы одну площадку в «Редактировать» → Дистрибуция', 'error')
        return redirect(url_for('releases.edit', id=id))

    files = request.files.getlist('release_documents')
    allowed_docs = current_app.config.get('ALLOWED_DOC_CONFIRM_EXTENSIONS', {'pdf'})
    max_doc_size = current_app.config.get('MAX_DOC_CONFIRM_SIZE', 15 * 1024 * 1024)
    docs_subfolder = f'release_docs/{release.id}'
    saved_docs = 0

    for file in files:
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename, allowed_docs):
            flash('Подтверждающие документы: разрешены только PDF-файлы', 'error')
            return redirect(url_for('releases.view', id=id))

        file.stream.seek(0, os.SEEK_END)
        file_size = file.stream.tell()
        file.stream.seek(0)
        if file_size > max_doc_size:
            max_mb = max_doc_size // (1024 * 1024)
            flash(f'Файл подтверждающего документа слишком большой (максимум {max_mb} МБ)', 'error')
            return redirect(url_for('releases.view', id=id))

        saved_filename = save_file(file, docs_subfolder)
        if not saved_filename:
            flash('Не удалось сохранить один из подтверждающих документов', 'error')
            return redirect(url_for('releases.view', id=id))
        saved_docs += 1
    
    release.status = 'moderation'
    release.moderator_comment = None
    log_release_event(release, 'submitted', actor=current_user, commit=False)
    db.session.commit()

    try:
        db.session.add(
            Notification(
                user_id=release.user_id,
                kind='release_submitted',
                title='Релиз отправлен на модерацию',
                message=f'«{release.title}» передан на проверку.',
                release_id=release.id,
            )
        )
        db.session.commit()
    except Exception as e:
        current_app.logger.warning('in-app notification release_submitted: %s', e)

    try:
        ok = send_release_submitted_email(release)
        if not ok:
            flash('Релиз отправлен на модерацию. Уведомление на почту не отправлено — проверьте email в профиле и настройки SMTP в .env', 'warning')
    except Exception as e:
        current_app.logger.warning('Ошибка отправки уведомления о модерации: %s', e)
        flash('Релиз отправлен на модерацию. Не удалось отправить письмо на почту — проверьте настройки SMTP.', 'warning')

    if saved_docs:
        flash(f'Загружено подтверждающих документов: {saved_docs}', 'success')
    flash('Релиз отправлен на модерацию', 'success')
    return redirect(url_for('releases.view', id=id))


@releases_bp.route('/releases/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Запрос на удаление релиза"""
    release = Release.query.get_or_404(id)
    
    # Проверка доступа
    if release.user_id != current_user.id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('releases.index'))
    
    # Проверка возможности удаления
    if not release.can_delete():
        flash('Этот релиз нельзя удалить', 'error')
        return redirect(url_for('releases.view', id=id))
    
    if release.status == 'draft':
        # Мягкое удаление — релиз остаётся в разделе «Удалены»
        release.status = 'deleted'
        log_release_event(release, 'deletion_confirmed', actor=current_user, commit=False)
        db.session.commit()
        flash('Черновик перемещён в «Удалены»', 'success')
        return redirect(url_for('releases.index', status='deleted'))
    else:
        # Отправка запроса на удаление
        release.status = 'deletion'
        log_release_event(release, 'deletion_requested', actor=current_user, commit=False)
        db.session.commit()
        
        flash('Запрос на удаление отправлен', 'info')
        return redirect(url_for('releases.view', id=id))


@releases_bp.route('/releases/<int:release_id>/tracks/add', methods=['POST'])
@login_required
def add_track(release_id):
    """Добавление трека"""
    release = Release.query.get_or_404(release_id)
    
    # Проверка доступа
    if release.user_id != current_user.id:
        return jsonify({'error': 'Доступ запрещён'}), 403
    
    if not release.can_edit():
        return jsonify({'error': 'Релиз нельзя редактировать'}), 400
    
    # Получение данных
    title = request.form.get('title', '').strip()
    artists = request.form.get('artists', '').strip()
    wav_file = request.files.get('wav_file')
    
    if not title or not artists:
        return jsonify({'error': 'Название и артисты обязательны'}), 400
    
    if not wav_file or not wav_file.filename:
        return jsonify({'error': 'WAV файл обязателен'}), 400
    
    if not allowed_file(wav_file.filename, current_app.config['ALLOWED_TRACK_EXTENSIONS']):
        return jsonify({'error': 'Разрешены только WAV файлы'}), 400
    
    # Сохранение файла
    filename = save_file(wav_file, 'tracks')
    if not filename:
        return jsonify({'error': 'Ошибка загрузки файла'}), 500
    
    # Определение порядка
    max_order = db.session.query(db.func.max(Track.track_order)).filter_by(
        release_id=release_id
    ).scalar() or 0
    
    # Создание трека
    track = Track(
        release_id=release_id,
        wav_file=filename,
        title=title,
        version=request.form.get('version', '').strip() or None,
        artists=artists,
        composers=request.form.get('composers', '').strip() or None,
        authors=request.form.get('authors', '').strip() or None,
        explicit=request.form.get('explicit') == 'on',
        language=request.form.get('language', '').strip() or None,
        isrc=normalize_isrc(request.form.get('isrc', '')),
        lyrics=request.form.get('lyrics', '').strip() or None,
        track_order=max_order + 1
    )
    
    db.session.add(track)
    db.session.commit()
    
    flash('Трек добавлен', 'success')
    return redirect(url_for('releases.edit', id=release_id))


@releases_bp.route('/releases/<int:release_id>/tracks/<int:track_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_track(release_id, track_id):
    """Редактирование трека (отдельная страница + сохранение)"""
    release = Release.query.get_or_404(release_id)
    track = Track.query.get_or_404(track_id)
    
    # Проверка доступа
    if release.user_id != current_user.id or track.release_id != release_id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('releases.edit', id=release_id))
    
    if not release.can_edit():
        flash('Релиз нельзя редактировать', 'error')
        return redirect(url_for('releases.edit', id=release_id))

    if request.method == 'GET':
        return render_template('releases/edit_track.html', release=release, track=track)
    
    # Обновление данных
    track.title = request.form.get('title', '').strip()
    track.version = request.form.get('version', '').strip() or None
    track.artists = request.form.get('artists', '').strip()
    track.composers = request.form.get('composers', '').strip() or None
    track.authors = request.form.get('authors', '').strip() or None
    track.explicit = request.form.get('explicit') == 'on'
    track.language = request.form.get('language', '').strip() or None
    track.isrc = normalize_isrc(request.form.get('isrc', ''))
    track.lyrics = request.form.get('lyrics', '').strip() or None
    
    # Обновление WAV файла
    wav_file = request.files.get('wav_file')
    if wav_file and wav_file.filename:
        if allowed_file(wav_file.filename, current_app.config['ALLOWED_TRACK_EXTENSIONS']):
            # Удаление старого файла
            if track.wav_file:
                delete_file(track.wav_file, 'tracks')
            
            filename = save_file(wav_file, 'tracks')
            if filename:
                track.wav_file = filename
        else:
            flash('Разрешены только WAV файлы', 'error')
            return redirect(url_for('releases.edit_track', release_id=release_id, track_id=track_id))
    
    db.session.commit()
    flash('Трек обновлён', 'success')
    return redirect(url_for('releases.edit', id=release_id))


@releases_bp.route('/releases/<int:release_id>/tracks/<int:track_id>/delete', methods=['POST'])
@login_required
def delete_track(release_id, track_id):
    """Удаление трека"""
    release = Release.query.get_or_404(release_id)
    track = Track.query.get_or_404(track_id)
    
    # Проверка доступа
    if release.user_id != current_user.id or track.release_id != release_id:
        flash('Доступ запрещён', 'error')
        return redirect(url_for('releases.edit', id=release_id))
    
    if not release.can_edit():
        flash('Релиз нельзя редактировать', 'error')
        return redirect(url_for('releases.edit', id=release_id))
    
    # Удаление файла
    if track.wav_file:
        delete_file(track.wav_file, 'tracks')
    
    db.session.delete(track)
    db.session.commit()
    
    flash('Трек удалён', 'success')
    return redirect(url_for('releases.edit', id=release_id))


@releases_bp.route('/releases/export')
@login_required
def export():
    """Экспорт каталога в CSV"""
    releases = Release.query.filter_by(user_id=current_user.id).order_by(Release.created_at.desc()).all()
    
    # Создание CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Заголовки
    writer.writerow([
        'ID', 'Название', 'Артисты', 'Тип', 'Жанр', 'Дата релиза',
        'Статус', 'UPC', 'Копирайт', 'Дата создания', 'Кол-во треков'
    ])
    
    # Данные
    for release in releases:
        writer.writerow([
            release.id,
            release.title,
            release.artists,
            release.type,
            release.genre,
            release.release_date.strftime('%d.%m.%Y'),
            release.status_display,
            release.upc or '',
            release.copyright or '',
            release.created_at.strftime('%d.%m.%Y'),
            release.tracks_count
        ])
    
    output.seek(0)
    
    # Отправка файла
    from io import BytesIO
    bytes_output = BytesIO()
    bytes_output.write(output.getvalue().encode('utf-8-sig'))
    bytes_output.seek(0)
    
    return send_file(
        bytes_output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'releases_{datetime.now().strftime("%Y%m%d")}.csv'
    )


@releases_bp.route('/uploads/covers/<filename>')
@login_required
def serve_cover(filename):
    """Отдача файла обложки (только владелец релиза или админ)"""
    release = Release.query.filter_by(cover=filename).first()
    if not release or (release.user_id != current_user.id and not current_user.is_admin):
        abort(404)
    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', 'covers')
    path = os.path.join(upload_folder, filename)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path)


@releases_bp.route('/uploads/tracks/<filename>')
@login_required
def serve_track(filename):
    """Отдача файла трека: ?play=1 — для встроенного плеера; иначе — скачивание."""
    track = Track.query.filter_by(wav_file=filename).first()
    if not track:
        abort(404)
    release = track.release
    if release.user_id != current_user.id and not current_user.is_admin:
        abort(404)
    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', 'tracks')
    path = os.path.join(upload_folder, filename)
    if not os.path.isfile(path):
        abort(404)
    want_play = request.args.get('play') in ('1', 'true', 'yes')
    if want_play:
        return send_file(path, mimetype='audio/wav', conditional=True, max_age=3600)
    dl_name = secure_filename(f'{track.display_title}.wav')
    if not dl_name or dl_name == '.wav':
        dl_name = filename
    return send_file(path, as_attachment=True, download_name=dl_name)


@releases_bp.route('/releases/<int:id>/documents/<filename>')
@login_required
def download_release_document(id, filename):
    """Скачивание подтверждающего документа релиза (владелец или админ)."""
    release = Release.query.get_or_404(id)
    if release.user_id != current_user.id and not current_user.is_admin:
        abort(404)

    safe_name = os.path.basename(filename)
    if safe_name != filename:
        abort(404)

    file_path = os.path.join(_release_docs_dir(release.id), safe_name)
    if not os.path.isfile(file_path):
        abort(404)
    return send_file(file_path, as_attachment=True, download_name=safe_name)