# Деплой конфигурации на Beget

> Этот файл — про Flask-проект (почта, `.env`, Passenger для Python).
> `index.php` / `.htaccess` / `README.txt` в этой же папке — отдельная памятка на будущее
> (PHP/Laravel), к текущему проекту отношения не имеет; трогать не стали, чтобы не сломать
> то, для чего оно готовилось.

Сервер: **suppoyyo.beget.tech**
SSH/SFTP-логин: **suppoyyo_loveyou** (порт 22)

Reg.ru больше не используется — папка `deploy/reg_ru/` удалена, весь проект переехал на Beget.

## Важно: passenger_wsgi.py в этом репозитории мог устареть

Корневой `passenger_wsgi.py` в этой копии проекта указывает на путь Python от **Reg.ru**
(`/var/www/u3616355/data/flaskenv/bin/python3.10`). Сайт при этом реально работает на Beget — то есть
на сервере файл, скорее всего, уже был вручную поправлен и разошёлся с локальной копией.

В `deploy/beget/PASSENGER.md` уже записан вероятный актуальный путь:

```
/home/s/suppoyyo/toolls-muisic-distribution.ru/public_html/venv/bin/python
```

Но чтобы не гадать и не сломать рабочий сайт, точный вариант (venv или системный `python3`)
стоит один раз проверить по SSH:

```bash
ssh suppoyyo_loveyou@suppoyyo.beget.tech
cat ~/toolls-muisic-distribution.ru/public_html/.htaccess   # какая строка PassengerPython сейчас
cat ~/toolls-muisic-distribution.ru/public_html/passenger_wsgi.py   # что реально используется
```

После этого можно привести локальный `passenger_wsgi.py` и `.htaccess` в соответствие с тем,
что реально на сервере, и уже не бояться перезаливать их скриптом.

## .htaccess

`PassengerEnabled on` — этого достаточно, если Passenger уже поднят на аккаунте (директивы
`PassengerPython`/`PassengerAppRoot` актуальны, только когда путь к интерпретатору не задан
глобально в панели — уточняйте у поддержки Beget, если после деплоя сайт не стартует).

## Автоматический деплой .env

```bash
pip install paramiko
python deploy/beget/apply_config.py
```

Что делает:
- загружает `.env` (без `BEGET_SSH_*` — деплойные секреты на хостинг не идут) в `public_html/.env`;
- создаёт `public_html/tmp/restart.txt`, чтобы Passenger перечитал переменные окружения.

Перед запуском добавьте в локальный `.env`:

```env
YOOKASSA_SHOP_ID=1467382
YOOKASSA_SECRET_KEY=ваш_секретный_ключ_ЮKassa
YOOKASSA_API_URL=https://api.yookassa.ru/v3
```

Если каталог сайта на сервере называется иначе — `python deploy/beget/apply_config.py --remote-dir <путь>`.

## Почта

- SMTP: `smtp.beget.com:465` (SSL)
- Логин: `noreply@toolls-music.ru`
- Проверка: `/admin/test-email` в личном кабинете

Письма по релизам, счетам, подпискам, тикетам и кодам входа используют этот же SMTP — отдельно
настраивать их не нужно, все уже подключены к событиям в коде (`app/routes/releases.py`,
`app/routes/moderation.py`, `app/routes/contracts.py`, `app/routes/documents.py`).
Просрочки счетов и напоминания о подписке уходят автоматически раз в сутки
(`app/services/billing_scheduler.py`, запускается при любом запросе к сайту — отдельный cron не нужен).

## Telegram

Бот: `@toolls_music_bot`. После деплоя `.env` с `TELEGRAM_BOT_TOKEN`/`TELEGRAM_WEBHOOK_SECRET` —
зайти в админку → «Telegram-новости» → **Set webhook**.
