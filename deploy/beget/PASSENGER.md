# Запуск Flask на Beget (Passenger)

## Ошибка «нет файла …/venv/bin/python»

Виртуальное окружение с **Windows** на Linux не переносится. Его нужно **создать на сервере** по SSH (или временно использовать системный `python3` и поставить пакеты вручную).

### Вариант A (рекомендуется): venv на сервере

Подключитесь по SSH к хостингу, затем:

```bash
cd ~/public_html
# Если ensurepip недоступен на Beget — ставьте зависимости в user site:
python3 -m pip install --user -r requirements.txt
# Либо (если доступен python3-venv):
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

Узнайте полный путь к `python` в venv:

```bash
readlink -f venv/bin/python
```

В файле **`public_html/.htaccess`** в корне сайта укажите эту строку (замените путь на свой, если отличается):

```apache
PassengerPython /home/s/suppoyyo/toolls-muisic-distribution.ru/public_html/venv/bin/python
```

Закомментируйте или удалите строку с `PassengerPython /usr/bin/python3`.

Перезапуск приложения: в панели Beget «Перезапуск сайта» / касание `tmp/restart.txt` (если доступно).

### Вариант B: без venv

В `.htaccess` оставьте `PassengerPython /usr/bin/python3` и установите зависимости для пользователя:

```bash
pip3 install --user -r requirements.txt
```

Убедитесь, что `python3` видит пакеты (иногда нужен `export PYTHONPATH=...` — лучше всё же venv).

### Проверка

```bash
cd ~/public_html
python3 -c "from app import create_app; create_app(); print('OK')"
```

(Для venv: `./venv/bin/python -c "..."`.)
