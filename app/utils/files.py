"""
Утилиты для работы с файлами
"""

import mimetypes
import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app


def _normalize_extension_set(allowed_extensions):
    if not allowed_extensions:
        return set()
    return {str(ext).lower().lstrip('.') for ext in allowed_extensions if str(ext).strip()}


def _mime_to_extension(mimetype):
    if not mimetype:
        return None
    mime = mimetype.split(';', 1)[0].strip().lower()
    mapping = {
        'image/jpeg': '.jpg',
        'image/jpg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/webp': '.webp',
        'video/mp4': '.mp4',
        'video/quicktime': '.mov',
        'video/webm': '.webm',
        'video/x-msvideo': '.avi',
        'video/x-matroska': '.mkv',
        'video/x-ms-wmv': '.wmv',
    }
    if mime in mapping:
        return mapping[mime]
    return mimetypes.guess_extension(mime)


def detect_media_kind(filename, mimetype=None, default='image'):
    """Определяет тип медиа по MIME или расширению имени файла."""
    if mimetype:
        mime = mimetype.split(';', 1)[0].strip().lower()
        if mime.startswith('image/'):
            return 'image'
        if mime.startswith('video/'):
            return 'video'

    lowered = (filename or '').lower()
    ext = lowered.rsplit('.', 1)[1] if '.' in lowered else ''
    if ext in {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'}:
        return 'image'
    if ext in {'mp4', 'mov', 'webm', 'avi', 'mkv', 'm4v', 'wmv'}:
        return 'video'
    return default


def choose_media_extension(filename, mimetype=None):
    """Возвращает корректное расширение по MIME, иначе по имени файла."""
    if mimetype:
        ext = _mime_to_extension(mimetype)
        if ext:
            return ext

    lowered = (filename or '').lower()
    if '.' not in lowered:
        return ''
    ext = lowered.rsplit('.', 1)[1]
    return f'.{ext}' if ext else ''


def allowed_file(filename, allowed_extensions, mimetype=None):
    """Проверка разрешённого расширения файла с учётом MIME-типов."""
    if not filename:
        return False

    allowed = _normalize_extension_set(allowed_extensions)
    if not allowed:
        return False

    lowered = filename.lower()
    ext = lowered.rsplit('.', 1)[1] if '.' in lowered else ''
    if ext and ext in allowed:
        return True

    if mimetype:
        mime = mimetype.split(';', 1)[0].strip().lower()
        mime_ext = (_mime_to_extension(mime) or '').lstrip('.').lower()
        if mime_ext and mime_ext in allowed:
            return True

        if mime.startswith('image/') and {'jpg', 'jpeg', 'png', 'gif', 'webp'} & allowed:
            return True
        if mime.startswith('video/') and {'mp4', 'mov', 'webm', 'avi', 'mkv', 'm4v', 'wmv'} & allowed:
            return True

    return False


def save_file(file, subfolder, allowed_extensions=None, mime_type=None):
    """
    Сохранение загруженного файла

    Args:
        file: FileStorage объект
        subfolder: подпапка в uploads (например, 'covers', 'tracks')
        allowed_extensions: разрешённые расширения для фильтрации
        mime_type: MIME тип файла, чтобы выбирать корректное расширение

    Returns:
        Имя сохранённого файла или None при ошибке
    """
    if not file or not file.filename:
        return None

    if allowed_extensions is not None and not allowed_file(file.filename, allowed_extensions, mime_type):
        return None

    original_filename = secure_filename(file.filename)
    ext = choose_media_extension(original_filename, mime_type)
    unique_filename = f'{uuid.uuid4().hex}{ext}' if ext else uuid.uuid4().hex

    # Путь для сохранения
    upload_folder = os.path.join(current_app.root_path, '..', 'uploads', subfolder)
    os.makedirs(upload_folder, exist_ok=True)

    file_path = os.path.join(upload_folder, unique_filename)

    try:
        file.save(file_path)
        return unique_filename
    except Exception as e:
        current_app.logger.error(f'Ошибка сохранения файла: {e}')
        return None


def delete_file(filename, subfolder):
    """
    Удаление файла
    
    Args:
        filename: имя файла
        subfolder: подпапка в uploads
    
    Returns:
        True при успешном удалении, False при ошибке
    """
    if not filename:
        return False
    
    file_path = os.path.join(current_app.root_path, '..', 'uploads', subfolder, filename)
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except Exception as e:
        current_app.logger.error(f'Ошибка удаления файла: {e}')
        return False


def get_file_size(filename, subfolder):
    """Получение размера файла в байтах"""
    if not filename:
        return 0
    
    file_path = os.path.join(current_app.root_path, '..', 'uploads', subfolder, filename)
    
    try:
        if os.path.exists(file_path):
            return os.path.getsize(file_path)
        return 0
    except Exception:
        return 0


def format_file_size(size_bytes):
    """Форматирование размера файла"""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    elif size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    else:
        return f'{size_bytes / (1024 * 1024 * 1024):.1f} GB'
