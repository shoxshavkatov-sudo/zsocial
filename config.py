"""Конфигурация ZSocial — production-ready."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # SECRET_KEY: из env (production) либо из файла рядом с БД (локально — стабильно
    # между рестартами). Если файла нет — создаём и сохраняем случайный.
    _sk_env = os.environ.get('SECRET_KEY')
    if _sk_env:
        SECRET_KEY = _sk_env
    else:
        _sk_file = os.path.join(
            os.environ.get('RENDER_DATA_DIR') or BASE_DIR, '.secret_key')
        if os.path.exists(_sk_file):
            with open(_sk_file, 'rb') as f:
                SECRET_KEY = f.read()
        else:
            SECRET_KEY = os.urandom(32)
            try:
                with open(_sk_file, 'wb') as f:
                    f.write(SECRET_KEY)
            except OSError:
                pass  # read-only FS — fallback на случайный ключ

    # БД: постоянное хранилище. На Render free tier только /opt/render/.data переживает деплой
    _render_persist = os.environ.get('RENDER') == 'true' and '/opt/render/.data'
    _data_dir = os.environ.get('RENDER_DATA_DIR') or _render_persist or os.environ.get('XDG_DATA_HOME') or BASE_DIR
    os.makedirs(_data_dir, exist_ok=True)
    DATABASE = os.path.join(_data_dir, 'social.db')

    UPLOAD_FOLDER = os.path.join(_data_dir, 'uploads')
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

    # VAPID для Web Push: ключи генерируются один раз и хранятся в файле
    VAPID_PRIVATE_KEY_PATH = os.path.join(_data_dir, '.vapid_private')
    VAPID_PUBLIC_KEY_PATH = os.path.join(_data_dir, '.vapid_public')
    VAPID_SUBJECT = os.environ.get('VAPID_SUBJECT', 'mailto:admin@zsocial.app')

    @classmethod
    def ensure_vapid_keys(cls):
        """Генерирует VAPID ключи при первом запуске, возвращает (private_pem, public_b64url)."""
        if os.path.exists(cls.VAPID_PRIVATE_KEY_PATH) and os.path.exists(cls.VAPID_PUBLIC_KEY_PATH):
            with open(cls.VAPID_PRIVATE_KEY_PATH, 'rb') as f:
                priv = f.read()
            with open(cls.VAPID_PUBLIC_KEY_PATH) as f:
                pub = f.read().strip()
            return priv, pub
        from py_vapid import Vapid
        from cryptography.hazmat.primitives import serialization
        import base64
        vapid = Vapid()
        vapid.generate_keys()
        priv_pem = vapid.private_pem()  # bytes
        # Публичный ключ → uncompressed point → base64url
        pub_bytes = vapid.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )
        pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode().rstrip('=')
        with open(cls.VAPID_PRIVATE_KEY_PATH, 'wb') as f:
            f.write(priv_pem)
        with open(cls.VAPID_PUBLIC_KEY_PATH, 'w') as f:
            f.write(pub_b64)
        return priv_pem, pub_b64
