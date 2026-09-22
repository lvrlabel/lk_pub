"""
Валидаторы
"""

import re


def validate_password(password):
    """
    Валидация пароля
    
    Требования:
    - Минимум 8 символов
    - Минимум одна заглавная буква
    - Минимум одна строчная буква
    - Минимум одна цифра
    - Минимум один спецсимвол
    
    Returns:
        Список ошибок (пустой список, если пароль валиден)
    """
    errors = []
    
    if len(password) < 8:
        errors.append('Пароль должен содержать минимум 8 символов')
    
    if not re.search(r'[A-Z]', password):
        errors.append('Пароль должен содержать минимум одну заглавную букву')
    
    if not re.search(r'[a-z]', password):
        errors.append('Пароль должен содержать минимум одну строчную букву')
    
    if not re.search(r'\d', password):
        errors.append('Пароль должен содержать минимум одну цифру')
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append('Пароль должен содержать минимум один спецсимвол (!@#$%^&*(),.?":{}|<>)')
    
    return errors


def validate_email(email):
    """
    Валидация email
    
    Returns:
        True если email валиден, False иначе
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_upc(upc):
    """
    Валидация UPC кода
    
    Returns:
        True если UPC валиден, False иначе
    """
    if not upc:
        return True  # UPC опционален
    
    # UPC должен содержать только цифры и быть длиной 12-14 символов
    if not upc.isdigit():
        return False
    
    if len(upc) < 12 or len(upc) > 14:
        return False
    
    return True


def normalize_isrc(value, max_length=128):
    """
    Подготовка ISRC (или внутреннего кода) к сохранению.
    Формат не проверяется — допустимы дефисы, пробелы, регистр как у партнёра.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = ' '.join(s.split())
    if len(s) > max_length:
        return s[:max_length]
    return s


def validate_isrc(isrc):
    """
    Мягкая проверка длины (для совместимости). Строгого формата CCXXXYYNNNNN нет.
    """
    if not isrc:
        return True
    return len(str(isrc).strip()) <= 128


def sanitize_filename(filename):
    """
    Очистка имени файла от опасных символов
    """
    # Удаляем путь
    filename = filename.split('/')[-1].split('\\')[-1]
    
    # Оставляем только безопасные символы
    safe_chars = re.sub(r'[^\w\s\-\.]', '', filename)
    
    # Заменяем пробелы на подчёркивания
    safe_chars = safe_chars.replace(' ', '_')
    
    return safe_chars


def validate_date_format(date_str, format='%Y-%m-%d'):
    """
    Валидация формата даты
    
    Returns:
        True если формат валиден, False иначе
    """
    from datetime import datetime
    
    try:
        datetime.strptime(date_str, format)
        return True
    except ValueError:
        return False
