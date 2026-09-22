"""
Отправка SMS через SMS Aero API
Документация: https://smsaero.ru/integration/documentation/api/
"""

import base64
import json
import logging
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

logger = logging.getLogger(__name__)

SMSAERO_URL = 'https://gate.smsaero.ru/v2/sms/send'


def _normalize_phone(phone):
    """Привести номер к формату 79XXXXXXXXX (РФ)."""
    if not phone:
        return None
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 10 and digits.startswith('9'):
        return '7' + digits
    if len(digits) == 11 and digits.startswith('7'):
        return digits
    if len(digits) == 11 and digits.startswith('8'):
        return '7' + digits[1:]
    if len(digits) == 10 and digits.startswith('8'):
        return '7' + digits[1:]
    return None


def send_login_code_sms(phone, code):
    """
    Отправить SMS с кодом авторизации через SMS Aero.
    phone — номер телефона (любой формат), code — 5-значный код.
    Возвращает (True, None) при успехе или (False, сообщение_об_ошибке).
    """
    email = (current_app.config.get('SMSAERO_EMAIL') or '').strip()
    api_key = (current_app.config.get('SMSAERO_API_KEY') or '').strip()
    sign = (current_app.config.get('SMSAERO_SIGN') or 'общее').strip()

    if not email or not api_key:
        logger.warning('SMS Aero не настроен: SMSAERO_EMAIL и SMSAERO_API_KEY должны быть в .env')
        return False, 'SMS не настроен: проверьте SMSAERO_EMAIL и SMSAERO_API_KEY в .env'

    normalized = _normalize_phone(phone)
    if not normalized:
        logger.warning('Некорректный формат телефона: %s', phone)
        return False, 'Некорректный формат номера телефона'

    text = (
        f'Здравствуйте, ваш код для авторизации в личный кабинет '
        f'Toolls Music Distribution: {code}'
    )

    def _parse_response(raw):
        """Парсинг ответа API и проверка успеха."""
        data = json.loads(raw)
        if current_app.debug:
            logger.info('SMS Aero ответ (отладка): %s', raw[:500])
        if data.get('success') is True or data.get('data', {}).get('id'):
            return True, None
        err = data.get('message', data.get('error', 'Неизвестная ошибка SMS Aero'))
        return False, str(err)

    credentials = base64.b64encode(f'{email}:{api_key}'.encode()).decode()

    # SSL: на shared-хостинге часто ошибка CERTIFICATE_VERIFY_FAILED
    ssl_verify = current_app.config.get('SMSAERO_SSL_VERIFY', True)
    if ssl_verify:
        ssl_ctx = None
    else:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        if current_app.debug:
            logger.warning('SMS Aero: проверка SSL отключена (SMSAERO_SSL_VERIFY=false)')

    def _send_request(use_sign):
        """Отправить запрос с указанной подписью."""
        body = {
            'number': normalized,  # строка 79XXXXXXXXX — некоторые среды API ожидают string
            'text': text,
            'sign': use_sign,
        }
        body_json = json.dumps(body, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            SMSAERO_URL,
            data=body_json,
            method='POST',
            headers={
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/json; charset=utf-8',
            }
        )
        with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
            return resp.read().decode()

    # Вариант 1: POST с JSON
    try:
        raw = _send_request(sign)
        ok, err = _parse_response(raw)
        if ok:
            logger.info('SMS с кодом входа отправлено на %s', normalized)
            return True, None
        # При "Validation error" часто виновата подпись: пробуем стандартную "SMS Aero"
        if err and 'validation' in str(err).lower() and sign != 'SMS Aero':
            logger.warning('SMS Aero Validation error с подписью "%s", пробуем SMS Aero', sign)
            raw2 = _send_request('SMS Aero')
            ok2, _ = _parse_response(raw2)
            if ok2:
                logger.info('SMS отправлено с подписью SMS Aero (подпись "%s" не прошла)', sign)
                return True, None
        logger.warning('SMS Aero ошибка: %s (ответ: %s)', err, raw[:400])
        return False, err

    except urllib.error.HTTPError as e:
        if e.code in (405, 501):
            # Метод POST не поддерживается — пробуем GET
            try:
                params = urllib.parse.urlencode({
                    'number': int(normalized),
                    'text': text,
                    'sign': sign,
                })
                url = f'{SMSAERO_URL}?{params}'
                req = urllib.request.Request(url, method='GET', headers={'Authorization': f'Basic {credentials}'})
                with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
                    raw = resp.read().decode()
                    ok, err = _parse_response(raw)
                    if ok:
                        logger.info('SMS с кодом входа отправлено на %s (GET)', normalized)
                        return True, None
                    return False, err
            except Exception:
                pass
        body = ''
        try:
            body = e.read().decode()
        except Exception:
            pass
        err_msg = f'HTTP {e.code}'
        try:
            data = json.loads(body) if body else {}
            err_msg = data.get('message', data.get('error', err_msg))
        except Exception:
            if body:
                err_msg = body[:200]
        logger.exception('SMS Aero HTTP ошибка: %s, тело: %s', err_msg, body[:300])
        return False, err_msg
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.exception('SMS Aero: неверный ответ API: %s', e)
        return False, str(e)
    except urllib.error.URLError as e:
        logger.exception('SMS Aero: ошибка сети: %s', e)
        return False, str(e)
    except Exception as e:
        logger.exception('SMS Aero: %s', e)
        return False, str(e)
