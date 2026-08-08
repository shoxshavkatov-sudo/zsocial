"""Общие фикстуры pytest для ZSocial.

Каждый тест получает свежее приложение с временной БД (tmp_path),
CSRF и rate-limiter отключены, чтобы тесты были детерминированными.
"""
import os
import sys
import shutil
from pathlib import Path

import pytest

# Убеждаемся, что корень проекта — в путях импорта
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Создаёт Flask-приложение с временной БД во временной папке."""
    # Фиксированный ключ сессии → детерминированные тесты
    monkeypatch.setenv('SECRET_KEY', 'pytest-secret-key')
    # БД и аплоады — во временной папке
    monkeypatch.setenv('RENDER_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('TESTING', '1')

    # Импортируем заново, чтобы config подхватил новые env
    import importlib
    import config
    importlib.reload(config)
    import app as app_module
    importlib.reload(app_module)

    flask_app = app_module.app
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
        SECRET_KEY='pytest-secret-key',
    )
    # Полностью отключаем rate limiter
    try:
        lim = list(flask_app.extensions.get('limiter', []))[0]
        lim.enabled = False
    except Exception:
        pass
    # Полностью отключаем CSRF protect — подменяем метод на no-op
    try:
        csrf_ext = flask_app.extensions.get('csrf')
        if csrf_ext is not None:
            csrf_ext.protect = lambda *a, **kw: None
    except Exception:
        pass

    # Включаем регистрацию в настройках
    with flask_app.app_context():
        from models import get_db
        db = get_db()
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('allow_registration', '1')")
        db.commit()

    yield flask_app

    # Очистка
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture()
def client(app):
    """Тестовый клиент без сохранения сессии между запросами."""
    return app.test_client()


@pytest.fixture()
def db(app):
    """Контекст БД для прямых SQL-запросов в тестах."""
    with app.app_context():
        from models import get_db
        return get_db()


def register(client, username='alice', email=None, password='Pass1234'):
    """Вспомогательная функция: регистрирует пользователя через POST."""
    email = email or f'{username}@test.com'
    return client.post('/register', data={
        'username': username, 'email': email,
        'password': password, 'confirm': password,
    }, follow_redirects=True)


def login(client, username='alice', password='Pass1234'):
    """Вспомогательная функция: логинит пользователя."""
    return client.post('/login', data={
        'login': username, 'password': password,
    }, follow_redirects=True)


def auth_client(app, username='alice', password='Pass1234'):
    """Возвращает клиент с уже залогиненной сессией (через session_transaction)."""
    client = app.test_client()
    register(client, username=username)
    with client.session_transaction() as sess:
        with app.app_context():
            from models import User
            u = User.get_by_username(username)
            sess['user_id'] = u['id']
            sess['token_version'] = u['token_version'] if 'token_version' in u.keys() else 0
    return client
