"""ZSocial — социальная сеть. Production версия с чатом, закладками, хештегами, админкой."""
import os
import re
import atexit
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, send_from_directory
)
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
import uuid

from config import Config
from models import (
    init_db, migrate_db, get_db, close_db, can_view_profile, render_text_content,
    is_online, backup_db_to_json, restore_db_from_json,
    User, Post, Like, Comment, Bookmark, Follow, Message, Notification, Report, Group, Poll, PostView, SiteSettings,
    GroupMessage, VoiceRoom, Story, StoryView, PushSubscription
)
import mailer

app = Flask(__name__)
app.config.from_object(Config)
# gevent для production (gunicorn), threading как fallback для локали
try:
    import gevent  # noqa
    _async = 'gevent'
except ImportError:
    _async = 'threading'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=_async)

# CSRF защита (формы + AJAX). Socket.IO не использует CSRF (engineio path).
csrf = CSRFProtect(app)
# Исключаем WebSocket-эндпоинт из CSRF
csrf.exempt(__name__)  # no-op; Socket.IO обрабатывается middleware, не Flask-роутами

# Rate limiting (in-memory). На production стоит заменить на Redis storage,
# но для free-tier Render in-memory приемлемо.
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[],  # без глобальных лимитов — только явные на роутах
    storage_uri="memory://",
)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.teardown_appcontext(close_db)


@app.before_request
def update_last_seen():
    """Обновляет last_seen пользователя (раз в 60с, чтобы не писать в БД на каждый запрос)."""
    if 'user_id' not in session:
        return
    import time
    now = time.time()
    last = session.get('_last_seen_ts', 0)
    if now - last > 60:
        from models import get_db as _get_db
        try:
            db = _get_db()
            db.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE id = ?", (session['user_id'],))
            db.commit()
        except Exception:
            pass
        session['_last_seen_ts'] = now


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Отдаёт загруженные пользователями файлы из UPLOAD_FOLDER.

    Физически файлы лежат ВНЕ static/ (в папке данных), поэтому для их показа
    нужен отдельный роут. Шаблоны используют хелпер media_url(), который для
    пользовательских файлов строит URL сюда.
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/sw.js')
def service_worker():
    """Service Worker в корне домена, чтобы его scope был '/'."""
    resp = send_from_directory(app.static_folder, 'sw.js')
    resp.headers['Content-Type'] = 'application/javascript; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


@app.route('/manifest.json')
def web_manifest():
    """manifest.json в корне для соответствия PWA-спецификации."""
    resp = send_from_directory(app.static_folder, 'manifest.json')
    resp.headers['Content-Type'] = 'application/manifest+json; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache, must-revalidate'
    return resp

# Версия приложения — для cache-busting статики.
# В продакшене берём хэш коммита из env. Локально — mtime style.css/main.js,
# чтобы при каждом изменении статики браузер гарантированно подхватывал обновления.
_commit = os.environ.get('RENDER_GIT_COMMIT', '')
if _commit:
    APP_VERSION = _commit[:8]
else:
    import time as _t
    _here = os.path.dirname(os.path.abspath(__file__))
    _mtime = 0
    for _f in ('static/css/style.css', 'static/js/main.js'):
        _p = os.path.join(_here, _f)
        if os.path.isfile(_p):
            _mtime = max(_mtime, int(os.path.getmtime(_p)))
    APP_VERSION = str(_mtime or int(_t.time()))


# ==================== WEB PUSH (VAPID) ====================
# Генерируем ключи один раз при старте (если ещё не созданы).
try:
    VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY = Config.ensure_vapid_keys()
except Exception as e:
    print(f'[push] VAPID key generation failed: {e}')
    VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY = None, None


def send_push(user_id, title, body, url='/feed'):
    """Отправляет Web Push всем подпискам пользователя (если он офлайн).
    Вызывается в отдельном потоке, поэтому создаёт app context."""
    if not VAPID_PRIVATE_KEY:
        return
    with app.app_context():
        subs = PushSubscription.get_by_user(user_id)
        if not subs:
            return
        try:
            from pywebpush import webpush, WebPushException
        except ImportError:
            return
        import json as _json
        payload = _json.dumps({'title': title, 'body': body, 'url': url})
        dead = []
        for sub in subs:
            try:
                webpush(
                    subscription_info={
                        'endpoint': sub['endpoint'],
                        'keys': {'p256dh': sub['p256dh'], 'auth': sub['auth']},
                    },
                    data=payload,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims={'sub': Config.VAPID_SUBJECT},
                )
            except WebPushException as ex:
                # 410 Gone / 404 — подписка больше не валидна
                if ex.response is not None and ex.response.status_code in (404, 410):
                    dead.append(sub['endpoint'])
                else:
                    print(f'[push] error: {ex}')
            except Exception as ex:
                print(f'[push] unexpected: {ex}')
        for ep in dead:
            PushSubscription.delete_by_endpoint(ep)


@app.route('/api/vapid-public')
def vapid_public_key():
    """Возвращает публичный VAPID ключ (base64url) для подписки в браузере."""
    if not VAPID_PUBLIC_KEY:
        return jsonify({'error': 'VAPID не настроен'}), 500
    return jsonify({'publicKey': VAPID_PUBLIC_KEY})





@app.after_request
def no_cache_dynamic(resp):
    """Кэш-стратегия:
       — HTML: без кэша (свежий контент после деплоя);
       — Статика (CSS/JS/шрифты/иконки): длинный кэш (1 год), т.к. URL несёт
         ?v=<mtime> и при изменении файла версия меняется → браузер тянет свежую
         копию, а между деплоями отдаёт из кэша (быстрее, меньше запросов);
       — Загруженные медиа: средний кэш (1 час), чтобы не дёргать БД/диск лишний раз.
    """
    ct = resp.headers.get('Content-Type') or ''
    if 'text/html' in ct:
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    elif '/static/' in (request.path or '') or any(ct.startswith(t) for t in
            ('text/css', 'application/javascript', 'text/javascript', 'image/',
             'font/', 'application/font', 'application/json')):
        # Длинный кэш для версифицированной статики
        resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    elif request.path and request.path.startswith('/uploads/'):
        resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


def _seed_if_empty():
    """Создаёт демо-пользователей при первом запуске."""
    from werkzeug.security import generate_password_hash
    db = get_db()
    if db.execute('SELECT COUNT(*) c FROM users').fetchone()['c'] > 0:
        return
    users = [
        ('admin', 'admin@z.io', 'admin', 'Администратор', 'Системный администратор ZSocial.', 'Режим обслуживания', 'admin', 1, 0),
        ('a_karimova', 'aliya@test.com', '123456', 'Алия Каримова', 'Продуктовый дизайнер.', 'Работаю над новым проектом', 'user', 1, 0),
        ('b_aliev', 'bob@test.com', '123456', 'Боб Алиев', 'Senior Backend разработчик.', '', 'user', 0, 0),
        ('c_yusupova', 'carol@test.com', '123456', 'Кэрол Юсупова', 'Маркетолог. SMM.', 'Открыта к сотрудничеству', 'user', 0, 1),
    ]
    for u in users:
        db.execute(
            'INSERT INTO users (username, email, password_hash, display_name, bio, status, role, verified, is_private) VALUES (?,?,?,?,?,?,?,?,?)',
            (u[0], u[1], generate_password_hash(u[2]), u[3], u[4], u[5], u[6], u[7], u[8])
        )
    posts = [
        (2, 'Запустили редизайн. Стало чище — минимум цвета, максимум воздуха. #дизайн #ux'),
        (3, 'Перевели бэкенд на новую архитектуру. Время ответа API упало с 340мс до 90мс. #разработка'),
        (1, 'Добро пожаловать в ZSocial — профессиональную сеть. Строгий дизайн, фокус на содержании.'),
        (2, 'Тёмная тема доступна в настройках. Приятная работа в любое время суток.'),
    ]
    for p in posts:
        db.execute('INSERT INTO posts (user_id, content) VALUES (?,?)', (p[0], p[1]))
    db.execute('INSERT INTO likes (user_id, post_id) VALUES (3,1)')
    db.execute('INSERT INTO likes (user_id, post_id) VALUES (4,1)')
    db.execute('INSERT INTO likes (user_id, post_id) VALUES (1,1)')
    db.execute('INSERT INTO likes (user_id, post_id) VALUES (2,2)')
    db.execute('INSERT INTO likes (user_id, post_id) VALUES (2,3)')
    db.execute('INSERT INTO likes (user_id, post_id) VALUES (3,3)')
    db.execute('INSERT INTO likes (user_id, post_id) VALUES (3,4)')
    db.execute('INSERT INTO comments (user_id, post_id, content) VALUES (3,1,?)', ('Согласен, стало лучше.',))
    db.execute('INSERT INTO comments (user_id, post_id, content) VALUES (2,2,?)', ('Отличный результат!',))
    db.execute('INSERT INTO follows (follower_id, followed_id) VALUES (2,3)')
    db.execute('INSERT INTO follows (follower_id, followed_id) VALUES (3,2)')
    db.execute('INSERT INTO follows (follower_id, followed_id) VALUES (2,1)')
    db.execute('INSERT INTO follows (follower_id, followed_id) VALUES (4,2)')
    db.execute('INSERT INTO bookmarks (user_id, post_id) VALUES (2,2)')
    db.execute('INSERT INTO notifications (user_id, actor_id, type, post_id) VALUES (2,3,?,1)', ('like',))
    db.execute('INSERT INTO notifications (user_id, actor_id, type, post_id) VALUES (2,4,?,1)', ('like',))
    db.execute('INSERT INTO notifications (user_id, actor_id, type) VALUES (3,4,?)', ('follow',))
    db.commit()


# Инициализация БД с демо-данными при первом запуске
with app.app_context():
    init_db()
    migrate_db()
    # Restore из бэкапа если БД пустая (данные потерялись при деплое)
    restored = restore_db_from_json()
    if not restored:
        _seed_if_empty()
    # Создаём первичный бэкап
    backup_db_to_json()


# Периодический backup каждые 5 минут (фон) — данные переживут деплой
import threading
def _periodic_backup():
    while True:
        import time as _t
        _t.sleep(300)
        try:
            with app.app_context():
                backup_db_to_json()
        except Exception:
            pass

_backup_thread = threading.Thread(target=_periodic_backup, daemon=True)
_backup_thread.start()


# Гарантия сохранения данных: checkpoint WAL перед завершением процесса.
# Без этого при kill -9 несохранённые WAL-страницы могут потеряться.
def _db_checkpoint_on_exit():
    try:
        import sqlite3
        conn = sqlite3.connect(Config.DATABASE)
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        conn.commit()
        conn.close()
    except Exception:
        pass
    # Финальный бэкап
    try:
        backup_db_to_json()
    except Exception:
        pass


atexit.register(_db_checkpoint_on_exit)


# ==================== ХЕЛПЕРЫ ====================
def _media_for(path):
    """URL для медиа-пути из БД. img/... → static; иначе → /uploads/..."""
    if not path:
        return ''
    if isinstance(path, str) and path.startswith(('img/', 'css/', 'js/')):
        return url_for('static', filename=path)
    # Загруженные файлы: БД хранит 'uploads/<name>', убираем префикс для serve_upload
    if isinstance(path, str) and path.startswith('uploads/'):
        path = path[len('uploads/'):]
    return url_for('serve_upload', filename=path)


def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def save_file(file, prefix='img'):
    if file and file.filename and allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        name = f"{prefix}_{uuid.uuid4().hex[:12]}.{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], name))
        return f'uploads/{name}'
    return None


def current_user():
    if 'user_id' not in session:
        return None
    u = User.get(session['user_id'])
    if not u:
        session.pop('user_id', None)
        return None
    if u['banned']:
        session.pop('user_id', None)
        return None
    # Проверка версии токена (выход со всех устройств)
    if session.get('token_version', 0) != u['token_version']:
        session.pop('user_id', None)
        return None
    return u


def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if 'user_id' not in session:
            flash('Войдите, чтобы продолжить', 'error')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        u = current_user()
        if not u or u['role'] != 'admin':
            flash('Доступ только для администраторов', 'error')
            return redirect(url_for('feed'))
        return f(*a, **kw)
    return wrap


def time_ago(s):
    if not s:
        return ''
    try:
        dt = datetime.strptime(str(s)[:19], '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return str(s)
    diff = (datetime.now() - dt).total_seconds()
    if diff < 60: return 'только что'
    if diff < 3600: return f'{int(diff//60)} мин'
    if diff < 86400: return f'{int(diff//3600)} ч'
    if diff < 604800: return f'{int(diff//86400)} д'
    return dt.strftime('%d.%m.%Y')


app.jinja_env.filters['time_ago'] = time_ago
app.jinja_env.filters['render_text'] = render_text_content


@app.template_filter('urlize_message')
def urlize_message(text):
    """Экранирует текст и делает URL кликабельными (для чата)."""
    import re as _re
    from markupsafe import Markup, escape
    if not text:
        return Markup('')
    safe = str(escape(text))
    # ссылки
    safe = _re.sub(
        r'(https?://[^\s<]+)',
        r'<a href="\1" target="_blank" rel="noopener">\1</a>',
        safe)
    return Markup(safe)


@app.context_processor
def inject_globals():
    u = current_user()
    notifs = msgs = 0
    site = SiteSettings.get_all()
    if u:
        notifs = Notification.unread_count(u['id'])
        msgs = Message.unread_count(u['id'])

    def media_url(path):
        """Строит правильный URL для медиа по пути из БД (см. _media_for)."""
        return _media_for(path)

    def poll_for(post_id):
        """Возвращает опрос для поста или None (для шаблона)."""
        return Poll.get_by_post(post_id)

    def has_voted(post_id):
        """Голосовал ли текущий пользователь в опросе поста."""
        if not u:
            return False
        return Poll.has_voted(post_id, u['id'])

    def view_count(post_id):
        return PostView.count(post_id)

    def voice_room_participants(room_id):
        return VoiceRoom.get_participants(room_id)

    return dict(cu=u, unread_notifs=notifs, unread_msgs=msgs,
                site_name=site.get('site_name', 'ZSocial'),
                site_desc=site.get('site_desc', ''),
                site=site,
                v=APP_VERSION,
                media_url=media_url,
                _media_for=_media_for,
                is_online=is_online,
                poll_for=poll_for,
                has_voted=has_voted,
                view_count=view_count,
                voice_room_participants=voice_room_participants)


@app.context_processor
def inject_app_version():
    """Версия для cache-busting статики (v=... в URL)."""
    return dict(APP_VERSION=APP_VERSION)


# ==================== АВТОРИЗАЦИЯ ====================
@app.route('/')
def index():
    u = current_user()
    if SiteSettings.get('maintenance_mode') == '1' and (not u or u['role'] != 'admin'):
        return render_template('maintenance.html')
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('feed'))


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("3/hour", methods=['POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('feed'))
    if SiteSettings.get('allow_registration') != '1':
        flash('Регистрация временно отключена', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        un = request.form.get('username', '').strip()
        em = request.form.get('email', '').strip()
        pw = request.form.get('password', '')
        cf = request.form.get('confirm', '')
        errs = []
        if len(un) < 3: errs.append('Минимум 3 символа в username')
        if '@' not in em: errs.append('Некорректный email')
        if len(pw) < 6: errs.append('Пароль минимум 6 символов')
        if pw != cf: errs.append('Пароли не совпадают')
        if User.get_by_username(un): errs.append('Имя занято')
        if User.get_by_email(em): errs.append('Email занят')
        if errs:
            for e in errs: flash(e, 'error')
            return render_template('register.html')
        u = User.create(un, em, pw)
        session['user_id'] = u['id']
        session['token_version'] = u['token_version'] if 'token_version' in u.keys() else 0
        flash(f'Добро пожаловать, {un}!', 'success')
        return redirect(url_for('feed'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("8/minute", methods=['POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('feed'))
    if request.method == 'POST':
        lf = request.form.get('login', '').strip()
        pw = request.form.get('password', '')
        u = User.get_by_username(lf) or User.get_by_email(lf)
        if u and User.verify(u['password_hash'], pw):
            if u['banned']:
                flash('Аккаунт заблокирован', 'error')
                return render_template('login.html')
            session['user_id'] = u['id']
            session['token_version'] = u['token_version']
            flash(f'С возвращением, {u["username"]}!', 'success')
            return redirect(url_for('feed'))
        flash('Неверные данные', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли', 'success')
    return redirect(url_for('login'))


# ==================== WEB PUSH ПОДПИСКИ ====================
@app.route('/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    """Сохраняет подписку браузера (endpoint + ключи) для текущего пользователя."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    p256dh = data.get('keys', {}).get('p256dh')
    auth = data.get('keys', {}).get('auth')
    if not (endpoint and p256dh and auth):
        return jsonify({'error': 'Неполные данные'}), 400
    PushSubscription.subscribe(session['user_id'], endpoint, p256dh, auth)
    return jsonify({'ok': True})


@app.route('/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    """Удаляет подписку (например, при отключении в настройках)."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get('endpoint')
    if endpoint:
        PushSubscription.delete(session['user_id'], endpoint)
    else:
        db = get_db()
        db.execute('DELETE FROM push_subscriptions WHERE user_id=?', (session['user_id'],))
        db.commit()
    return jsonify({'ok': True})


# ==================== ЛЕНТА ====================
@app.route('/feed')
@login_required
def feed():
    Story.cleanup_expired()  # чистка истёкших историй
    tab = request.args.get('tab', 'all')
    tag = request.args.get('tag', '').strip()
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 20
    if tab == 'following':
        posts, total = Post.get_following_feed(session['user_id'], page=page, per_page=per_page, tag=tag or None)
    else:
        posts, total = Post.get_all(page=page, per_page=per_page, tag=tag or None)
    liked = {p['id'] for p in posts if Like.is_liked(session['user_id'], p['id'])}
    saved_ids = {b['id'] for b in Bookmark.get_by_user(session['user_id'])}
    trending = Post.get_trending_tags(10)
    pages = (total + per_page - 1) // per_page
    story_groups = Story.get_active_for_user(session['user_id'])
    return render_template('feed.html', posts=posts, liked_posts=liked, saved_posts=saved_ids,
                           tab=tab, tag=tag, trending=trending,
                           page=page, pages=pages, per_page=per_page,
                           story_groups=story_groups)


@app.route('/explore')
@login_required
def explore():
    """Страница обзора: популярные посты, тренды, рекомендации пользователей и групп."""
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 12
    popular_posts, total = Post.get_popular(page=page, per_page=per_page)
    liked = {p['id'] for p in popular_posts if Like.is_liked(session['user_id'], p['id'])}
    saved_ids = {b['id'] for b in Bookmark.get_by_user(session['user_id'])}
    trending = Post.get_trending_tags(15)
    suggested_users = User.get_suggested(session['user_id'], limit=8)
    popular_groups = Group.get_popular(limit=6)
    pages = (total + per_page - 1) // per_page
    return render_template('explore.html',
                           posts=popular_posts, liked_posts=liked, saved_posts=saved_ids,
                           trending=trending,
                           suggested_users=suggested_users,
                           popular_groups=popular_groups,
                           page=page, pages=pages, per_page=per_page)


@app.route('/post/create', methods=['POST'])
@login_required
@limiter.limit("10/minute")
def create_post():
    content = request.form.get('content', '').strip()
    image = request.files.get('image')
    # Опрос (необязательно)
    poll_question = request.form.get('poll_question', '').strip()
    poll_options_raw = request.form.get('poll_options', '').strip()
    has_poll = poll_question and poll_options_raw
    if not content and (not image or not image.filename) and not has_poll:
        flash('Пост пуст', 'error')
        return redirect(url_for('feed'))
    img_path = save_file(image, 'post') if image else None
    post = Post.create(session['user_id'], content, img_path)
    if has_poll:
        opts = [o.strip() for o in poll_options_raw.split('\n') if o.strip()]
        if len(opts) >= 2:
            Poll.create(post['id'], poll_question, opts)
    flash('Опубликовано', 'success')
    return redirect(url_for('feed'))


@app.route('/post/<int:pid>/delete', methods=['POST'])
@login_required
def delete_post(pid):
    force = current_user()['role'] == 'admin'
    if Post.delete(pid, session['user_id'], force=force):
        flash('Удалено', 'success')
    else:
        flash('Ошибка', 'error')
    return redirect(request.referrer or url_for('feed'))


@app.route('/post/<int:pid>/edit', methods=['GET', 'POST'])
@login_required
@limiter.limit("10/minute", methods=['POST'])
def edit_post(pid):
    post = Post.get(pid)
    if not post:
        flash('Не найдено', 'error')
        return redirect(url_for('feed'))
    if post['user_id'] != session['user_id'] and current_user()['role'] != 'admin':
        flash('Нет прав', 'error')
        return redirect(url_for('feed'))
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            flash('Пост пуст', 'error')
            return redirect(url_for('edit_post', pid=pid))
        Post.edit(pid, session['user_id'], content)
        flash('Сохранено', 'success')
        return redirect(url_for('feed'))
    return render_template('edit_post.html', post=post)


@app.route('/post/<int:pid>/repost', methods=['POST'])
@login_required
def repost(pid):
    parent = Post.get(pid)
    if not parent:
        return jsonify({'error': 'Не найдено'}), 404
    quote = request.get_json(silent=True)
    quote_text = (quote.get('quote') or '').strip() if quote else ''
    new = Post.repost(session['user_id'], pid, quote_text)
    if new:
        return jsonify({'ok': True, 'id': new['id']})
    return jsonify({'error': 'Вы уже поделились этим постом'}), 400


@app.route('/post/<int:pid>/like', methods=['POST'])
@login_required
def toggle_like(pid):
    post = Post.get(pid)
    if not post:
        return jsonify({'error': 'Не найдено'}), 404
    liked = Like.toggle(session['user_id'], pid)
    if liked:
        Notification.create(post['user_id'], session['user_id'], 'like', pid)
        owner = User.get(post['user_id'])
        if owner and owner['email_notifs'] and owner['id'] != session['user_id']:
            actor = current_user()
            mailer.notify_like(owner['email'], actor['display_name'] or actor['username'], (post['content'] or '')[:80])
        # Web Push если получатель офлайн
        if owner and owner['id'] != session['user_id'] and not is_online(owner):
            actor = current_user()
            import threading
            threading.Thread(target=send_push, args=(
                owner['id'], 'ZSocial',
                f'{actor["display_name"] or actor["username"]} оценил(а) ваш пост',
                url_for('feed', _external=False)
            ), daemon=True).start()
    return jsonify({'liked': liked, 'count': Like.count(pid)})


@app.route('/poll/<int:option_id>/vote', methods=['POST'])
@login_required
def poll_vote(option_id):
    ok = Poll.vote(option_id, session['user_id'])
    if not ok:
        return jsonify({'error': 'Вариант не найден'}), 404
    # Найти пост и вернуть обновлённый опрос
    opt = get_db().execute('SELECT p.post_id FROM poll_options o JOIN polls p ON o.poll_id=p.id WHERE o.id=?',
                           (option_id,)).fetchone()
    poll = Poll.get_by_post(opt['post_id']) if opt else None
    return jsonify({'ok': True, 'poll': poll})


@app.route('/post/<int:pid>/bookmark', methods=['POST'])
@login_required
def toggle_bookmark(pid):
    if not Post.get(pid):
        return jsonify({'error': 'Не найдено'}), 404
    saved = Bookmark.toggle(session['user_id'], pid)
    return jsonify({'saved': saved})


@app.route('/post/<int:pid>/comment', methods=['POST'])
@login_required
def add_comment(pid):
    post = Post.get(pid)
    if not post:
        return jsonify({'error': 'Не найдено'}), 404
    content = request.form.get('content', '').strip()
    if not content:
        return jsonify({'error': 'Пусто'}), 400
    parent_id = request.form.get('parent_id', type=int)
    c = Comment.create(session['user_id'], pid, content, parent_id=parent_id)
    Notification.create(post['user_id'], session['user_id'], 'comment', pid)
    owner = User.get(post['user_id'])
    if owner and owner['email_notifs'] and owner['id'] != session['user_id']:
        actor = current_user()
        mailer.notify_comment(owner['email'], actor['display_name'] or actor['username'], (post['content'] or '')[:80])
    # Web Push если владелец поста офлайн
    if owner and owner['id'] != session['user_id'] and not is_online(owner):
        actor = current_user()
        import threading
        threading.Thread(target=send_push, args=(
            owner['id'], 'ZSocial',
            f'{actor["display_name"] or actor["username"]} прокомментировал(а) ваш пост',
            url_for('feed', _external=False)
        ), daemon=True).start()
    return jsonify({
        'id': c['id'], 'content': c['content'], 'username': c['username'],
        'avatar': c['avatar'], 'avatar_url': _media_for(c['avatar']),
        'verified': c['verified'], 'parent_id': c['parent_id'],
        'time': time_ago(c['created_at'])
    })


@app.route('/post/<int:pid>/comments')
@login_required
def get_comments(pid):
    return jsonify([{
        'id': c['id'], 'content': c['content'], 'username': c['username'],
        'avatar': c['avatar'], 'avatar_url': _media_for(c['avatar']),
        'verified': c['verified'], 'parent_id': c['parent_id'],
        'time': time_ago(c['created_at'])
    } for c in Comment.get_by_post(pid)])


# ==================== ПРОФИЛЬ ====================
@app.route('/profile/<username>')
@login_required
def profile(username):
    u = User.get_by_username(username)
    if not u:
        flash('Не найдено', 'error')
        return redirect(url_for('feed'))
    can_view = can_view_profile(session['user_id'], u)
    posts = Post.get_by_user(u['id']) if can_view else []
    media = Post.get_media_by_user(u['id']) if can_view else []
    liked = {p['id'] for p in posts if Like.is_liked(session['user_id'], p['id'])}
    saved_ids = {b['id'] for b in Bookmark.get_by_user(session['user_id'])}
    return render_template('profile.html', pu=u, posts=posts, liked_posts=liked,
                           saved_posts=saved_ids, can_view=can_view, media=media,
                           followers_count=Follow.followers_count(u['id']),
                           following_count=Follow.following_count(u['id']),
                           is_following=Follow.is_following(session['user_id'], u['id']),
                           is_own=u['id'] == session['user_id'])


# ==================== ГРУППЫ ====================

@app.route('/groups')
@login_required
def groups():
    all_groups = Group.get_all()
    my_groups = Group.get_user_groups(session['user_id'])
    return render_template('groups.html', all_groups=all_groups, my_groups=my_groups)


@app.route('/group/create', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        desc = request.form.get('description', '').strip()
        priv = 1 if request.form.get('is_private') else 0
        cover = None
        f = request.files.get('cover')
        if f and f.filename:
            cover = save_file(f, 'group_cover')
        if not name:
            flash('Введите название', 'error'); return redirect(request.url)
        g = Group.create(session['user_id'], name, desc, priv, cover)
        return redirect(url_for('group_page', slug=g['slug']))
    return render_template('create_group.html')


@app.route('/group/<slug>')
@login_required
def group_page(slug):
    g = Group.get_by_slug(slug)
    if not g:
        flash('Группа не найдена', 'error'); return redirect(url_for('groups'))
    members = Group.get_members(g['id'])
    am_member = Group.is_member(g['id'], session['user_id'])
    am_owner = g['owner_id'] == session['user_id']
    # Групповой чат (как в Telegram)
    chat_messages = GroupMessage.get_recent(g['id'], 100) if am_member else []
    # Голосовые комнаты (как в Discord)
    voice_rooms = VoiceRoom.get_by_group(g['id']) if am_member else []
    my_voice_room = None
    if am_member:
        for vr in voice_rooms:
            for p in VoiceRoom.get_participants(vr['id']):
                if p['user_id'] == session['user_id']:
                    my_voice_room = vr['id']
                    break
    return render_template('group.html', g=g, members=members,
                           am_member=am_member, am_owner=am_owner,
                           chat_messages=chat_messages, voice_rooms=voice_rooms,
                           my_voice_room=my_voice_room)


@app.route('/group/<slug>/join', methods=['POST'])
@login_required
def join_group(slug):
    g = Group.get_by_slug(slug)
    if not g:
        return jsonify({'error': 'Не найдено'}), 404
    joined = Group.toggle_join(g['id'], session['user_id'])
    return jsonify({'joined': joined})


@app.route('/group/<slug>/chat/send', methods=['POST'])
@login_required
def group_chat_send(slug):
    """Отправка сообщения в групповой чат ( realtime через Socket.IO)."""
    g = Group.get_by_slug(slug)
    if not g:
        return jsonify({'error': 'Не найдено'}), 404
    if not Group.is_member(g['id'], session['user_id']):
        return jsonify({'error': 'Только для участников'}), 403
    content = request.form.get('content', '').strip()
    msg_type = 'text'
    file_url = None
    file_name = None
    file_size = 0
    f = request.files.get('file')
    if f and f.filename:
        file_url = save_file(f, 'gmsg')
        file_name = f.filename
        file_size = 0
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        if ext in {'jpg', 'jpeg', 'png', 'gif', 'webp'}:
            msg_type = 'image'
        elif ext in {'mp4', 'webm', 'mov'}:
            msg_type = 'video'
        else:
            msg_type = 'file'
    if not content and not file_url:
        return jsonify({'error': 'Пусто'}), 400
    mid = GroupMessage.create(g['id'], session['user_id'], content,
                              msg_type=msg_type, file_url=file_url,
                              file_name=file_name, file_size=file_size)
    u = current_user()
    msg_data = {
        'id': mid,
        'group_id': g['id'],
        'sender_id': session['user_id'],
        'sender_name': u['display_name'] or u['username'],
        'sender_username': u['username'],
        'sender_avatar': u['avatar'],
        'verified': u['verified'],
        'content': content,
        'msg_type': msg_type,
        'file_url': file_url,
        'file_name': file_name,
        'created_at': 'только что',
    }
    socketio.emit('group_message', msg_data, room=f'group_{g["id"]}')
    return jsonify({'ok': True, 'message': msg_data})


@app.route('/group/<slug>/chat/delete/<int:mid>', methods=['POST'])
@login_required
def group_chat_delete(slug, mid):
    g = Group.get_by_slug(slug)
    if not g:
        return jsonify({'error': 'Не найдено'}), 404
    if GroupMessage.delete(mid, session['user_id']):
        socketio.emit('group_message_deleted', {'id': mid, 'group_id': g['id']},
                      room=f'group_{g["id"]}')
        return jsonify({'ok': True})
    return jsonify({'error': 'Нельзя удалить'}), 403


@app.route('/group/<slug>/voice/create', methods=['POST'])
@login_required
def voice_create(slug):
    """Создать голосовую комнату в группе."""
    g = Group.get_by_slug(slug)
    if not g:
        return jsonify({'error': 'Не найдено'}), 404
    if g['owner_id'] != session['user_id']:
        return jsonify({'error': 'Только владелец может создавать комнаты'}), 403
    name = request.form.get('name', 'Голосовая').strip() or 'Голосовая'
    rid = VoiceRoom.create(g['id'], name)
    return jsonify({'ok': True, 'room_id': rid, 'name': name})


@app.route('/group/<slug>/members')
@login_required
def group_members(slug):
    g = Group.get_by_slug(slug)
    if not g:
        flash('Группа не найдена', 'error'); return redirect(url_for('groups'))
    members = Group.get_members(g['id'])
    am_owner = g['owner_id'] == session['user_id']
    return render_template('group_members.html', g=g, members=members, am_owner=am_owner)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    u = current_user()
    if request.method == 'POST':
        avatar = request.files.get('avatar')
        cover = request.files.get('cover')
        User.update(u['id'],
                    display_name=request.form.get('display_name', '').strip(),
                    bio=request.form.get('bio', '').strip(),
                    status=request.form.get('status', '').strip(),
                    avatar=save_file(avatar, 'avatar'),
                    cover=save_file(cover, 'cover'),
                    is_private=1 if request.form.get('is_private') else 0,
                    email_notifs=1 if request.form.get('email_notifs') else 0)
        flash('Сохранено', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html')


# ==================== МУЗЫКА В ПРОФИЛЕ ====================
@app.route('/profile/music/upload', methods=['POST'])
@login_required
@limiter.limit("10/minute")
def upload_profile_music():
    """Загрузка музыки в профиль (как в Telegram)."""
    file = request.files.get('music')
    title = request.form.get('title', '').strip()
    if not file or not file.filename:
        return jsonify({'error': 'Файл не выбран'}), 400
    fn = file.filename.lower()
    if not ('.' in fn and fn.rsplit('.', 1)[1] in {'mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac'}):
        return jsonify({'error': 'Поддерживаются: MP3, WAV, OGG, M4A'}), 400
    music_path = save_file(file, 'music')
    if not title:
        title = secure_filename(file.filename).rsplit('.', 1)[0].replace('_', ' ')[:80]
    db = get_db()
    db.execute('UPDATE users SET profile_music=?, profile_music_title=? WHERE id=?',
               (music_path, title, session['user_id']))
    db.commit()
    return jsonify({'ok': True, 'music': music_path, 'title': title,
                    'music_url': _media_for(music_path)})


@app.route('/profile/music/remove', methods=['POST'])
@login_required
def remove_profile_music():
    """Удаление музыки из профиля."""
    db = get_db()
    db.execute('UPDATE users SET profile_music=NULL, profile_music_title=NULL WHERE id=?',
               (session['user_id'],))
    db.commit()
    return jsonify({'ok': True})


@app.route('/settings/password', methods=['POST'])
@login_required
def change_password():
    u = current_user()
    cur = request.form.get('current_password', '')
    new = request.form.get('new_password', '')
    conf = request.form.get('confirm_password', '')
    if not User.verify(u['password_hash'], cur):
        flash('Неверный текущий пароль', 'error')
        return redirect(url_for('settings'))
    if len(new) < 6:
        flash('Новый пароль минимум 6 символов', 'error')
        return redirect(url_for('settings'))
    if new != conf:
        flash('Пароли не совпадают', 'error')
        return redirect(url_for('settings'))
    User.change_password(u['id'], new)
    User.logout_everywhere(u['id'])
    session.clear()
    flash('Пароль изменён. Войдите заново.', 'success')
    return redirect(url_for('login'))


@app.route('/settings/delete', methods=['POST'])
@login_required
def delete_account():
    u = current_user()
    pw = request.form.get('delete_password', '')
    if not User.verify(u['password_hash'], pw):
        flash('Неверный пароль', 'error')
        return redirect(url_for('settings'))
    User.delete(u['id'])
    session.clear()
    flash('Аккаунт удалён', 'success')
    return redirect(url_for('register'))


@app.route('/settings/logout_all', methods=['POST'])
@login_required
def logout_all():
    u = current_user()
    User.logout_everywhere(u['id'])
    session.clear()
    flash('Вы вышли со всех устройств', 'success')
    return redirect(url_for('login'))


@app.route('/follow/<int:uid>', methods=['POST'])
@login_required
def toggle_follow(uid):
    if uid == session['user_id']:
        return jsonify({'error': 'Нельзя на себя'}), 400
    u = User.get(uid)
    if not u:
        return jsonify({'error': 'Не найдено'}), 404
    f = Follow.toggle(session['user_id'], uid)
    if f:
        Notification.create(uid, session['user_id'], 'follow')
        target = User.get(uid)
        if target and target['email_notifs']:
            actor = current_user()
            mailer.notify_follow(target['email'], actor['display_name'] or actor['username'])
        # Web Push если цель офлайн
        if target and not is_online(target):
            actor = current_user()
            import threading
            threading.Thread(target=send_push, args=(
                uid, 'ZSocial',
                f'У вас новый подписчик: {actor["display_name"] or actor["username"]}',
                url_for('profile', username=actor['username'], _external=False)
            ), daemon=True).start()
    return jsonify({'following': f, 'count': Follow.followers_count(uid)})


# ==================== ПОИСК / ЛЮДИ ====================
@app.route('/people')
@login_required
def people():
    q = request.args.get('q', '')
    tab = request.args.get('tab', 'users')
    page = max(1, request.args.get('page', 1, type=int))
    per_page = 20
    users = []
    posts_results = []
    pages = 0
    following_ids = {f['followed_id'] for f in Follow.get_following(session['user_id'])}
    liked = set()
    saved_ids = set()
    if q:
        if tab == 'posts':
            posts_results, total = Post.search_content(q, page=page, per_page=per_page)
            liked = {p['id'] for p in posts_results if Like.is_liked(session['user_id'], p['id'])}
            saved_ids = {b['id'] for b in Bookmark.get_by_user(session['user_id'])}
            pages = (total + per_page - 1) // per_page
        else:
            users = User.search(q)
    else:
        users = [x for x in User.get_all() if x['id'] != session['user_id'] and x['banned'] == 0]
    return render_template('people.html', users=users, following_ids=following_ids, q=q, tab=tab,
                           posts=posts_results, liked_posts=liked, saved_posts=saved_ids,
                           page=page, pages=pages)


# ==================== ЗАКЛАДКИ ====================
@app.route('/bookmarks')
@login_required
def bookmarks():
    posts = Bookmark.get_by_user(session['user_id'])
    liked = {p['id'] for p in posts if Like.is_liked(session['user_id'], p['id'])}
    saved_ids = {p['id'] for p in posts}
    return render_template('bookmarks.html', posts=posts, liked_posts=liked, saved_posts=saved_ids)


# ==================== ЧАТ ====================
@app.route('/chat')
@login_required
def chat():
    u = current_user()
    dialogs = Message.get_dialogs(u['id'])
    partner = None
    messages = []
    partner_online = False
    partner_status = ''
    pinned_msg = None
    with_user = request.args.get('with')
    if with_user:
        partner = User.get_by_username(with_user)
        if partner:
            messages = Message.get_conversation(u['id'], partner['id'])
            # подгружаем реакции для каждого сообщения
            messages = [dict(m) for m in messages]
            for m in messages:
                m['reactions'] = [{'emoji': r['emoji'], 'count': r['cnt']} for r in Message.get_reactions(m['id'])]
            Message.mark_read(partner['id'], u['id'])
            # онлайн-статус партнёра
            partner_online = is_online(partner)
            if partner_online:
                partner_status = 'в сети'
            elif partner['last_seen']:
                partner_status = f'был(а) {time_ago(partner["last_seen"])}'
            else:
                partner_status = 'был(а) недавно'
            # закреплённое сообщение
            pinned_msg = Message.get_pinned(u['id'], partner['id'])
    return render_template('chat.html', dialogs=dialogs, partner=partner, messages=messages,
                           partner_online=partner_online, partner_status=partner_status,
                           pinned_msg=pinned_msg)


@app.route('/chat/send', methods=['POST'])
@login_required
@limiter.limit("30/minute")
def send_message():
    u = current_user()
    rid = request.form.get('receiver_id', type=int)
    content = request.form.get('content', '').strip()
    msg_type = request.form.get('msg_type', 'text')
    file = request.files.get('file')
    duration = request.form.get('duration', type=int) or 0

    if not rid:
        return jsonify({'error': 'Нет получателя'}), 400
    if not User.get(rid):
        return jsonify({'error': 'Не найдено'}), 404

    file_url = None
    file_name = None
    file_size = 0

    # Если есть файл — определяем тип и сохраняем
    if file and file.filename:
        if msg_type == 'text':
            # авто-определение типа по расширению
            fn = file.filename.lower()
            if fn.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                msg_type = 'image'
            elif fn.endswith(('.mp4', '.webm', '.mov', '.avi')):
                msg_type = 'video'
            elif fn.endswith(('.mp3', '.wav', '.ogg', '.m4a', '.aac')):
                msg_type = 'audio'
            else:
                msg_type = 'file'
        prefix = {'image': 'img', 'video': 'vid', 'audio': 'voice', 'file': 'file'}.get(msg_type, 'file')
        file_url = save_file(file, prefix)
        file_name = file.filename
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        if not content:
            content = {'image': '🖼️ Фото', 'video': '🎬 Видео', 'audio': '🎤 Голосовое', 'file': '📎 Файл'}.get(msg_type, 'Файл')

    if not content and not file_url:
        return jsonify({'error': 'Пусто'}), 400

    reply_to_id = request.form.get('reply_to_id', type=int) or None
    msg = Message.create(u['id'], rid, content, msg_type=msg_type,
                         file_url=file_url, file_name=file_name, file_size=file_size, duration=duration,
                         reply_to_id=reply_to_id)
    data = {
        'id': msg['id'], 'content': msg['content'], 'msg_type': msg['msg_type'],
        'file_url': msg['file_url'], 'file_name': msg['file_name'],
        'file_size': msg['file_size'], 'duration': msg['duration'],
        'sender_id': msg['sender_id'], 'receiver_id': msg['receiver_id'],
        'time': time_ago(msg['created_at']),
        'sender_username': u['username'], 'sender_avatar': u['avatar'],
        'file_url_full': (_media_for(msg['file_url']) if msg['file_url'] else None),
        'reply_to_id': msg['reply_to_id'] if 'reply_to_id' in msg.keys() else None,
        'reply_to_content': None,
        'is_read': msg['is_read'] if 'is_read' in msg.keys() else 0,
        'edited_at': msg['edited_at'] if 'edited_at' in msg.keys() else None,
    }
    # Добавляем текст ответа для превью
    if data['reply_to_id']:
        rm = Message.get(data['reply_to_id'])
        if rm:
            data['reply_to_content'] = rm['content'][:80]
    socketio.emit('new_message', data, room=f'user_{rid}')
    socketio.emit('new_message', data, room=f'user_{u["id"]}')
    # Web Push получателю если он офлайн
    receiver = User.get(rid)
    if receiver and rid != u['id'] and not is_online(receiver):
        import threading
        threading.Thread(target=send_push, args=(
            rid, f'{u["display_name"] or u["username"]}',
            (content or 'Новое сообщение')[:100],
            url_for('chat', partner_id=u['id'], _external=False)
        ), daemon=True).start()
    return jsonify(data)


@app.route('/chat/<int:mid>/delete', methods=['POST'])
@login_required
def delete_message(mid):
    m = Message.get(mid)
    if not m:
        return jsonify({'error': 'Не найдено'}), 404
    receiver = m['receiver_id']
    sender = m['sender_id']
    if not Message.delete(mid, session['user_id']):
        return jsonify({'error': 'Нет прав'}), 403
    socketio.emit('message_deleted', {'id': mid}, room=f'user_{receiver}')
    socketio.emit('message_deleted', {'id': mid}, room=f'user_{sender}')
    return jsonify({'ok': True})


@app.route('/chat/<int:mid>/edit', methods=['POST'])
@login_required
@limiter.limit("20/minute")
def edit_message(mid):
    """Редактирование сообщения (только текст, в течение 15 минут)."""
    content = request.form.get('content', '').strip()
    if not content:
        return jsonify({'error': 'Пусто'}), 400
    m = Message.get(mid)
    if not m:
        return jsonify({'error': 'Не найдено'}), 404
    if not Message.edit(mid, session['user_id'], content):
        return jsonify({'error': 'Нельзя редактировать (прошло >15 мин или нет прав)'}), 403
    data = {'id': mid, 'content': content, 'edited': True}
    socketio.emit('message_edited', data, room=f'user_{m["receiver_id"]}')
    socketio.emit('message_edited', data, room=f'user_{m["sender_id"]}')
    return jsonify(data)


@app.route('/chat/<int:partner_id>/read', methods=['POST'])
@login_required
def mark_chat_read(partner_id):
    """Отметить переписку с partner_id как прочитанную."""
    Message.mark_read(partner_id, session['user_id'])
    socketio.emit('messages_read', {'reader_id': session['user_id']}, room=f'user_{partner_id}')
    return jsonify({'ok': True})


@app.route('/chat/<int:mid>/react', methods=['POST'])
@login_required
@limiter.limit("40/minute")
def react_message(mid):
    m = Message.get(mid)
    if not m:
        return jsonify({'error': 'Не найдено'}), 404
    emoji = (request.get_json(silent=True) or {}).get('emoji', '').strip()
    if not emoji or len(emoji) > 8:
        return jsonify({'error': 'Некорректная реакция'}), 400
    added = Message.toggle_reaction(mid, session['user_id'], emoji)
    reactions = [{'emoji': r['emoji'], 'count': r['cnt']} for r in Message.get_reactions(mid)]
    data = {'id': mid, 'reactions': reactions}
    socketio.emit('message_reaction', data, room=f'user_{m["receiver_id"]}')
    socketio.emit('message_reaction', data, room=f'user_{m["sender_id"]}')
    return jsonify(data)


@app.route('/chat/<int:partner_id>/search')
@login_required
def search_chat_messages(partner_id):
    """Поиск по тексту сообщений в переписке."""
    q = request.args.get('q', '').strip()
    if not q or not User.get(partner_id):
        return jsonify({'results': []})
    results = Message.search(session['user_id'], partner_id, q)
    return jsonify({'results': [{'id': r['id'], 'content': r['content'][:120],
                                  'time': time_ago(r['created_at']),
                                  'sender_id': r['sender_id']} for r in results]})


@app.route('/chat/<int:mid>/forward', methods=['POST'])
@login_required
@limiter.limit("20/minute")
def forward_message(mid):
    """Переслать сообщение другому пользователю."""
    to_uid = (request.get_json(silent=True) or {}).get('to_user_id')
    if not to_uid or not User.get(to_uid):
        return jsonify({'error': 'Получатель не найден'}), 400
    new_msg = Message.forward(mid, to_uid, session['user_id'])
    if not new_msg:
        return jsonify({'error': 'Не удалось переслать'}), 400
    u = current_user()
    data = {
        'id': new_msg['id'], 'content': new_msg['content'], 'msg_type': new_msg['msg_type'],
        'file_url': new_msg['file_url'], 'file_name': new_msg['file_name'],
        'file_size': new_msg['file_size'], 'duration': new_msg['duration'],
        'sender_id': new_msg['sender_id'], 'receiver_id': new_msg['receiver_id'],
        'time': time_ago(new_msg['created_at']),
        'sender_username': u['username'], 'sender_avatar': u['avatar'],
        'file_url_full': _media_for(new_msg['file_url']) if new_msg['file_url'] else None,
        'forwarded_from_name': new_msg['forwarded_from_name'] if 'forwarded_from_name' in new_msg.keys() else None,
    }
    socketio.emit('new_message', data, room=f'user_{to_uid}')
    socketio.emit('new_message', data, room=f'user_{session["user_id"]}')
    return jsonify({'ok': True, 'id': new_msg['id']})


@app.route('/chat/<int:mid>/pin', methods=['POST'])
@login_required
def pin_message(mid):
    """Закрепить/открепить сообщение в диалоге."""
    pinned = Message.toggle_pin(mid, session['user_id'])
    m = Message.get(mid)
    if m:
        data = {'id': mid, 'pinned': pinned}
        socketio.emit('message_pinned', data, room=f'user_{m["receiver_id"]}')
        socketio.emit('message_pinned', data, room=f'user_{m["sender_id"]}')
    return jsonify({'ok': True, 'pinned': pinned})


# ==================== УВЕДОМЛЕНИЯ ====================
@app.route('/notifications')
@login_required
def notifications():
    ns = Notification.get_all(session['user_id'])
    Notification.mark_all_read(session['user_id'])
    return render_template('notifications.html', notifications=ns)


# ==================== ЖАЛОБЫ ====================
@app.route('/report', methods=['POST'])
@login_required
@limiter.limit("5/minute")
def report():
    data = request.get_json(silent=True) or {}
    target_type = data.get('target_type', '')
    target_id = data.get('target_id')
    reason = (data.get('reason') or '')[:500]
    if target_type not in ('post', 'user', 'message') or not target_id:
        return jsonify({'error': 'Некорректный запрос'}), 400
    Report.create(session['user_id'], target_type, int(target_id), reason)
    return jsonify({'ok': True})


# ==================== АДМИН-ПАНЕЛЬ ====================
@app.route('/admin')
@admin_required
def admin():
    tab = request.args.get('tab', 'stats')
    db = get_db()
    stats = {
        'users': db.execute('SELECT COUNT(*) c FROM users').fetchone()['c'],
        'posts': db.execute('SELECT COUNT(*) c FROM posts').fetchone()['c'],
        'comments': db.execute('SELECT COUNT(*) c FROM comments').fetchone()['c'],
        'messages': db.execute('SELECT COUNT(*) c FROM messages').fetchone()['c'],
        'likes': db.execute('SELECT COUNT(*) c FROM likes').fetchone()['c'],
        'verified': db.execute('SELECT COUNT(*) c FROM users WHERE verified=1').fetchone()['c'],
        'banned': db.execute('SELECT COUNT(*) c FROM users WHERE banned=1').fetchone()['c'],
        'private': db.execute('SELECT COUNT(*) c FROM users WHERE is_private=1').fetchone()['c'],
        'reports': db.execute('SELECT COUNT(*) c FROM reports WHERE status="pending"').fetchone()['c'],
    }
    top_users = db.execute('''
        SELECT u.*, (SELECT COUNT(*) FROM posts WHERE user_id=u.id) as post_count
        FROM users u ORDER BY post_count DESC LIMIT 5
    ''').fetchall()
    all_users = User.get_all()
    all_posts, _ = Post.get_all(page=1, per_page=200)
    reports = Report.get_all(status='pending') if tab == 'reports' else None
    return render_template('admin.html', tab=tab, stats=stats, top_users=top_users,
                           all_users=all_users, all_posts=all_posts, reports=reports)


@app.route('/admin/user/<int:uid>/ban', methods=['POST'])
@admin_required
def admin_ban(uid):
    u = User.get(uid)
    if not u or u['role'] == 'admin':
        return jsonify({'error': 'Нельзя'}), 400
    db = get_db()
    db.execute('UPDATE users SET banned = 1 - banned WHERE id = ?', (uid,))
    db.commit()
    u = User.get(uid)
    return jsonify({'banned': bool(u['banned'])})


@app.route('/admin/user/<int:uid>/verify', methods=['POST'])
@admin_required
def admin_verify(uid):
    u = User.get(uid)
    if not u:
        return jsonify({'error': 'Не найдено'}), 404
    db = get_db()
    db.execute('UPDATE users SET verified = 1 - verified WHERE id = ?', (uid,))
    db.commit()
    u = User.get(uid)
    return jsonify({'verified': bool(u['verified'])})


@app.route('/admin/user/<int:uid>/role', methods=['POST'])
@admin_required
def admin_role(uid):
    u = User.get(uid)
    if not u or u['role'] == 'admin':
        return jsonify({'error': 'Нельзя'}), 400
    db = get_db()
    db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (uid,))
    db.commit()
    return jsonify({'ok': True})


@app.route('/admin/settings', methods=['POST'])
@admin_required
def admin_settings_save():
    for key in ['site_name', 'site_desc', 'max_post_length']:
        val = request.form.get(key)
        if val is not None:
            SiteSettings.set(key, val)
    SiteSettings.set('allow_registration', '1' if request.form.get('allow_registration') else '0')
    SiteSettings.set('maintenance_mode', '1' if request.form.get('maintenance_mode') else '0')
    flash('Настройки сохранены', 'success')
    return redirect(url_for('admin', tab='system'))


@app.route('/admin/report/<int:rid>/resolve', methods=['POST'])
@admin_required
def admin_resolve_report(rid):
    Report.resolve(rid)
    return jsonify({'ok': True})


@app.route('/admin/post/<int:pid>/delete', methods=['POST'])
@admin_required
def admin_delete_post(pid):
    if Post.delete(pid, 0, force=True):
        return jsonify({'ok': True})
    return jsonify({'error': 'Не найдено'}), 404


# ==================== WEBSOCKET ====================
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        join_room(f'user_{session["user_id"]}')


@socketio.on('typing')
def handle_typing(data):
    """Индикатор «печатает»: шлём получателю."""
    if 'user_id' not in session:
        return
    to = (data or {}).get('to')
    if to:
        emit('typing', {'from': session['user_id']}, room=f'user_{to}')


@socketio.on('stop_typing')
def handle_stop_typing(data):
    if 'user_id' not in session:
        return
    to = (data or {}).get('to')
    if to:
        emit('stop_typing', {'from': session['user_id']}, room=f'user_{to}')


# ==================== ГРУППОВЫЕ ЧАТЫ ====================
@socketio.on('group_join')
def handle_group_join(data):
    """Вступить в комнату группы (для realtime-сообщений)."""
    if 'user_id' not in session:
        return
    gid = (data or {}).get('group_id')
    if gid and Group.is_member(gid, session['user_id']):
        join_room(f'group_{gid}')


@socketio.on('group_typing')
def handle_group_typing(data):
    if 'user_id' not in session:
        return
    gid = (data or {}).get('group_id')
    if gid and Group.is_member(gid, session['user_id']):
        emit('group_typing', {'from': session['user_id'],
                              'name': (data or {}).get('name', '')},
             room=f'group_{gid}', include_self=False)


@socketio.on('group_stop_typing')
def handle_group_stop_typing(data):
    if 'user_id' not in session:
        return
    gid = (data or {}).get('group_id')
    if gid:
        emit('group_stop_typing', {'from': session['user_id']},
             room=f'group_{gid}', include_self=False)


# ==================== ГОЛОСОВЫЕ КОМНАТЫ (Discord-like) ====================
# Полностью peer-to-peer mesh через WebRTC. Сервер только маршрутизирует
# сигналинг между участниками комнаты.
@socketio.on('voice_join')
def handle_voice_join(data):
    """Пользователь входит в голосовую комнату — оповещаем всех в комнате."""
    if 'user_id' not in session:
        return
    room_id = (data or {}).get('room_id')
    if not room_id:
        return
    room = VoiceRoom.get(room_id)
    if not room:
        return
    if not Group.is_member(room['group_id'], session['user_id']):
        return
    VoiceRoom.join(room_id, session['user_id'])
    room_key = f'voice_{room_id}'
    join_room(room_key)
    # Говорим остальным, что новичок хочет подключиться — они инициируют offer
    emit('voice_user_joined', {
        'user_id': session['user_id'],
        'name': (data or {}).get('name', ''),
    }, room=room_key, include_self=False)
    # Шлём новичку список уже присутствующих (чтобы он знал, к кому подключаться)
    peers = VoiceRoom.get_participants(room_id)
    emit('voice_peers', {
        'peers': [{'user_id': p['user_id']} for p in peers if p['user_id'] != session['user_id']],
    })


@socketio.on('voice_leave')
def handle_voice_leave(data):
    if 'user_id' not in session:
        return
    room_id = (data or {}).get('room_id')
    if not room_id:
        return
    VoiceRoom.leave(room_id, session['user_id'])
    leave_room(f'voice_{room_id}')
    emit('voice_user_left', {'user_id': session['user_id']},
         room=f'voice_{room_id}', include_self=False)


@socketio.on('voice_signal')
def handle_voice_signal(data):
    """Маршрутизация WebRTC сигналинга между двумя пирами в голосовой комнате.
    Peer-to-peer: один участник шлёт offer/answer/candidate другому напрямую."""
    if 'user_id' not in session:
        return
    to = (data or {}).get('to')
    if not to:
        return
    emit('voice_signal', {
        'from': session['user_id'],
        'signal': (data or {}).get('signal'),
    }, room=f'user_{to}')


@socketio.on('voice_mute')
def handle_voice_mute(data):
    """Оповещение об изменении состояния микрофона."""
    if 'user_id' not in session:
        return
    room_id = (data or {}).get('room_id')
    muted = bool((data or {}).get('muted'))
    if room_id:
        VoiceRoom.set_muted(room_id, session['user_id'], muted)
        emit('voice_mute_changed', {
            'user_id': session['user_id'], 'muted': muted,
        }, room=f'voice_{room_id}', include_self=False)


# ==================== ВЕБ-ЗВОНКИ (WebRTC сигналинг) ====================
def _call_peer(data):
    """Достаём адресата из payload и проверяем сессию."""
    if 'user_id' not in session:
        return None
    to = (data or {}).get('to')
    return to if to else None


@socketio.on('call_offer')
def handle_call_offer(data):
    """Инициатор звонка шлёт offer (SDP) получателю."""
    to = _call_peer(data)
    if to:
        emit('call_offer', {
            'from': session['user_id'],
            'from_name': (data or {}).get('from_name', ''),
            'video': (data or {}).get('video', False),
            'sdp': (data or {}).get('sdp'),
        }, room=f'user_{to}')


@socketio.on('call_answer')
def handle_call_answer(data):
    """Ответ принимающей стороны (SDP)."""
    to = _call_peer(data)
    if to:
        emit('call_answer', {
            'from': session['user_id'],
            'sdp': (data or {}).get('sdp'),
        }, room=f'user_{to}')


@socketio.on('call_ice')
def handle_call_ice(data):
    """Обмен ICE-кандидатами (NAT traversal)."""
    to = _call_peer(data)
    if to:
        emit('call_ice', {
            'from': session['user_id'],
            'candidate': (data or {}).get('candidate'),
        }, room=f'user_{to}')


@socketio.on('call_end')
def handle_call_end(data):
    """Сброс звонка любой из сторон."""
    to = _call_peer(data)
    if to:
        emit('call_end', {'from': session['user_id']}, room=f'user_{to}')


@socketio.on('call_reject')
def handle_call_reject(data):
    """Отклонение входящего звонка."""
    to = _call_peer(data)
    if to:
        emit('call_reject', {'from': session['user_id']}, room=f'user_{to}')


# ==================== ИСТОРИИ (Stories) ====================

@app.route('/story/create', methods=['POST'])
@login_required
@limiter.limit("20/hour")
def create_story():
    """Создать историю (фото или видео)."""
    file = request.files.get('media')
    caption = request.form.get('caption', '').strip()[:300]
    if not file or not file.filename:
        return jsonify({'error': 'Выберите фото или видео'}), 400
    media_type = 'image' if file.content_type and file.content_type.startswith('image/') else 'video'
    media_path = save_file(file, 'story')
    if not media_path:
        return jsonify({'error': 'Неподдерживаемый формат'}), 400
    story = Story.create(session['user_id'], media_path, media_type, caption or None)
    return jsonify({'ok': True, 'id': story['id'], 'media': media_path, 'media_type': media_type})


@app.route('/api/user/id')
@login_required
def api_user_id():
    """Возвращает id пользователя по username (для пересылки и т.д.)."""
    username = request.args.get('username', '').strip()
    if not username:
        return jsonify({'error': 'no username'}), 400
    u = User.get_by_username(username)
    if not u:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'id': u['id'], 'username': u['username']})


@app.route('/api/stories')
@login_required
def api_stories():
    """JSON: активные истории (для кольца в ленте)."""
    Story.cleanup_expired()
    groups = Story.get_active_for_user(session['user_id'])
    # Добавляем свою историю первым (если есть)
    my_stories = Story.get_user_stories(session['user_id'])
    if my_stories and (not groups or groups[0]['user_id'] != session['user_id']):
        me = current_user()
        stories_list = []
        for st in my_stories:
            stories_list.append({
                'id': st['id'], 'media': st['media'], 'media_type': st['media_type'],
                'caption': st['caption'], 'created_at': st['created_at'], 'seen': True,
            })
        groups.insert(0, {
            'user_id': session['user_id'],
            'username': me['username'],
            'display_name': me['display_name'],
            'avatar': me['avatar'],
            'verified': me['verified'] if 'verified' in me.keys() else 0,
            'stories': stories_list,
        })
    return jsonify({'groups': groups})


@app.route('/story/<int:sid>/view', methods=['POST'])
@login_required
def view_story(sid):
    """Отметить историю как просмотренную."""
    StoryView.record(sid, session['user_id'])
    count = StoryView.count(sid)
    return jsonify({'ok': True, 'views': count})


@app.route('/story/<int:sid>/delete', methods=['POST'])
@login_required
def delete_story(sid):
    """Удалить свою историю."""
    if Story.delete(sid, session['user_id']):
        return jsonify({'ok': True})
    return jsonify({'error': 'Не найдена'}), 404


@app.route('/story/<int:sid>/viewers')
@login_required
def story_viewers(sid):
    """Список просмотревших."""
    s = Story.get(sid)
    if not s:
        return jsonify({'error': 'Не найдена'}), 404
    return jsonify({'viewers': [
        {'id': v['id'], 'username': v['username'], 'display_name': v['display_name'],
         'avatar': v['avatar'], 'verified': v['verified']}
        for v in StoryView.viewers(sid)
    ]})


# ==================== 404 ====================
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Страница не найдена'), 404


@app.errorhandler(429)
def ratelimit_handler(e):
    if request.path.startswith('/post/') or request.path.startswith('/chat/') or request.path == '/report':
        return jsonify({'error': 'Слишком много запросов. Подождите немного.'}), 429
    flash('Слишком много попыток. Подождите минуту.', 'error')
    return redirect(request.referrer or url_for('login'))


# ==================== БЭКАП/ВОССТАНОВЛЕНИЕ (админ) ====================
@app.route('/admin/backup', methods=['POST'])
@login_required
def admin_backup_route():
    """Ручной бэкап БД в JSON (только админ)."""
    u = current_user()
    if u['role'] != 'admin':
        return jsonify({'error': 'Доступ запрещён'}), 403
    backup_db_to_json()
    return jsonify({'ok': True, 'msg': 'Бэкап создан'})


@app.route('/admin/restore', methods=['POST'])
@login_required
def admin_restore_route():
    """Ручное восстановление из бэкапа (только админ)."""
    u = current_user()
    if u['role'] != 'admin':
        return jsonify({'error': 'Доступ запрещён'}), 403
    restored = restore_db_from_json()
    return jsonify({'ok': restored, 'msg': 'Восстановлено' if restored else 'Бэкап не найден или БД не пустая'})


# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0',
                 port=int(os.environ.get('PORT', 5050)),
                 allow_unsafe_werkzeug=True)
