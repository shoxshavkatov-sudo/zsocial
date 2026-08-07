# ZSocial — Профессиональная социальная сеть

Строгий чёрно-белый минимализм. Liquid glass нижняя панель. Чат в реальном времени. Админ-панель. Закладки. Хештеги. Упоминания. Репосты. Реакции. Email-уведомления.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-black)
![Deploy](https://img.shields.io/badge/Deploy-Render-46E3B7)

## ✨ Возможности

- 💬 **Чат в реальном времени** — WebSocket (Flask-SocketIO + gevent)
  - Индикатор «печатает...»
  - Статус прочтения (✓ / ✓✓)
  - Удаление сообщений
  - Реакции (эмодзи) на сообщения
  - Голосовые / видео / файлы
- 📝 **Посты** — текст + изображения, лайки, комментарии
  - Редактирование постов
  - Репосты / цитирование
  - @упоминания (кликабельные)
  - #хештеги + трендовые теги
  - Глобальный поиск по людям и постам
- 🔖 **Закладки** — сохраняйте посты
- 👤 **Профили** — аватар, обложка, био, статус
- 🔒 **Приватность** — публичные / приватные профили
- ✓ **Верификация** — значок для подтверждённых аккаунтов
- 👥 **Подписки** — лента по подпискам
- 🔔 **Уведомления** — лайки, комментарии, подписки (+ опционально на email)
- 🛡️ **Админ-панель** — пользователи, контент, жалобы, статистика, настройки
- 🔐 **Аккаунт** — смена пароля, выход со всех устройств, удаление аккаунта
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
   - Persistent disk (1 ГБ) — БД и загрузки переживают деплой
5. Добавьте переменные окружения:
   - `SECRET_KEY` (генерируется автоматически)
   - `MAIL_ENABLED=1` + `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` — для email

> Без SMTP-настроек (`MAIL_ENABLED=0`) сайт работает полностью, письма пишутся в лог вместо отправки.

## 📧 Email-уведомления

Через stdlib `smtplib` (без внешних зависимостей). Поддерживаются:
- Лайк вашего поста
- Комментарий под вашим постом
- Новая подписка

Каждый пользователь может отключить email-уведомления в настройках.

## 📁 Структура

```
ZSocial/
├── app.py              # Flask + SocketIO сервер
├── wsgi.py             # WSGI entry для gunicorn/Render
├── models.py           # БД модели и функции
├── mailer.py           # SMTP email (async, no-op fallback)
├── config.py           # Конфигурация
├── requirements.txt    # Зависимости
├── Procfile            # Команда запуска
├── render.yaml         # Render Blueprint (+ persistent disk)
├── templates/          # HTML шаблоны
├── static/css/         # Стили (liquid glass, темы)
├── static/js/          # Клиентская логика
└── uploads/            # Загруженные пользователями файлы
```

## 🛠️ Технологии

Python · Flask · Flask-SocketIO · gevent · SQLite · smtplib · Vanilla JS · CSS3
