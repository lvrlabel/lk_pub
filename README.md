# public_html
Личный кабинет Toolls Music Distribution, предназначенный для загрузки треков на модерацию, отслеживанием аналитики и прочее.

## ЮKassa: счета API

Для создания счетов из раздела «Финансы → Счета» задайте на сервере:

- `YOOKASSA_SHOP_ID` — идентификатор магазина `1467382`;
- `YOOKASSA_SECRET_KEY` — live_4f5_nSLuZ_YG482S3TfV24-NEyzk_lCkLvWQOI3sq0w.

В кабинете ЮKassa включите HTTP-уведомления для события `payment.succeeded` и укажите URL:
`https://lk.toolls-muisic-distribution.ru/documents/webhooks/yookassa`

После этого администратор вводит сумму и тему счёта, приложение создаёт счёт через API ЮKassa, сохраняет выданную ссылку, а webhook автоматически переводит локальный счёт в статус «Оплачен».