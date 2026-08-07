"""Модели базы данных ZSocial (Pro версия)."""
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config


def get_db():
    from flask import g
    if 'db' not in g:
        g.db = sqlite3.connect(Config.DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(e=None):
    from flask import g
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(Config.DATABASE) or '.', exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE)
    conn.execute('PRAGMA foreign_keys = ON')

    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        display_name TEXT DEFAULT '',
        bio TEXT DEFAULT '',
        status TEXT DEFAULT '',
        avatar TEXT DEFAULT 'img/default_avatar.svg',
        cover TEXT DEFAULT 'img/default_cover.svg',
        role TEXT DEFAULT 'user',
        verified INTEGER DEFAULT 0,
        is_private INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        image TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, post_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        post_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, post_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS follows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        follower_id INTEGER NOT NULL,
        followed_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(follower_id, followed_id),
        FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (followed_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        msg_type TEXT DEFAULT 'text',
        file_url TEXT,
        file_name TEXT,
        file_size INTEGER DEFAULT 0,
        duration INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_read INTEGER DEFAULT 0,
        FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        actor_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        post_id INTEGER,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    ''')

    # Настройки по умолчанию
    defaults = {
        'site_name': 'ZSocial',
        'site_desc': 'Профессиональная сеть нового поколения',
        'allow_registration': '1',
        'maintenance_mode': '0',
        'max_post_length': '500'
    }
    for k, v in defaults.items():
        conn.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))

    conn.commit()
    conn.close()


def migrate_db():
    """Добавляет новые колонки, если БД уже существует (миграция)."""
    conn = sqlite3.connect(Config.DATABASE)
    # Проверяем и добавляем недостающие колонки в messages
    cols = [r[1] for r in conn.execute('PRAGMA table_info(messages)').fetchall()]
    new_cols = {
        'msg_type': 'TEXT DEFAULT "text"',
        'file_url': 'TEXT',
        'file_name': 'TEXT',
        'file_size': 'INTEGER DEFAULT 0',
        'duration': 'INTEGER DEFAULT 0',
    }
    for col, typedef in new_cols.items():
        if col not in cols:
            conn.execute(f'ALTER TABLE messages ADD COLUMN {col} {typedef}')
    # Проверяем колонки users (verified, is_private, banned, role)
    ucols = [r[1] for r in conn.execute('PRAGMA table_info(users)').fetchall()]
    user_new = {
        'role': 'TEXT DEFAULT "user"',
        'verified': 'INTEGER DEFAULT 0',
        'is_private': 'INTEGER DEFAULT 0',
        'banned': 'INTEGER DEFAULT 0',
    }
    for col, typedef in user_new.items():
        if col not in ucols:
            conn.execute(f'ALTER TABLE users ADD COLUMN {col} {typedef}')
    # bookmarks таблица (если старая БД)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if 'bookmarks' not in tables:
        conn.execute('''CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, post_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )''')
    if 'settings' not in tables:
        conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    conn.commit()
    conn.close()


# ==================== УТИЛИТЫ ====================
def can_view_profile(viewer_id, profile_user):
    """Может ли зритель видеть приватный профиль."""
    if not profile_user:
        return False
    if profile_user['is_private'] == 0:
        return True
    if viewer_id == profile_user['id']:
        return True
    if profile_user['role'] == 'admin':
        return True
    db = get_db()
    f = db.execute(
        'SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?',
        (viewer_id, profile_user['id'])
    ).fetchone()
    return f is not None


def render_text_content(text):
    """Превращает #хештеги в кликабельные ссылки (HTML экранирование)."""
    import html
    import re
    escaped = html.escape(text or '')
    return re.sub(
        r'#([\wа-яёА-ЯЁ]+)',
        r'<span class="hashtag" onclick="searchTag(\'\1\')">#\1</span>',
        escaped
    )


# ==================== МОДЕЛИ ====================
class User:
    @staticmethod
    def create(username, email, password):
        db = get_db()
        db.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (username, email, generate_password_hash(password))
        )
        db.commit()
        return User.get_by_username(username)

    @staticmethod
    def get(uid):
        db = get_db()
        return db.execute('SELECT * FROM users WHERE id = ?', (uid,)).fetchone()

    @staticmethod
    def get_by_username(uname):
        db = get_db()
        return db.execute('SELECT * FROM users WHERE username = ?', (uname,)).fetchone()

    @staticmethod
    def get_by_email(email):
        db = get_db()
        return db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()

    @staticmethod
    def verify(h, p):
        return check_password_hash(h, p)

    @staticmethod
    def update(uid, **kw):
        db = get_db()
        allowed = ['display_name', 'bio', 'status', 'avatar', 'cover', 'is_private']
        sets, vals = [], []
        for k in allowed:
            if k in kw:
                sets.append(f'{k} = ?')
                vals.append(kw[k])
        if sets:
            vals.append(uid)
            db.execute(f'UPDATE users SET {", ".join(sets)} WHERE id = ?', vals)
            db.commit()
        return User.get(uid)

    @staticmethod
    def search(q):
        db = get_db()
        return db.execute(
            'SELECT * FROM users WHERE (username LIKE ? OR display_name LIKE ?) AND banned = 0 ORDER BY username',
            (f'%{q}%', f'%{q}%')
        ).fetchall()

    @staticmethod
    def get_all():
        db = get_db()
        return db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()


class Post:
    @staticmethod
    def create(user_id, content, image=None):
        db = get_db()
        db.execute(
            'INSERT INTO posts (user_id, content, image) VALUES (?, ?, ?)',
            (user_id, content, image)
        )
        db.commit()
        return db.execute('SELECT * FROM posts WHERE id = last_insert_rowid()').fetchone()

    @staticmethod
    def get(pid):
        db = get_db()
        return db.execute('SELECT * FROM posts WHERE id = ?', (pid,)).fetchone()

    @staticmethod
    def _feed_where(extra=''):
        return f'''
            SELECT p.*, u.username, u.display_name, u.avatar, u.verified, u.role,
                   (SELECT COUNT(*) FROM likes WHERE post_id = p.id) as like_count,
                   (SELECT COUNT(*) FROM comments WHERE post_id = p.id) as comment_count
            FROM posts p JOIN users u ON p.user_id = u.id
            WHERE u.banned = 0 {extra}
            ORDER BY p.created_at DESC
        '''

    @staticmethod
    def get_all(limit=100, tag=None):
        db = get_db()
        if tag:
            return db.execute(Post._feed_where('AND LOWER(p.content) LIKE ?'), (f'%#{tag}%',)).fetchall()[:limit]
        return db.execute(Post._feed_where()).fetchall()[:limit]

    @staticmethod
    def get_following_feed(user_id, limit=100, tag=None):
        db = get_db()
        extra = 'AND (p.user_id IN (SELECT followed_id FROM follows WHERE follower_id = ?) OR p.user_id = ?)'
        if tag:
            extra += ' AND LOWER(p.content) LIKE ?'
            params = (user_id, user_id, f'%#{tag}%')
        else:
            params = (user_id, user_id)
        return db.execute(Post._feed_where(extra), params).fetchall()[:limit]

    @staticmethod
    def get_by_user(user_id):
        db = get_db()
        return db.execute(Post._feed_where('AND p.user_id = ?'), (user_id,)).fetchall()

    @staticmethod
    def delete(pid, uid, force=False):
        db = get_db()
        post = Post.get(pid)
        if post and (post['user_id'] == uid or force):
            db.execute('DELETE FROM posts WHERE id = ?', (pid,))
            db.commit()
            return True
        return False


class Like:
    @staticmethod
    def toggle(uid, pid):
        db = get_db()
        ex = db.execute('SELECT * FROM likes WHERE user_id=? AND post_id=?', (uid, pid)).fetchone()
        if ex:
            db.execute('DELETE FROM likes WHERE user_id=? AND post_id=?', (uid, pid))
            db.commit(); return False
        db.execute('INSERT INTO likes (user_id, post_id) VALUES (?, ?)', (uid, pid))
        db.commit(); return True

    @staticmethod
    def is_liked(uid, pid):
        db = get_db()
        return db.execute('SELECT 1 FROM likes WHERE user_id=? AND post_id=?', (uid, pid)).fetchone() is not None

    @staticmethod
    def count(pid):
        db = get_db()
        return db.execute('SELECT COUNT(*) c FROM likes WHERE post_id=?', (pid,)).fetchone()['c']


class Comment:
    @staticmethod
    def create(uid, pid, content):
        db = get_db()
        db.execute('INSERT INTO comments (user_id, post_id, content) VALUES (?, ?, ?)', (uid, pid, content))
        db.commit()
        c = db.execute('SELECT * FROM comments WHERE id = last_insert_rowid()').fetchone()
        u = User.get(uid)
        return {**dict(c), 'username': u['username'], 'avatar': u['avatar'], 'verified': u['verified']}

    @staticmethod
    def get_by_post(pid):
        db = get_db()
        return db.execute('''
            SELECT c.*, u.username, u.avatar, u.verified
            FROM comments c JOIN users u ON c.user_id = u.id
            WHERE c.post_id = ? ORDER BY c.created_at ASC
        ''', (pid,)).fetchall()


class Bookmark:
    @staticmethod
    def toggle(uid, pid):
        db = get_db()
        ex = db.execute('SELECT * FROM bookmarks WHERE user_id=? AND post_id=?', (uid, pid)).fetchone()
        if ex:
            db.execute('DELETE FROM bookmarks WHERE user_id=? AND post_id=?', (uid, pid))
            db.commit(); return False
        db.execute('INSERT INTO bookmarks (user_id, post_id) VALUES (?, ?)', (uid, pid))
        db.commit(); return True

    @staticmethod
    def get_by_user(uid):
        db = get_db()
        return db.execute('''
            SELECT p.*, u.username, u.display_name, u.avatar, u.verified, u.role,
                   (SELECT COUNT(*) FROM likes WHERE post_id=p.id) as like_count,
                   (SELECT COUNT(*) FROM comments WHERE post_id=p.id) as comment_count
            FROM bookmarks b
            JOIN posts p ON b.post_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE b.user_id = ?
            ORDER BY b.created_at DESC
        ''', (uid,)).fetchall()


class Follow:
    @staticmethod
    def toggle(follower_id, followed_id):
        if follower_id == followed_id:
            return None
        db = get_db()
        ex = db.execute('SELECT * FROM follows WHERE follower_id=? AND followed_id=?', (follower_id, followed_id)).fetchone()
        if ex:
            db.execute('DELETE FROM follows WHERE follower_id=? AND followed_id=?', (follower_id, followed_id))
            db.commit(); return False
        db.execute('INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)', (follower_id, followed_id))
        db.commit(); return True

    @staticmethod
    def is_following(a, b):
        db = get_db()
        return db.execute('SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?', (a, b)).fetchone() is not None

    @staticmethod
    def followers_count(uid):
        db = get_db()
        return db.execute('SELECT COUNT(*) c FROM follows WHERE followed_id=?', (uid,)).fetchone()['c']

    @staticmethod
    def following_count(uid):
        db = get_db()
        return db.execute('SELECT COUNT(*) c FROM follows WHERE follower_id=?', (uid,)).fetchone()['c']

    @staticmethod
    def get_following(uid):
        db = get_db()
        return db.execute('SELECT u.* FROM users u JOIN follows f ON u.id=f.followed_id WHERE f.follower_id=?', (uid,)).fetchall()


class Message:
    @staticmethod
    def create(s, r, content, msg_type='text', file_url=None, file_name=None, file_size=0, duration=0):
        db = get_db()
        db.execute('''INSERT INTO messages
            (sender_id, receiver_id, content, msg_type, file_url, file_name, file_size, duration)
            VALUES (?,?,?,?,?,?,?,?)''',
            (s, r, content, msg_type, file_url, file_name, file_size, duration))
        db.commit()
        return db.execute('SELECT * FROM messages WHERE id = last_insert_rowid()').fetchone()

    @staticmethod
    def get_conversation(a, b):
        db = get_db()
        return db.execute('''
            SELECT m.*, u.username, u.avatar, u.verified
            FROM messages m JOIN users u ON m.sender_id = u.id
            WHERE (m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?)
            ORDER BY m.created_at ASC
        ''', (a, b, b, a)).fetchall()

    @staticmethod
    def mark_read(sender, receiver):
        db = get_db()
        db.execute('UPDATE messages SET is_read=1 WHERE sender_id=? AND receiver_id=?', (sender, receiver))
        db.commit()

    @staticmethod
    def unread_count(uid):
        db = get_db()
        return db.execute('SELECT COUNT(*) c FROM messages WHERE receiver_id=? AND is_read=0', (uid,)).fetchone()['c']

    @staticmethod
    def get_dialogs(uid):
        db = get_db()
        rows = db.execute('''
            SELECT convos.other_id, u.username, u.display_name, u.avatar, u.verified,
                   (SELECT content FROM messages
                    WHERE (sender_id=convos.other_id AND receiver_id=?)
                       OR (sender_id=? AND receiver_id=convos.other_id)
                    ORDER BY created_at DESC LIMIT 1) AS last_msg,
                   (SELECT msg_type FROM messages
                    WHERE (sender_id=convos.other_id AND receiver_id=?)
                       OR (sender_id=? AND receiver_id=convos.other_id)
                    ORDER BY created_at DESC LIMIT 1) AS last_msg_type,
                   (SELECT created_at FROM messages
                    WHERE (sender_id=convos.other_id AND receiver_id=?)
                       OR (sender_id=? AND receiver_id=convos.other_id)
                    ORDER BY created_at DESC LIMIT 1) AS last_time,
                   (SELECT COUNT(*) FROM messages
                    WHERE sender_id=convos.other_id AND receiver_id=? AND is_read=0) AS unread
            FROM (
                SELECT CASE WHEN sender_id=? THEN receiver_id ELSE sender_id END AS other_id,
                       MAX(created_at) AS max_time
                FROM messages
                WHERE sender_id=? OR receiver_id=?
                GROUP BY other_id
            ) AS convos
            JOIN users u ON u.id = convos.other_id
            ORDER BY convos.max_time DESC
        ''', (uid, uid, uid, uid, uid, uid, uid, uid, uid, uid)).fetchall()
        return rows


class Notification:
    @staticmethod
    def create(uid, actor_id, type, post_id=None):
        if uid == actor_id:
            return None
        db = get_db()
        db.execute('INSERT INTO notifications (user_id, actor_id, type, post_id) VALUES (?,?,?,?)',
                   (uid, actor_id, type, post_id))
        db.commit()

    @staticmethod
    def unread_count(uid):
        db = get_db()
        return db.execute('SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0', (uid,)).fetchone()['c']

    @staticmethod
    def get_all(uid):
        db = get_db()
        return db.execute('''
            SELECT n.*, u.username, u.display_name, u.avatar, u.verified
            FROM notifications n JOIN users u ON n.actor_id = u.id
            WHERE n.user_id=? ORDER BY n.created_at DESC LIMIT 50
        ''', (uid,)).fetchall()

    @staticmethod
    def mark_all_read(uid):
        db = get_db()
        db.execute('UPDATE notifications SET is_read=1 WHERE user_id=?', (uid,))
        db.commit()


class SiteSettings:
    @staticmethod
    def get(key, default=None):
        db = get_db()
        r = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return r['value'] if r else default

    @staticmethod
    def get_all():
        db = get_db()
        rows = db.execute('SELECT * FROM settings').fetchall()
        return {r['key']: r['value'] for r in rows}

    @staticmethod
    def set(key, value):
        db = get_db()
        db.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?',
                   (key, value, value))
        db.commit()
