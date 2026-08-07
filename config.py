"""Конфигурация ZSocial — production-ready."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32))

    # БД: используем постоянную директорию Render, если есть
    _data_dir = os.environ.get('RENDER_DATA_DIR') or os.environ.get('XDG_DATA_HOME') or BASE_DIR
    DATABASE = os.path.join(_data_dir, 'social.db')

    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS = {
        # Изображения
        'png', 'jpg', 'jpeg', 'gif', 'webp',
        # Аудио
        'mp3', 'wav', 'ogg', 'm4a', 'aac', 'webm', 'flac',
        # Видео
        'mp4', 'webm', 'mov', 'avi', 'mkv',
        # Документы
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt', 'zip', 'rar',
    }
