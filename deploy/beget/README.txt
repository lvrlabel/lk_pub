ДЕПЛОЙ НА BEGET.COM
===================

1. Загрузи весь проект на хостинг в папку public_html.
   Структура должна быть такой:
   
   public_html/
   ├── index.php      ← скопируй из deploy/beget/
   ├── .htaccess      ← скопируй из deploy/beget/
   └── php/
       ├── app/
       ├── bootstrap/
       ├── config/
       ├── public/
       ├── storage/
       ├── vendor/
       └── ... (остальные папки Laravel)

2. Скопируй эти 2 файла в КОРЕНЬ public_html:
   - deploy/beget/index.php  →  public_html/index.php
   - deploy/beget/.htaccess →  public_html/.htaccess

3. Готово! Сайт должен открываться без ошибки 403.
