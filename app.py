"""ZSocial — социальная сеть. Production версия с чатом, закладками, хештегами, админкой."""
import os
import re
from functools import wraps
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
from flask_socketio import SocketIO, emit, join_room
from werkzeug.utils import secure_filename
import uuid

from config import Config
from models import (
    init_db, migrate_db, get_db, close_db, can_view_profile, render_text_content,
    User, Post, Like, Comment, Bookmark, Follow, Message, Notification, SiteSettings
)

app = Flask(__name__)
app.config.from_object(Config)
# gevent для production (gunicorn), threading как fallback для локали
try:
    import gevent  # noqa
    _async = 'gevent'
except ImportError:
    _async = 'threading'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=_async)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.teardown_appcontext(close_db)

# Версия приложения — для cache-busting статики (каждый деплой = новый хэш)
APP_VERSION = os.environ.get('RENDER_GIT_COMMIT', 'dev')[:8] or str(int(__import__('time').time()))


@app.after_request
def no_cache_dynamic(resp):
    """Запрещаем кэширование HTML страниц — чтобы после деплоя был свежий контент."""
    if 'text/html' in (resp.headers.get('Content-Type') or ''):
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
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
    _seed_if_empty()


# ==================== ХЕЛПЕРЫ ====================
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
    if u and u['banned']:
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


@app.context_processor
def inject_globals():
    u = current_user()
    notifs = msgs = 0
    site = SiteSettings.get_all()
    if u:
        notifs = Notification.unread_count(u['id'])
        msgs = Message.unread_count(u['id'])
    return dict(cu=u, unread_notifs=notifs, unread_msgs=msgs,
                site_name=site.get('site_name', 'ZSocial'),
                site_desc=site.get('site_desc', ''),
                site=site,
                v=APP_VERSION)


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
        flash(f'Добро пожаловать, {un}!', 'success')
        return redirect(url_for('feed'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
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
            flash(f'С возвращением, {u["username"]}!', 'success')
            return redirect(url_for('feed'))
        flash('Неверные данные', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли', 'success')
    return redirect(url_for('login'))


# ==================== ЛЕНТА ====================
@app.route('/feed')
@login_required
def feed():
    tab = request.args.get('tab', 'all')
    tag = request.args.get('tag', '').strip()
    if tab == 'following':
        posts = Post.get_following_feed(session['user_id'], tag=tag or None)
    else:
        posts = Post.get_all(tag=tag or None)
    liked = {p['id'] for p in posts if Like.is_liked(session['user_id'], p['id'])}
    saved_ids = {b['id'] for b in Bookmark.get_by_user(session['user_id'])}
    return render_template('feed.html', posts=posts, liked_posts=liked, saved_posts=saved_ids, tab=tab, tag=tag)


@app.route('/post/create', methods=['POST'])
@login_required
def create_post():
    content = request.form.get('content', '').strip()
    image = request.files.get('image')
    if not content and (not image or not image.filename):
        flash('Пост пуст', 'error')
        return redirect(url_for('feed'))
    img_path = save_file(image, 'post') if image else None
    Post.create(session['user_id'], content, img_path)
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


@app.route('/post/<int:pid>/like', methods=['POST'])
@login_required
def toggle_like(pid):
    post = Post.get(pid)
    if not post:
        return jsonify({'error': 'Не найдено'}), 404
    liked = Like.toggle(session['user_id'], pid)
    if liked:
        Notification.create(post['user_id'], session['user_id'], 'like', pid)
    return jsonify({'liked': liked, 'count': Like.count(pid)})


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
    c = Comment.create(session['user_id'], pid, content)
    Notification.create(post['user_id'], session['user_id'], 'comment', pid)
    return jsonify({
        'id': c['id'], 'content': c['content'], 'username': c['username'],
        'avatar': c['avatar'], 'verified': c['verified'],
        'time': time_ago(c['created_at'])
    })


@app.route('/post/<int:pid>/comments')
@login_required
def get_comments(pid):
    return jsonify([{
        'id': c['id'], 'content': c['content'], 'username': c['username'],
        'avatar': c['avatar'], 'verified': c['verified'],
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
    liked = {p['id'] for p in posts if Like.is_liked(session['user_id'], p['id'])}
    saved_ids = {b['id'] for b in Bookmark.get_by_user(session['user_id'])}
    return render_template('profile.html', pu=u, posts=posts, liked_posts=liked,
                           saved_posts=saved_ids, can_view=can_view,
                           followers_count=Follow.followers_count(u['id']),
                           following_count=Follow.following_count(u['id']),
                           is_following=Follow.is_following(session['user_id'], u['id']),
                           is_own=u['id'] == session['user_id'])


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
                    is_private=1 if request.form.get('is_private') else 0)
        flash('Сохранено', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html')


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
    return jsonify({'following': f, 'count': Follow.followers_count(uid)})


# ==================== ПОИСК / ЛЮДИ ====================
@app.route('/people')
@login_required
def people():
    q = request.args.get('q', '')
    users = User.search(q) if q else [x for x in User.get_all() if x['id'] != session['user_id'] and x['banned'] == 0]
    following_ids = {f['followed_id'] for f in Follow.get_following(session['user_id'])}
    return render_template('people.html', users=users, following_ids=following_ids, q=q)


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
    with_user = request.args.get('with')
    if with_user:
        partner = User.get_by_username(with_user)
        if partner:
            messages = Message.get_conversation(u['id'], partner['id'])
            Message.mark_read(partner['id'], u['id'])
    return render_template('chat.html', dialogs=dialogs, partner=partner, messages=messages)


@app.route('/chat/send', methods=['POST'])
@login_required
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

    msg = Message.create(u['id'], rid, content, msg_type=msg_type,
                         file_url=file_url, file_name=file_name, file_size=file_size, duration=duration)
    data = {
        'id': msg['id'], 'content': msg['content'], 'msg_type': msg['msg_type'],
        'file_url': msg['file_url'], 'file_name': msg['file_name'],
        'file_size': msg['file_size'], 'duration': msg['duration'],
        'sender_id': msg['sender_id'], 'receiver_id': msg['receiver_id'],
        'time': time_ago(msg['created_at']),
        'sender_username': u['username'], 'sender_avatar': u['avatar'],
        'file_url_full': (url_for('static', filename=msg['file_url']) if msg['file_url'] else None),
    }
    socketio.emit('new_message', data, room=f'user_{rid}')
    socketio.emit('new_message', data, room=f'user_{u["id"]}')
    return jsonify(data)


# ==================== УВЕДОМЛЕНИЯ ====================
@app.route('/notifications')
@login_required
def notifications():
    ns = Notification.get_all(session['user_id'])
    Notification.mark_all_read(session['user_id'])
    return render_template('notifications.html', notifications=ns)


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
    }
    top_users = db.execute('''
        SELECT u.*, (SELECT COUNT(*) FROM posts WHERE user_id=u.id) as post_count
        FROM users u ORDER BY post_count DESC LIMIT 5
    ''').fetchall()
    all_users = User.get_all()
    all_posts = Post.get_all(limit=200)
    return render_template('admin.html', tab=tab, stats=stats, top_users=top_users,
                           all_users=all_users, all_posts=all_posts)


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


# ==================== WEBSOCKET ====================
@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        join_room(f'user_{session["user_id"]}')


# ==================== 404 ====================
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Страница не найдена'), 404


# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0',
                 port=int(os.environ.get('PORT', 5050)),
                 allow_unsafe_werkzeug=True)
