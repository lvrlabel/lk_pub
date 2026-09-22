#!/usr/bin/env python3
"""Генерация скриншотов для инструкции «Личный кабинет» (UI-макеты в стиле кабинета)."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'app' / 'static' / 'img' / 'knowledge'

W, H = 1280, 720
SIDEBAR = 248

C = {
    'sidebar': '#0f172a',
    'sidebar_text': '#cbd5e1',
    'sidebar_active': '#14b8a6',
    'bg': '#f1f5f9',
    'card': '#ffffff',
    'border': '#e2e8f0',
    'text': '#0f172a',
    'muted': '#64748b',
    'primary': '#14b8a6',
    'primary_soft': '#ccfbf1',
    'orange': '#ea580c',
    'green': '#059669',
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        ('C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',),
        ('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf',),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',),
    ]
    for path in candidates:
        p = path[0]
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _base(active: str = 'Обзор') -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new('RGB', (W, H), C['bg'])
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, SIDEBAR, H], fill=C['sidebar'])
    d.rectangle([SIDEBAR, 0, W, 56], fill=C['card'])
    d.line([SIDEBAR, 56, W, 56], fill=C['border'], width=1)
    d.line([SIDEBAR, 0, SIDEBAR, H], fill='#1e293b', width=1)

    logo = _font(15, True)
    d.text((20, 18), 'Toolls', fill='#ffffff', font=logo)
    d.text((20, 36), 'Publishing', fill=C['sidebar_text'], font=_font(11))

    items = [
        'Новый релиз',
        'Обзор',
        'Релизы',
        'Аналитика',
        'Финансы',
        'Смарт-ссылки',
        'Новости',
        'Поддержка',
        'Ещё',
    ]
    y = 88
    for label in items:
        is_active = label == active or (active == 'Релизы' and label == 'Релизы')
        if label == 'Новый релиз':
            d.rounded_rectangle([16, y, SIDEBAR - 16, y + 34], radius=8, fill=C['primary'])
            d.text((36, y + 8), label, fill='#ffffff', font=_font(12, True))
            y += 46
            continue
        if is_active:
            d.rounded_rectangle([12, y - 2, SIDEBAR - 12, y + 28], radius=6, fill='#1e293b')
            d.rectangle([12, y + 4, 15, y + 22], fill=C['sidebar_active'])
        d.text((28, y + 4), label, fill='#ffffff' if is_active else C['sidebar_text'], font=_font(12, is_active))
        y += 34

    return img, d


def _title(d: ImageDraw.ImageDraw, text: str, subtitle: str | None = None) -> int:
    d.text((SIDEBAR + 28, 16), text, fill=C['text'], font=_font(18, True))
    if subtitle:
        d.text((SIDEBAR + 28, 38), subtitle, fill=C['muted'], font=_font(12))
    return 72


def _card(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, title: str | None = None) -> tuple[int, int, int, int]:
    d.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=C['card'], outline=C['border'], width=1)
    if title:
        d.text((x + 16, y + 14), title, fill=C['text'], font=_font(13, True))
    return x, y, w, h


def _btn(d: ImageDraw.ImageDraw, x: int, y: int, label: str, primary: bool = False) -> None:
    w = 8 * len(label) + 36
    bg = C['primary'] if primary else C['card']
    fg = '#ffffff' if primary else C['text']
    d.rounded_rectangle([x, y, x + w, y + 32], radius=8, fill=bg, outline=C['border'] if not primary else C['primary'])
    d.text((x + 14, y + 8), label, fill=fg, font=_font(11, primary))


def shot_login() -> None:
    img = Image.new('RGB', (W, H), '#eef2ff')
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([360, 120, 920, 600], radius=16, fill=C['card'], outline=C['border'], width=1)
    d.text((430, 170), 'Toolls Music Distribution', fill=C['text'], font=_font(22, True))
    d.text((430, 205), 'Вход в личный кабинет', fill=C['muted'], font=_font(13))
    d.text((430, 270), 'Email', fill=C['muted'], font=_font(11))
    d.rounded_rectangle([430, 288, 850, 328], radius=8, outline=C['border'], width=1, fill='#f8fafc')
    d.text((442, 300), 'artist@example.com', fill=C['text'], font=_font(12))
    d.text((430, 350), 'Пароль', fill=C['muted'], font=_font(11))
    d.rounded_rectangle([430, 368, 850, 408], radius=8, outline=C['border'], width=1, fill='#f8fafc')
    d.text((442, 380), '••••••••', fill=C['text'], font=_font(12))
    d.rounded_rectangle([430, 440, 850, 484], radius=8, fill=C['primary'])
    d.text((610, 454), 'Войти', fill='#ffffff', font=_font(13, True))
    img.save(OUT / 'cabinet-01.png', optimize=True)


def shot_dashboard() -> None:
    img, d = _base('Обзор')
    _title(d, 'Обзор', 'Привет, Artist Name')
    y = 84
    for i, (label, val, color) in enumerate([
        ('Всего релизов', '12', C['text']),
        ('Одобрено', '8', C['green']),
        ('На модерации', '2', C['orange']),
        ('Черновики', '2', C['muted']),
    ]):
        x = SIDEBAR + 28 + (i % 2) * 390
        yy = y + (i // 2) * 110
        _card(d, x, yy, 360, 90)
        d.text((x + 16, yy + 16), label, fill=C['muted'], font=_font(11))
        d.text((x + 16, yy + 42), val, fill=color, font=_font(26, True))
    _card(d, SIDEBAR + 28, 320, 780, 150, 'Последняя новость')
    d.text((SIDEBAR + 44, 370), 'Обновление сервиса: новые функции кабинета', fill=C['text'], font=_font(12))
    d.text((SIDEBAR + 44, 392), '03.07.2026', fill=C['muted'], font=_font(11))
    img.save(OUT / 'cabinet-02.png', optimize=True)


def shot_new_release_btn() -> None:
    img, d = _base('Релизы')
    _title(d, 'Релизы', 'Все ваши релизы')
    _btn(d, SIDEBAR + 28, 84, 'Новый релиз', primary=True)
    d.rounded_rectangle([SIDEBAR + 170, 84, SIDEBAR + 420, 116], radius=8, outline=C['border'], fill=C['card'])
    d.text((SIDEBAR + 186, 94), 'Поиск по названию…', fill=C['muted'], font=_font(11))
    img.save(OUT / 'cabinet-03.png', optimize=True)


def shot_cover_upload() -> None:
    img, d = _base('Релизы')
    _title(d, 'Новый релиз', 'Шаг 1 — обложка')
    _card(d, SIDEBAR + 28, 84, 320, 320, 'Обложка')
    d.rounded_rectangle([SIDEBAR + 60, 140, SIDEBAR + 316, 360], radius=10, outline=C['primary'], width=2, fill=C['primary_soft'])
    d.text((SIDEBAR + 92, 230), 'Перетащите файл', fill=C['primary'], font=_font(12, True))
    d.text((SIDEBAR + 86, 252), '3000×3000 JPG/PNG', fill=C['muted'], font=_font(10))
    img.save(OUT / 'cabinet-03.2.png', optimize=True)


def shot_release_form() -> None:
    img, d = _base('Релизы')
    _title(d, 'Новый релиз', 'Основные данные')
    _card(d, SIDEBAR + 28, 84, 780, 280, 'Данные релиза')
    fields = ['Название релиза', 'Артисты', 'Тип', 'Жанр', 'Дата релиза']
    y = 130
    for f in fields:
        d.text((SIDEBAR + 44, y), f, fill=C['muted'], font=_font(10))
        d.rounded_rectangle([SIDEBAR + 44, y + 14, SIDEBAR + 760, y + 42], radius=6, outline=C['border'], fill='#f8fafc')
        y += 52
    img.save(OUT / 'cabinet-03.3.png', optimize=True)


def shot_draft_save() -> None:
    img, d = _base('Релизы')
    _title(d, 'Новый релиз', 'Черновик')
    _btn(d, SIDEBAR + 28, 84, 'Сохранить черновик', primary=True)
    _btn(d, SIDEBAR + 210, 84, 'Отправить на модерацию')
    d.text((SIDEBAR + 28, 130), 'Статус: Черновик', fill=C['orange'], font=_font(12, True))
    img.save(OUT / 'cabinet-03.4.png', optimize=True)


def shot_tracks() -> None:
    img, d = _base('Релизы')
    _title(d, 'Новый релиз', 'Треки')
    _card(d, SIDEBAR + 28, 84, 780, 220, 'Треки')
    d.rounded_rectangle([SIDEBAR + 44, 130, SIDEBAR + 780, 170], radius=8, outline=C['border'], fill='#f8fafc')
    d.text((SIDEBAR + 56, 142), '01  Track Title.wav', fill=C['text'], font=_font(11))
    d.text((SIDEBAR + 56, 188), '+ Добавить трек (WAV)', fill=C['primary'], font=_font(11, True))
    img.save(OUT / 'cabinet-03.5.png', optimize=True)


def shot_moderation() -> None:
    img, d = _base('Релизы')
    _title(d, 'Новый релиз', 'Отправка')
    _btn(d, SIDEBAR + 28, 84, 'Отправить на модерацию', primary=True)
    d.text((SIDEBAR + 28, 130), 'После отправки релиз попадёт на проверку (до 72 часов).', fill=C['muted'], font=_font(11))
    img.save(OUT / 'cabinet-03.6.png', optimize=True)


def shot_releases() -> None:
    img, d = _base('Релизы')
    _title(d, 'Релизы', 'Фильтры и статусы')
    statuses = [('Single Title', 'Одобрено', C['green']), ('EP Name', 'На модерации', C['orange']), ('Draft', 'Черновик', C['muted'])]
    y = 84
    for title, status, color in statuses:
        _card(d, SIDEBAR + 28, y, 780, 72)
        d.text((SIDEBAR + 44, y + 16), title, fill=C['text'], font=_font(13, True))
        d.text((SIDEBAR + 44, y + 40), 'Artist Name', fill=C['muted'], font=_font(11))
        d.rounded_rectangle([SIDEBAR + 660, y + 22, SIDEBAR + 780, y + 50], radius=999, fill='#f1f5f9')
        d.text((SIDEBAR + 682, y + 30), status, fill=color, font=_font(10, True))
        y += 84
    img.save(OUT / 'cabinet-04.png', optimize=True)


def shot_analytics() -> None:
    img, d = _base('Аналитика')
    _title(d, 'Сводная информация', 'Single Title · Artist Name')
    metrics = [('Стримы', '48 320'), ('Скачивания', '1 204'), ('Доход', '12 450.00 ₽')]
    x = SIDEBAR + 28
    for label, val in metrics:
        _card(d, x, 84, 180, 72)
        d.text((x + 14, 98), label, fill=C['muted'], font=_font(10))
        d.text((x + 14, 118), val, fill=C['text'], font=_font(14, True))
        x += 196
    _card(d, SIDEBAR + 28, 176, 780, 280, 'Прослушивания')
    tabs = ['Стримы', 'Скачивания', 'Доход', 'Все вместе']
    tx = SIDEBAR + 44
    for i, t in enumerate(tabs):
        bg = C['primary'] if i == 3 else C['card']
        fg = '#fff' if i == 3 else C['text']
        d.rounded_rectangle([tx, 220, tx + 88, 248], radius=6, fill=bg, outline=C['border'])
        d.text((tx + 10, 228), t, fill=fg, font=_font(9, i == 3))
        tx += 96
    for i in range(8):
        h = 40 + i * 18
        d.rectangle([SIDEBAR + 70 + i * 80, 320 - h, SIDEBAR + 130 + i * 80, 320], fill=C['primary_soft'], outline=C['primary'])
    img.save(OUT / 'cabinet-05.png', optimize=True)


def shot_finance() -> None:
    img, d = _base('Финансы')
    _title(d, 'Финансы', 'Баланс и отчёты')
    _card(d, SIDEBAR + 28, 84, 780, 120, 'Ваш баланс')
    d.text((SIDEBAR + 44, 130), '24 580.00 ₽', fill=C['text'], font=_font(28, True))
    _card(d, SIDEBAR + 28, 220, 240, 120)
    d.text((SIDEBAR + 44, 240), 'Q1', fill=C['muted'], font=_font(11))
    d.text((SIDEBAR + 44, 262), '8 120.00 ₽', fill=C['text'], font=_font(16, True))
    img.save(OUT / 'cabinet-06.png', optimize=True)


def shot_smart_links() -> None:
    img, d = _base('Смарт-ссылки')
    _title(d, 'Смарт-ссылки', 'Единая ссылка на все площадки')
    _card(d, SIDEBAR + 28, 84, 780, 160, 'Новая смарт-ссылка')
    d.text((SIDEBAR + 44, 130), 'lvr.link/abc123', fill=C['primary'], font=_font(14, True))
    d.text((SIDEBAR + 44, 158), 'Spotify · Apple Music · Яндекс · VK', fill=C['muted'], font=_font(11))
    img.save(OUT / 'cabinet-07.png', optimize=True)


def shot_news() -> None:
    img, d = _base('Новости')
    _title(d, 'Новости', 'Анонсы Toolls Music Distribution')
    _card(d, SIDEBAR + 28, 84, 780, 90)
    d.text((SIDEBAR + 44, 104), 'Новый сезон релизов', fill=C['text'], font=_font(13, True))
    d.text((SIDEBAR + 44, 128), '01.07.2026', fill=C['muted'], font=_font(10))
    img.save(OUT / 'cabinet-08.png', optimize=True)


def shot_service_updates() -> None:
    img, d = _base('Ещё')
    _title(d, 'Обновление сервиса', 'Важные правки и новые функции')
    _card(d, SIDEBAR + 28, 84, 780, 88)
    d.rectangle([SIDEBAR + 28, 84, SIDEBAR + 31, 172], fill=C['primary'])
    d.text((SIDEBAR + 48, 104), '03.07.2026  Аналитика: переключение графиков', fill=C['text'], font=_font(12, True))
    d.text((SIDEBAR + 48, 128), 'Заработали переключатели метрик и типов графика…', fill=C['muted'], font=_font(10))
    _card(d, SIDEBAR + 28, 184, 780, 72)
    d.text((SIDEBAR + 48, 204), '02.07.2026  События у релиза на модерации', fill=C['text'], font=_font(11))
    img.save(OUT / 'cabinet-11.png', optimize=True)


def shot_support() -> None:
    img, d = _base('Поддержка')
    _title(d, 'Поддержка', 'Тикеты и обращения')
    _btn(d, SIDEBAR + 28, 84, 'Новый тикет', primary=True)
    _card(d, SIDEBAR + 28, 132, 780, 72)
    d.text((SIDEBAR + 44, 152), '#1042 · Вопрос по выплате', fill=C['text'], font=_font(12, True))
    d.text((SIDEBAR + 44, 174), 'Открыт · 02.07.2026', fill=C['muted'], font=_font(10))
    img.save(OUT / 'cabinet-09.png', optimize=True)


def shot_profile() -> None:
    img, d = _base('Обзор')
    _title(d, 'Профиль', 'Данные аккаунта')
    _card(d, SIDEBAR + 28, 84, 780, 260, 'Личные данные')
    fields = [('Имя', 'Artist Name'), ('Email', 'artist@example.com'), ('Пароль', '••••••••')]
    y = 130
    for label, val in fields:
        d.text((SIDEBAR + 44, y), label, fill=C['muted'], font=_font(10))
        d.rounded_rectangle([SIDEBAR + 44, y + 14, SIDEBAR + 520, y + 42], radius=6, outline=C['border'], fill='#f8fafc')
        d.text((SIDEBAR + 56, y + 22), val, fill=C['text'], font=_font(11))
        y += 56
    _btn(d, SIDEBAR + 44, 330, 'Сохранить', primary=True)
    img.save(OUT / 'cabinet-10.png', optimize=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shots = [
        shot_login,
        shot_dashboard,
        shot_new_release_btn,
        shot_cover_upload,
        shot_release_form,
        shot_draft_save,
        shot_tracks,
        shot_moderation,
        shot_releases,
        shot_analytics,
        shot_finance,
        shot_smart_links,
        shot_news,
        shot_service_updates,
        shot_support,
        shot_profile,
    ]
    for fn in shots:
        fn()
        print('OK', fn.__name__)
    print('Saved to', OUT)


if __name__ == '__main__':
    main()
