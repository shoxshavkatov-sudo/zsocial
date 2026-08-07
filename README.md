# ZSocial — Профессиональная социальная сеть

Строгий чёрно-белый минимализм. Liquid glass нижняя панель. Чат в реальном времени. Админ-панель. Закладки. Хештеги. Верификация.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-black)
![Deploy](https://img.shields.io/badge/Deploy-Render-46E3B7)

## ✨ Возможности

- 💬 **Чат в реальном времени** — WebSocket (Flask-SocketIO + gevent)
- 📝 **Посты** — текст + изображения, лайки, комментарии
- 🔖 **Закладки** — сохраняйте посты
- #️⃣ **Хештеги** — кликабельные, фильтр ленты по тегу
- 👤 **Профили** — аватар, обложка, био, статус
- 🔒 **Приватность** — публичные / приватные профили
- ✓ **Верификация** — значок для подтверждённых аккаунтов
- 👥 **Подписки** — лента по подпискам
- 🔔 **Уведомления** — лайки, комментарии, подписки
- 🛡️ **Админ-панель** — пользователи, контент, статистика, настройки
- 🌓 **Тёмная / светлая тема**
- 📱 **Адаптивный дизайн** с liquid glass нижним баром

## 🚀 Локальный запуск

```bash
cd ZSocial
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Открой: **http://localhost:5050**

### Демо-аккаунты
| Логин | Пароль | Роль |
|-------|--------|------|
| `admin` | `admin` | Администратор |
| `a_karimova` | `123456` | Пользователь (верифицирован) |
| `b_aliev` | `123456` | Пользователь |
| `c_yusupova` | `123456` | Приватный профиль |

## ☁️ Деплой на Render

1. Загрузите репозиторий на GitHub
2. На [render.com](https://render.com) → **New** → **Web Service**
3. Подключите репозиторий
4. Настройки подхватятся из `render.yaml` автоматически:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn --worker-class gevent --workers 1 --bind 0.0.0.0:$PORT wsgi:application`
5. Добавьте переменную окружения `SECRET_KEY`

Или нажмите кнопку Deploy (после загрузки на GitHub).

## 📁 Структура

```
ZSocial/
├── app.py              # Flask + SocketIO сервер
├── wsgi.py             # WSGI entry для gunicorn/Render
├── models.py           # БД модели и функции
├── config.py           # Конфигурация
├── requirements.txt    # Зависимости
├── Procfile            # Команда запуска
├── render.yaml         # Render Blueprint
├── templates/          # 11 HTML шаблонов
├── static/css/         # Стили (liquid glass, темы)
├── static/js/          # Клиентская логика
└── static/uploads/     # Загруженные файлы
```

## 🛠️ Технологии

Python · Flask · Flask-SocketIO · gevent · SQLite · Vanilla JS · CSS3
