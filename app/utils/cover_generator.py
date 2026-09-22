"""
Генератор обложек релизов (3000×3000, JPG/PNG) через Pillow.
Pillow импортируется лениво — чтобы сбой Pillow не ронял всё приложение при старте.
"""

import io
import os
import uuid
from pathlib import Path

from flask import current_app

COVER_SIZE = 3000
PREVIEW_SIZE = 800

STYLE_PRESETS = {
    'teal': {
        'label': 'Бирюзовый (Toolls)',
        'top': (20, 184, 166),
        'bottom': (15, 118, 110),
        'text': (255, 255, 255),
        'subtext': (204, 251, 241),
    },
    'purple': {
        'label': 'Фиолетовый',
        'top': (102, 126, 234),
        'bottom': (118, 75, 162),
        'text': (255, 255, 255),
        'subtext': (237, 233, 254),
    },
    'dark': {
        'label': 'Тёмный',
        'top': (30, 41, 59),
        'bottom': (15, 23, 42),
        'text': (248, 250, 252),
        'subtext': (148, 163, 184),
    },
    'sunset': {
        'label': 'Закат',
        'top': (251, 113, 133),
        'bottom': (124, 58, 237),
        'text': (255, 255, 255),
        'subtext': (254, 226, 226),
    },
    'minimal': {
        'label': 'Светлый минимализм',
        'top': (248, 250, 252),
        'bottom': (226, 232, 240),
        'text': (15, 23, 42),
        'subtext': (71, 85, 105),
    },
    'vinyl': {
        'label': 'Винил',
        'top': (23, 23, 23),
        'bottom': (10, 10, 10),
        'text': (250, 250, 250),
        'subtext': (163, 163, 163),
        'vinyl': True,
    },
}

_PIL_MODULES = None
_PILLOW_AVAILABLE = None
PILLOW_ERROR_HINT = (
    'На сервере не работает Pillow (Python 3.13). '
    'В venv выполните: pip install --force-reinstall --no-cache-dir Pillow'
)


def pillow_available():
    """Проверка Pillow без падения приложения при импорте модуля."""
    global _PILLOW_AVAILABLE
    if _PILLOW_AVAILABLE is None:
        try:
            from PIL import Image as _Image  # noqa: F401

            _PILLOW_AVAILABLE = True
        except ImportError:
            _PILLOW_AVAILABLE = False
    return _PILLOW_AVAILABLE


def _pil():
    global _PIL_MODULES
    if _PIL_MODULES is None:
        try:
            from PIL import Image, ImageDraw, ImageFont

            _PIL_MODULES = (Image, ImageDraw, ImageFont)
        except ImportError as e:
            raise RuntimeError(PILLOW_ERROR_HINT) from e
    return _PIL_MODULES


def style_choices():
    return [{'id': k, 'label': v['label']} for k, v in STYLE_PRESETS.items()]


def _font_path(bold=False):
    import PIL

    root = Path(PIL.__file__).parent
    name = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    path = root / name
    if path.is_file():
        return str(path)
    alt = root / 'fonts' / name
    if alt.is_file():
        return str(alt)
    return None


def _load_font(size, bold=True):
    _, _, ImageFont = _pil()
    path = _font_path(bold=bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _vertical_gradient(size, top_rgb, bottom_rgb):
    Image, _, _ = _pil()
    w, h = size
    mask = Image.linear_gradient('L').rotate(90, expand=True).resize((w, h))
    top = Image.new('RGB', size, top_rgb)
    bottom = Image.new('RGB', size, bottom_rgb)
    return Image.composite(bottom, top, mask)


def _wrap_text(text, font, max_width, draw):
    words = (text or '').strip().split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f'{current} {word}'
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_centered_block(draw, lines, font, y_start, box_w, box_h, fill, line_gap=0.08):
    if not lines:
        return y_start
    heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        heights.append(bbox[3] - bbox[1])
    gap = int(heights[0] * line_gap) if heights else 0
    total_h = sum(heights) + gap * max(0, len(lines) - 1)
    y = y_start + max(0, (box_h - total_h) // 2)
    for i, line in enumerate(lines):
        tw = draw.textlength(line, font=font)
        x = (box_w - tw) // 2
        draw.text((x, y), line, font=font, fill=fill)
        y += heights[i] + (gap if i < len(lines) - 1 else 0)
    return y


def _paste_background(bg_image, size):
    Image, _, _ = _pil()
    img = bg_image.convert('RGB')
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    return img.resize(size, Image.Resampling.LANCZOS)


def generate_cover_image(title, artists, style_id='teal', bg_image=None, size=COVER_SIZE):
    """Собрать обложку; возвращает PIL.Image RGB."""
    Image, ImageDraw, _ = _pil()
    preset = STYLE_PRESETS.get(style_id) or STYLE_PRESETS['teal']
    title = (title or '').strip() or 'Название релиза'
    artists = (artists or '').strip() or 'Артист'

    if bg_image is not None:
        try:
            uploaded = Image.open(bg_image)
            base = _paste_background(uploaded, (size, size))
            overlay = Image.new('RGBA', (size, size), (0, 0, 0, 120))
            base = Image.alpha_composite(base.convert('RGBA'), overlay).convert('RGB')
        except Exception:
            base = _vertical_gradient((size, size), preset['top'], preset['bottom'])
    elif preset.get('vinyl'):
        base = _vertical_gradient((size, size), preset['top'], preset['bottom'])
        draw_v = ImageDraw.Draw(base)
        cx = cy = size // 2
        r_outer = int(size * 0.38)
        r_inner = int(size * 0.12)
        draw_v.ellipse(
            (cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer),
            fill=(40, 40, 40),
            outline=(60, 60, 60),
            width=max(2, size // 500),
        )
        draw_v.ellipse(
            (cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner),
            fill=(15, 15, 15),
        )
    else:
        base = _vertical_gradient((size, size), preset['top'], preset['bottom'])

    draw = ImageDraw.Draw(base)
    pad = int(size * 0.1)
    inner_w = size - pad * 2
    inner_h = size - pad * 2

    title_font = _load_font(max(48, int(size * 0.09)), bold=True)
    artist_font = _load_font(max(32, int(size * 0.055)), bold=False)

    title_lines = _wrap_text(title, title_font, inner_w, draw)
    artist_lines = _wrap_text(artists, artist_font, inner_w, draw)

    title_block_h = int(inner_h * 0.55)
    artist_block_h = inner_h - title_block_h

    _draw_centered_block(
        draw, title_lines, title_font, pad, size, title_block_h,
        preset['text'],
    )
    _draw_centered_block(
        draw, artist_lines, artist_font, pad + title_block_h, size, artist_block_h,
        preset['subtext'],
    )

    badge = 'TOOLLS'
    badge_font = _load_font(max(18, int(size * 0.022)), bold=True)
    bw = draw.textlength(badge, font=badge_font)
    bh = int(size * 0.035)
    bx = size - pad - int(bw) - int(size * 0.02)
    by = pad
    draw.rounded_rectangle(
        (bx - int(size * 0.015), by, bx + bw + int(size * 0.015), by + bh),
        radius=int(size * 0.008),
        fill=(60, 60, 60) if style_id in ('dark', 'vinyl') else (255, 255, 255),
        outline=preset['subtext'],
        width=max(1, size // 800),
    )
    draw.text((bx, by + int(bh * 0.12)), badge, font=badge_font, fill=preset['subtext'])

    return base


def render_cover_bytes(title, artists, style_id='teal', bg_image=None, size=COVER_SIZE, fmt='JPEG'):
    if not pillow_available():
        raise RuntimeError(PILLOW_ERROR_HINT)
    img = generate_cover_image(title, artists, style_id, bg_image, size=size)
    buf = io.BytesIO()
    if fmt.upper() == 'PNG':
        img.save(buf, format='PNG', optimize=True)
    else:
        img.save(buf, format='JPEG', quality=92, subsampling=0, optimize=True)
    return buf.getvalue()


def save_cover_bytes(data, subfolder='covers'):
    """Сохранить байты обложки в uploads; вернуть имя файла."""
    ext = 'jpg'
    unique_filename = f'{uuid.uuid4().hex}.{ext}'
    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', subfolder)
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, unique_filename)
    with open(file_path, 'wb') as f:
        f.write(data)
    return unique_filename
