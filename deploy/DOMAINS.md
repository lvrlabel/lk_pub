# Настройка доменов: toolls-muisic-distribution.ru

Вход в личный кабинет: **https://auth.toolls-muisic-distribution.ru** (страница логина).  
После входа пользователь попадает на **https://lk.toolls-muisic-distribution.ru** (приложение ЛК).

## Что сделано в коде

- Все URL в конфигурации переведены на домен **toolls-muisic-distribution.ru** и его поддомены:
  - `auth.toolls-muisic-distribution.ru` — вход в личный кабинет (страница логина)
  - `lk.toolls-muisic-distribution.ru` — личный кабинет (приложение после входа)
  - `lnk.toolls-muisic-distribution.ru` — смарт-ссылки (опционально)
- В конфиг добавлена переменная **APPLICATION_ROOT_URL** (по умолчанию `https://toolls-muisic-distribution.ru`) для единого домена в ссылках.
- В production включён **ProxyFix**: приложение доверяет заголовкам `X-Forwarded-Host`, `X-Forwarded-Proto` от обратного прокси, чтобы формировать правильные абсолютные ссылки (в письмах, редиректах).

## Что нужно сделать на хостинге

### 1. Кнопка «Войти» на лендинге

На основном сайте **toolls-muisic-distribution.ru** кнопка «Войти» должна вести на:

- **https://auth.toolls-muisic-distribution.ru** (или **https://auth.toolls-muisic-distribution.ru/login**)

Измените ссылку в шаблоне/редакторе лендинга.

### 2. Настройка поддоменов на хостинге

- **auth.toolls-muisic-distribution.ru** — укажите корневую папку приложения. Здесь открывается страница входа.
- **lk.toolls-muisic-distribution.ru** — та же корневая папка приложения. После входа пользователь попадает сюда. Смарт-ссылки тоже работают на этом домене: `https://lk.toolls-muisic-distribution.ru/link/КОД`.

Оба поддомена могут указывать на один и тот же каталог с приложением; различие только в том, с какого URL пользователь заходит (auth — для входа, lk — для работы в ЛК).

**Опционально**: поддомен **lnk.toolls-muisic-distribution.ru** — если хотите короткие ссылки вида `lnk.toolls-muisic-distribution.ru/link/КОД`, создайте DNS A‑запись для lnk и настройте виртуальный хост, указывающий на тот же каталог приложения. Затем в `.env` задайте `SMART_LINK_BASE_URL=https://lnk.toolls-muisic-distribution.ru/link`.

### 3. Переменные окружения (.env)

На сервере приложения в `.env` заданы:

- `AUTH_SERVICE_URL=https://auth.toolls-muisic-distribution.ru`
- `AUTH_CALLBACK_URL=https://lk.toolls-muisic-distribution.ru/auth/callback`
- `APPLICATION_ROOT_URL=https://toolls-muisic-distribution.ru` — основной домен в ссылках (по желанию).

После изменений перезапустите приложение.
