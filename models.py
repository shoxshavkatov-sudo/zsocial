"""Модели базы данных ZSocial (Pro версия)."""
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config


def get_db():
    from flask import g
    if 'db' not in g:
        g.db = sqlite3.connect(Config.DATABASE, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
        g.db.execute('PRAGMA journal_mode = WAL')
        g.db.execute('PRAGMA synchronous = NORMAL')
    return g.db


def close_db(e=None):
    from flask import g
    db = g.pop('db', None)
    if db is not None:
        try:
            db.commit()
        except Exception:
            pass
        db.close()


def init_db():
    os.makedirs(os.path.dirname(Config.DATABASE) or '.', exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE, timeout=10)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')

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

    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter_id INTEGER NOT NULL,
        target_type TEXT NOT NULL,
        target_id INTEGER NOT NULL,
        reason TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS message_reactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        emoji TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(message_id, user_id),
        FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT DEFAULT '',
        cover TEXT DEFAULT 'img/default_cover.svg',
        is_private INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS group_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT DEFAULT 'member',
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(group_id, user_id),
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS group_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        msg_type TEXT DEFAULT 'text',
        file_url TEXT,
        file_name TEXT,
        file_size INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS voice_rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        name TEXT NOT NULL DEFAULT 'Голосовая',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS voice_room_state (
        room_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        muted INTEGER DEFAULT 0,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (room_id, user_id),
        FOREIGN KEY (room_id) REFERENCES voice_rooms(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS poll_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        poll_id INTEGER NOT NULL,
        option_text TEXT NOT NULL,
        FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS poll_votes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        option_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(option_id, user_id),
        FOREIGN KEY (option_id) REFERENCES poll_options(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS post_views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(post_id, user_id),
        FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
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
        'email_notifs': 'INTEGER DEFAULT 1',
        'token_version': 'INTEGER DEFAULT 0',
        'last_seen': 'TIMESTAMP',
        'profile_music': 'TEXT',
        'profile_music_title': 'TEXT',
    }
    for col, typedef in user_new.items():
        if col not in ucols:
            conn.execute(f'ALTER TABLE users ADD COLUMN {col} {typedef}')
    # Проверяем колонки posts (parent_id для репостов, updated_at для правки)
    pcols = [r[1] for r in conn.execute('PRAGMA table_info(posts)').fetchall()]
    post_new = {
        'parent_id': 'INTEGER REFERENCES posts(id) ON DELETE CASCADE',
        'quote': 'TEXT DEFAULT ""',
        'updated_at': 'TIMESTAMP',
        'group_id': 'INTEGER REFERENCES groups(id) ON DELETE CASCADE',
    }
    for col, typedef in post_new.items():
        if col not in pcols:
            conn.execute(f'ALTER TABLE posts ADD COLUMN {col} {typedef}')
    # Колонка comments.parent_id (треды/ответы)
    ccols = [r[1] for r in conn.execute('PRAGMA table_info(comments)').fetchall()]
    if 'parent_id' not in ccols:
        conn.execute('ALTER TABLE comments ADD COLUMN parent_id INTEGER')
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
    if 'reports' not in tables:
        conn.execute('''CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            reason TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
    if 'message_reactions' not in tables:
        conn.execute('''CREATE TABLE IF NOT EXISTS message_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(message_id, user_id),
            FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
    if 'groups' not in tables:
        conn.execute('''CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT '',
            cover TEXT DEFAULT 'img/default_cover.svg',
            is_private INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
    if 'group_members' not in tables:
        conn.execute('''CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, user_id),
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')
    # Новые таблицы (опросы, просмотры)
    for tname, tsql in [
        ('polls', '''CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )'''),
        ('poll_options', '''CREATE TABLE IF NOT EXISTS poll_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id INTEGER NOT NULL,
            option_text TEXT NOT NULL,
            FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
        )'''),
        ('poll_votes', '''CREATE TABLE IF NOT EXISTS poll_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            option_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(option_id, user_id),
            FOREIGN KEY (option_id) REFERENCES poll_options(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )'''),
        ('post_views', '''CREATE TABLE IF NOT EXISTS post_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(post_id, user_id),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        )'''),
        ('group_messages', '''CREATE TABLE IF NOT EXISTS group_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            msg_type TEXT DEFAULT 'text',
            file_url TEXT,
            file_name TEXT,
            file_size INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
        )'''),
        ('voice_rooms', '''CREATE TABLE IF NOT EXISTS voice_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT 'Голосовая',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
        )'''),
        ('voice_room_state', '''CREATE TABLE IF NOT EXISTS voice_room_state (
            room_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            muted INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (room_id, user_id),
            FOREIGN KEY (room_id) REFERENCES voice_rooms(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )'''),
        ('stories', '''CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            media TEXT NOT NULL,
            media_type TEXT DEFAULT 'image',
            caption TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )'''),
        ('story_views', '''CREATE TABLE IF NOT EXISTS story_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL,
            viewer_id INTEGER NOT NULL,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(story_id, viewer_id),
            FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
            FOREIGN KEY (viewer_id) REFERENCES users(id) ON DELETE CASCADE
        )'''),
    ]:
        if tname not in tables:
            conn.execute(tsql)

    # Доп. колонки в messages для ответов/редактирования/пересылки/закрепа (Этап 2 + редизайн)
    msg_cols = [r[1] for r in conn.execute('PRAGMA table_info(messages)').fetchall()]
    msg_new_cols = {
        'reply_to_id': 'INTEGER',
        'edited_at': 'TIMESTAMP',
        'forwarded_from_id': 'INTEGER',
        'forwarded_from_name': 'TEXT',
        'is_pinned': 'INTEGER DEFAULT 0',
    }
    for col, typedef in msg_new_cols.items():
        if col not in msg_cols:
            conn.execute(f'ALTER TABLE messages ADD COLUMN {col} {typedef}')

    # Таблица push-подписок (Этап 3b — Web Push VAPID)
    if 'push_subscriptions' not in tables:
        conn.execute('''CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, endpoint),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )''')

    # === Индексы для производительности (IF NOT EXISTS — идемпотентно) ===
    conn.executescript('''
        CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);
        CREATE INDEX IF NOT EXISTS idx_posts_parent_id ON posts(parent_id);
        CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at);
        CREATE INDEX IF NOT EXISTS idx_likes_post_id ON likes(post_id);
        CREATE INDEX IF NOT EXISTS idx_likes_user_id ON likes(user_id);
        CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);
        CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments(user_id);
        CREATE INDEX IF NOT EXISTS idx_bookmarks_user_id ON bookmarks(user_id);
        CREATE INDEX IF NOT EXISTS idx_follows_followed ON follows(followed_id);
        CREATE INDEX IF NOT EXISTS idx_follows_follower ON follows(follower_id);
        CREATE INDEX IF NOT EXISTS idx_messages_recv_read ON messages(receiver_id, is_read);
        CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
        CREATE INDEX IF NOT EXISTS idx_notifs_user_read ON notifications(user_id, is_read);
        CREATE INDEX IF NOT EXISTS idx_reactions_msg ON message_reactions(message_id);
        CREATE INDEX IF NOT EXISTS idx_stories_user ON stories(user_id);
        CREATE INDEX IF NOT EXISTS idx_stories_created ON stories(created_at);
        CREATE INDEX IF NOT EXISTS idx_story_views_story ON story_views(story_id);
    ''')

    conn.commit()
    conn.close()


# ==================== УТИЛИТЫ ====================
def is_online(profile_user, threshold_seconds=120):
    """True если пользователь был активен за последние ~2 минуты."""
    if not profile_user or not profile_user['last_seen']:
        return False
    try:
        from datetime import datetime
        dt = datetime.strptime(str(profile_user['last_seen'])[:19], '%Y-%m-%d %H:%M:%S')
        return (datetime.now() - dt).total_seconds() < threshold_seconds
    except (ValueError, TypeError):
        return False


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
    """Превращает #хештеги и @упоминания в кликабельные ссылки (HTML экранирование)."""
    import html
    import re
    escaped = html.escape(text or '')
    # @упоминания → ссылка на профиль
    escaped = re.sub(
        r'@([\w]{3,})',
        r'<span class="mention" onclick="location.href=\'/profile/\1\'">@\1</span>',
        escaped
    )
    # #хештеги → фильтр ленты
    escaped = re.sub(
        r'#([\wа-яёА-ЯЁ]+)',
        r'<span class="hashtag" onclick="searchTag(\'\1\')">#\1</span>',
        escaped
    )
    return escaped


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
        allowed = ['display_name', 'bio', 'status', 'avatar', 'cover', 'is_private', 'email_notifs']
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
    def change_password(uid, new_password):
        db = get_db()
        db.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                   (generate_password_hash(new_password), uid))
        db.commit()

    @staticmethod
    def delete(uid):
        db = get_db()
        db.execute('DELETE FROM users WHERE id = ?', (uid,))
        db.commit()

    @staticmethod
    def logout_everywhere(uid):
        """Инкрементирует версию токена — инвалидирует все сессии."""
        db = get_db()
        db.execute('UPDATE users SET token_version = token_version + 1 WHERE id = ?', (uid,))
        db.commit()
        return User.get(uid)['token_version']

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

    @staticmethod
    def get_suggested(uid, limit=8):
        """Рекомендации: пользователи, на которых не подписан uid, упорядоченные по активности."""
        db = get_db()
        rows = db.execute('''
            SELECT u.id, u.username, u.display_name, u.avatar, u.verified,
                   (SELECT COUNT(*) FROM posts WHERE user_id=u.id) AS post_count,
                   (SELECT COUNT(*) FROM follows WHERE followed_id=u.id) AS follower_count,
                   EXISTS(SELECT 1 FROM follows WHERE follower_id=? AND followed_id=u.id) AS is_following
            FROM users u
            WHERE u.id != ? AND u.is_private=0
            ORDER BY follower_count DESC, post_count DESC
            LIMIT ?
        ''', (uid, uid, limit)).fetchall()
        return rows


class Post:
    @staticmethod
    def create(user_id, content, image=None, group_id=None):
        db = get_db()
        db.execute(
            'INSERT INTO posts (user_id, content, image, group_id) VALUES (?, ?, ?, ?)',
            (user_id, content, image, group_id)
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
    def get_all(page=1, per_page=20, tag=None, limit=None):
        """Пагинированная лента. Возвращает (rows, total_count).
        limit — верхний потолок total_count (для админки), иначе считаем все."""
        db = get_db()
        where = ''
        params = ()
        if tag:
            where = 'WHERE LOWER(p.content) LIKE ?'
            params = (f'%#{tag}%',)
        total = db.execute(
            'SELECT COUNT(*) c FROM posts p JOIN users u ON p.user_id=u.id WHERE u.banned=0 '
            + ('AND LOWER(p.content) LIKE ?' if tag else ''),
            params
        ).fetchone()['c']
        rows = db.execute(
            Post._feed_where(('AND LOWER(p.content) LIKE ?' if tag else '')) + ' LIMIT ? OFFSET ?',
            (*params, per_page, (page - 1) * per_page)
        ).fetchall()
        return rows, total

    @staticmethod
    def get_following_feed(user_id, page=1, per_page=20, tag=None):
        db = get_db()
        extra = 'AND (p.user_id IN (SELECT followed_id FROM follows WHERE follower_id = ?) OR p.user_id = ?)'
        cnt_params = [user_id, user_id]
        feed_params = [user_id, user_id]
        if tag:
            extra += ' AND LOWER(p.content) LIKE ?'
            cnt_params.append(f'%#{tag}%')
            feed_params.append(f'%#{tag}%')
        total = db.execute(
            'SELECT COUNT(*) c FROM posts p JOIN users u ON p.user_id=u.id WHERE u.banned=0 '
            + extra, tuple(cnt_params)
        ).fetchone()['c']
        feed_params.append(per_page)
        feed_params.append((page - 1) * per_page)
        rows = db.execute(Post._feed_where(extra + ' LIMIT ? OFFSET ?'), tuple(feed_params)).fetchall()
        return rows, total

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

    @staticmethod
    def edit(pid, uid, content, force=False):
        db = get_db()
        post = Post.get(pid)
        if post and (post['user_id'] == uid or force):
            db.execute('UPDATE posts SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (content, pid))
            db.commit()
            return Post.get(pid)
        return None

    @staticmethod
    def search_content(q, page=1, per_page=20):
        db = get_db()
        like = f'%{q.lower()}%'
        total = db.execute(
            'SELECT COUNT(*) c FROM posts p JOIN users u ON p.user_id=u.id '
            'WHERE u.banned=0 AND LOWER(p.content) LIKE ?', (like,)
        ).fetchone()['c']
        rows = db.execute(
            Post._feed_where('AND LOWER(p.content) LIKE ?') + ' LIMIT ? OFFSET ?',
            (like, per_page, (page - 1) * per_page)
        ).fetchall()
        return rows, total

    @staticmethod
    def get_media_by_user(user_id):
        """Все посты пользователя с изображениями — для медиа-галереи профиля."""
        db = get_db()
        return db.execute(
            Post._feed_where('AND p.user_id = ? AND p.image IS NOT NULL'),
            (user_id,)
        ).fetchall()

    @staticmethod
    def repost(user_id, parent_id, quote=''):
        db = get_db()
        parent = db.execute('SELECT * FROM posts WHERE id = ?', (parent_id,)).fetchone()
        if not parent:
            return None
        # Проверяем что ещё не репостили
        existing = db.execute('SELECT id FROM posts WHERE user_id=? AND parent_id=?',
                              (user_id, parent_id)).fetchone()
        if existing:
            return None  # уже репостили
        content = quote or ''
        db.execute('INSERT INTO posts (user_id, content, parent_id, quote) VALUES (?,?,?,?)',
                   (user_id, content, parent_id, quote))
        db.commit()
        return db.execute('SELECT * FROM posts WHERE id = last_insert_rowid()').fetchone()

    @staticmethod
    def get_trending_tags(limit=10):
        """Топ хештегов из всех постов (Python-парсинг)."""
        db = get_db()
        all_tags = {}
        posts = db.execute('SELECT content FROM posts').fetchall()
        import re
        for p in posts:
            for tag in re.findall(r'#([\wа-яёА-ЯЁ]+)', p['content'] or ''):
                all_tags[tag] = all_tags.get(tag, 0) + 1
        return sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:limit]

    @staticmethod
    def get_popular(page=1, per_page=12):
        """Популярные посты за 7 дней по лайкам + комментариям."""
        db = get_db()
        offset = (page - 1) * per_page
        rows = db.execute('''
            SELECT p.*, u.username, u.display_name, u.avatar, u.verified,
                   (SELECT COUNT(*) FROM likes WHERE post_id=p.id) AS like_count,
                   (SELECT COUNT(*) FROM comments WHERE post_id=p.id) AS comment_count
            FROM posts p JOIN users u ON p.user_id=u.id
            WHERE p.created_at >= datetime('now', '-7 days')
              AND p.parent_id IS NULL
              AND u.is_private=0
            ORDER BY (SELECT COUNT(*) FROM likes WHERE post_id=p.id) +
                     (SELECT COUNT(*) FROM comments WHERE post_id=p.id) DESC,
                     p.created_at DESC
            LIMIT ? OFFSET ?
        ''', (per_page, offset)).fetchall()
        total = db.execute('''
            SELECT COUNT(*) c FROM posts p JOIN users u ON p.user_id=u.id
            WHERE p.created_at >= datetime('now', '-7 days')
              AND p.parent_id IS NULL AND u.is_private=0
        ''').fetchone()['c']
        return rows, total


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
    def create(uid, pid, content, parent_id=None):
        db = get_db()
        db.execute('INSERT INTO comments (user_id, post_id, content, parent_id) VALUES (?, ?, ?, ?)',
                   (uid, pid, content, parent_id))
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
    def create(s, r, content, msg_type='text', file_url=None, file_name=None, file_size=0, duration=0, reply_to_id=None, forwarded_from_id=None, forwarded_from_name=None):
        db = get_db()
        db.execute('''INSERT INTO messages
            (sender_id, receiver_id, content, msg_type, file_url, file_name, file_size, duration, reply_to_id, forwarded_from_id, forwarded_from_name)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (s, r, content, msg_type, file_url, file_name, file_size, duration, reply_to_id, forwarded_from_id, forwarded_from_name))
        db.commit()
        return db.execute('SELECT * FROM messages WHERE id = last_insert_rowid()').fetchone()

    @staticmethod
    def edit(mid, uid, content, window_minutes=15):
        """Редактирование сообщения (только своё, в течение window_minutes минут)."""
        from datetime import datetime, timedelta
        db = get_db()
        m = db.execute('SELECT * FROM messages WHERE id=?', (mid,)).fetchone()
        if not m or m['sender_id'] != uid:
            return False
        created = datetime.strptime(m['created_at'], '%Y-%m-%d %H:%M:%S')
        if datetime.utcnow() - created > timedelta(minutes=window_minutes):
            return False
        db.execute('UPDATE messages SET content=?, edited_at=CURRENT_TIMESTAMP WHERE id=?', (content, mid))
        db.commit()
        return True

    @staticmethod
    def get_conversation(a, b):
        db = get_db()
        return db.execute('''
            SELECT m.*, u.username, u.avatar, u.verified,
                   rm.content AS reply_to_content,
                   ru.username AS reply_to_username
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            LEFT JOIN messages rm ON m.reply_to_id = rm.id
            LEFT JOIN users ru ON rm.sender_id = ru.id
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
            SELECT convos.other_id, u.username, u.display_name, u.avatar, u.verified, u.last_seen,
                   CASE WHEN u.last_seen IS NOT NULL AND datetime(u.last_seen) >= datetime('now','-2 minutes') THEN 1 ELSE 0 END AS online,
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

    @staticmethod
    def get(mid):
        db = get_db()
        return db.execute('SELECT * FROM messages WHERE id = ?', (mid,)).fetchone()

    @staticmethod
    def delete(mid, uid, force=False):
        db = get_db()
        m = Message.get(mid)
        if m and (m['sender_id'] == uid or force):
            db.execute('DELETE FROM messages WHERE id = ?', (mid,))
            db.commit()
            return True
        return False

    @staticmethod
    def mark_one_read(mid):
        db = get_db()
        db.execute('UPDATE messages SET is_read=1 WHERE id = ?', (mid,))
        db.commit()

    @staticmethod
    def toggle_reaction(mid, uid, emoji):
        db = get_db()
        ex = db.execute('SELECT * FROM message_reactions WHERE message_id=? AND user_id=?', (mid, uid)).fetchone()
        if ex and ex['emoji'] == emoji:
            db.execute('DELETE FROM message_reactions WHERE message_id=? AND user_id=?', (mid, uid))
            db.commit()
            return False
        if ex:
            db.execute('UPDATE message_reactions SET emoji=? WHERE message_id=? AND user_id=?', (emoji, mid, uid))
        else:
            db.execute('INSERT INTO message_reactions (message_id, user_id, emoji) VALUES (?,?,?)', (mid, uid, emoji))
        db.commit()
        return True

    @staticmethod
    def get_reactions(mid):
        db = get_db()
        return db.execute(
            'SELECT emoji, COUNT(*) as cnt FROM message_reactions WHERE message_id=? GROUP BY emoji',
            (mid,)
        ).fetchall()

    @staticmethod
    def search(uid, partner_id, query):
        """Поиск по тексту сообщений в переписке двух пользователей."""
        db = get_db()
        like = f'%{query}%'
        return db.execute('''
            SELECT m.*, u.username, u.avatar, u.verified
            FROM messages m JOIN users u ON m.sender_id = u.id
            WHERE ((m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?))
              AND m.content LIKE ?
            ORDER BY m.created_at ASC
        ''', (uid, partner_id, partner_id, uid, like)).fetchall()

    @staticmethod
    def forward(mid, to_uid, from_uid):
        """Переслать сообщение другому пользователю (создаёт копию с пометкой)."""
        db = get_db()
        m = Message.get(mid)
        if not m:
            return None
        sender = db.execute('SELECT username, display_name FROM users WHERE id=?', (from_uid,)).fetchone()
        from_name = (sender['display_name'] or sender['username']) if sender else 'Unknown'
        db.execute('''INSERT INTO messages
            (sender_id, receiver_id, content, msg_type, file_url, file_name, file_size, duration, forwarded_from_id, forwarded_from_name)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (from_uid, to_uid, m['content'], m['msg_type'], m['file_url'], m['file_name'],
             m['file_size'], m['duration'], from_uid, from_name))
        db.commit()
        return db.execute('SELECT * FROM messages WHERE id = last_insert_rowid()').fetchone()

    @staticmethod
    def toggle_pin(mid, uid):
        """Закрепить/открепить сообщение (только участники переписки)."""
        db = get_db()
        m = Message.get(mid)
        if not m:
            return False
        if m['sender_id'] != uid and m['receiver_id'] != uid:
            return False
        # Снимаем все закрепы в этом диалоге (только 1 закреп)
        partner_id = m['receiver_id'] if m['sender_id'] == uid else m['sender_id']
        db.execute('''UPDATE messages SET is_pinned=0
                      WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)''',
                    (uid, partner_id, partner_id, uid))
        if not m['is_pinned']:
            db.execute('UPDATE messages SET is_pinned=1 WHERE id=?', (mid,))
            db.commit()
            return True
        db.commit()
        return False

    @staticmethod
    def get_pinned(uid, partner_id):
        """Получить закреплённое сообщение в диалоге (одно)."""
        db = get_db()
        return db.execute('''SELECT m.*, u.username, u.avatar, u.verified
                             FROM messages m JOIN users u ON m.sender_id = u.id
                             WHERE m.is_pinned=1 AND (
                               (m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?))
                             ORDER BY m.created_at DESC LIMIT 1''',
                          (uid, partner_id, partner_id, uid)).fetchone()

    @staticmethod
    def my_reaction(mid, uid):
        db = get_db()
        r = db.execute('SELECT emoji FROM message_reactions WHERE message_id=? AND user_id=?', (mid, uid)).fetchone()
        return r['emoji'] if r else None


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


class Report:
    @staticmethod
    def create(reporter_id, target_type, target_id, reason=''):
        db = get_db()
        db.execute('INSERT INTO reports (reporter_id, target_type, target_id, reason) VALUES (?,?,?,?)',
                   (reporter_id, target_type, target_id, reason))
        db.commit()

    @staticmethod
    def get_all(status=None):
        db = get_db()
        if status:
            return db.execute('''SELECT r.*, u.username, u.display_name, u.avatar
                FROM reports r JOIN users u ON r.reporter_id = u.id
                WHERE r.status = ? ORDER BY r.created_at DESC''', (status,)).fetchall()
        return db.execute('''SELECT r.*, u.username, u.display_name, u.avatar
            FROM reports r JOIN users u ON r.reporter_id = u.id
            ORDER BY r.created_at DESC''').fetchall()

    @staticmethod
    def resolve(rid, status='resolved'):
        db = get_db()
        db.execute('UPDATE reports SET status = ? WHERE id = ?', (status, rid))
        db.commit()


class Poll:
    @staticmethod
    def create(post_id, question, options):
        """Создаёт опрос: question + список вариантов."""
        db = get_db()
        db.execute('INSERT INTO polls (post_id, question) VALUES (?, ?)', (post_id, question))
        pid = db.execute('SELECT id FROM polls WHERE post_id = ?', (post_id,)).fetchone()['id']
        for opt in options:
            opt = opt.strip()
            if opt:
                db.execute('INSERT INTO poll_options (poll_id, option_text) VALUES (?, ?)', (pid, opt))
        db.commit()
        return pid

    @staticmethod
    def get_by_post(post_id):
        """Возвращает опрос поста или None: {id, question, options: [{id, text, votes, voted}]}"""
        db = get_db()
        poll = db.execute('SELECT * FROM polls WHERE post_id = ?', (post_id,)).fetchone()
        if not poll:
            return None
        opts = db.execute('SELECT * FROM poll_options WHERE poll_id = ?', (poll['id'],)).fetchall()
        total_votes = 0
        result_opts = []
        for o in opts:
            count = db.execute('SELECT COUNT(*) c FROM poll_votes WHERE option_id = ?', (o['id'],)).fetchone()['c']
            total_votes += count
            result_opts.append({'id': o['id'], 'text': o['option_text'], 'votes': count})
        # Проценты
        for o in result_opts:
            o['percent'] = round(o['votes'] / total_votes * 100) if total_votes else 0
        return {'id': poll['id'], 'question': poll['question'],
                'options': result_opts, 'total_votes': total_votes}

    @staticmethod
    def vote(option_id, user_id):
        """Голосует за вариант (один голос на пользователя в рамках опроса)."""
        db = get_db()
        opt = db.execute('SELECT * FROM poll_options WHERE id = ?', (option_id,)).fetchone()
        if not opt:
            return False
        poll_id = opt['poll_id']
        # Удаляем предыдущий голос пользователя в этом опросе
        db.execute('''DELETE FROM poll_votes WHERE user_id = ? AND option_id IN
                      (SELECT id FROM poll_options WHERE poll_id = ?)''', (user_id, poll_id))
        db.execute('INSERT INTO poll_votes (option_id, user_id) VALUES (?, ?)', (option_id, user_id))
        db.commit()
        return True

    @staticmethod
    def has_voted(post_id, user_id):
        """Проверяет, голосовал ли пользователь в опросе поста."""
        db = get_db()
        return db.execute('''SELECT 1 FROM poll_votes v
            JOIN poll_options o ON v.option_id = o.id
            JOIN polls p ON o.poll_id = p.id
            WHERE p.post_id = ? AND v.user_id = ?''', (post_id, user_id)).fetchone() is not None


class PostView:
    @staticmethod
    def record(post_id, user_id=None):
        """Фиксирует просмотр поста (один раз на пользователя)."""
        db = get_db()
        try:
            db.execute('INSERT OR IGNORE INTO post_views (post_id, user_id) VALUES (?, ?)',
                       (post_id, user_id))
            db.commit()
        except Exception:
            pass

    @staticmethod
    def count(post_id):
        db = get_db()
        return db.execute('SELECT COUNT(*) c FROM post_views WHERE post_id = ?', (post_id,)).fetchone()['c']


class Group:
    @staticmethod
    def _slugify(name):
        import re
        import unicodedata
        s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
        s = re.sub(r'[^\w\s-]', '', s).strip().lower()
        return re.sub(r'[-\s]+', '-', s) or 'group'

    @staticmethod
    def create(owner_id, name, description='', is_private=0, cover=None):
        db = get_db()
        base = Group._slugify(name)
        slug = base
        i = 2
        while db.execute('SELECT 1 FROM groups WHERE slug=?', (slug,)).fetchone():
            slug = f'{base}-{i}'; i += 1
        db.execute('INSERT INTO groups (owner_id, name, slug, description, is_private, cover) VALUES (?,?,?,?,?,?)',
                   (owner_id, name, slug, description, is_private, cover or 'img/default_cover.svg'))
        gid = db.execute('SELECT id FROM groups WHERE slug=?', (slug,)).fetchone()['id']
        db.execute('INSERT INTO group_members (group_id, user_id, role) VALUES (?,?,?)', (gid, owner_id, 'owner'))
        db.commit()
        return Group.get_by_slug(slug)

    @staticmethod
    def get(gid):
        db = get_db()
        return db.execute('SELECT * FROM groups WHERE id = ?', (gid,)).fetchone()

    @staticmethod
    def get_by_slug(slug):
        db = get_db()
        return db.execute('SELECT * FROM groups WHERE slug = ?', (slug,)).fetchone()

    @staticmethod
    def get_all():
        db = get_db()
        return db.execute('''
            SELECT g.*, u.username as owner_name,
                   (SELECT COUNT(*) FROM group_members WHERE group_id=g.id) as member_count
            FROM groups g JOIN users u ON g.owner_id=u.id
            ORDER BY g.created_at DESC
        ''').fetchall()

    @staticmethod
    def get_user_groups(uid):
        db = get_db()
        return db.execute('''
            SELECT g.*, (SELECT COUNT(*) FROM group_members WHERE group_id=g.id) as member_count
            FROM group_members gm JOIN groups g ON gm.group_id=g.id
            WHERE gm.user_id=? ORDER BY gm.joined_at DESC
        ''', (uid,)).fetchall()

    @staticmethod
    def is_member(gid, uid):
        db = get_db()
        return db.execute('SELECT 1 FROM group_members WHERE group_id=? AND user_id=?', (gid, uid)).fetchone() is not None

    @staticmethod
    def toggle_join(gid, uid):
        db = get_db()
        if Group.is_member(gid, uid):
            db.execute('DELETE FROM group_members WHERE group_id=? AND user_id=? AND role!="owner"', (gid, uid))
            db.commit(); return False
        db.execute('INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?,?)', (gid, uid))
        db.commit(); return True

    @staticmethod
    def get_members(gid):
        db = get_db()
        return db.execute('''
            SELECT u.username, u.display_name, u.avatar, u.verified, gm.role
            FROM group_members gm JOIN users u ON gm.user_id=u.id
            WHERE gm.group_id=? ORDER BY gm.joined_at ASC
        ''', (gid,)).fetchall()

    @staticmethod
    def get_posts(gid):
        db = get_db()
        return db.execute(Post._feed_where('AND p.group_id = ?'), (gid,)).fetchall()

    @staticmethod
    def get_popular(limit=6):
        """Популярные группы по количеству участников."""
        db = get_db()
        return db.execute('''
            SELECT g.*,
                   (SELECT COUNT(*) FROM group_members WHERE group_id=g.id) AS member_count
            FROM groups g
            ORDER BY member_count DESC
            LIMIT ?
        ''', (limit,)).fetchall()


class GroupMessage:
    """Сообщения в групповом чате (как в Telegram)."""

    @staticmethod
    def create(group_id, sender_id, content, msg_type='text', file_url=None,
               file_name=None, file_size=0):
        db = get_db()
        cur = db.execute(
            'INSERT INTO group_messages (group_id, sender_id, content, msg_type, file_url, file_name, file_size) '
            'VALUES (?,?,?,?,?,?,?)',
            (group_id, sender_id, content, msg_type, file_url, file_name, file_size))
        db.commit()
        return cur.lastrowid

    @staticmethod
    def get_recent(group_id, limit=100):
        """Последние N сообщений группы (с данными отправителя)."""
        db = get_db()
        return db.execute('''
            SELECT gm.*, u.username, u.display_name, u.avatar, u.verified, u.role
            FROM group_messages gm JOIN users u ON gm.sender_id=u.id
            WHERE gm.group_id=? ORDER BY gm.created_at ASC LIMIT ?
        ''', (group_id, limit)).fetchall()

    @staticmethod
    def delete(mid, uid):
        """Удаление (только автор или админ)."""
        db = get_db()
        msg = db.execute('SELECT sender_id FROM group_messages WHERE id=?', (mid,)).fetchone()
        if not msg:
            return False
        user = db.execute('SELECT role FROM users WHERE id=?', (uid,)).fetchone()
        if msg['sender_id'] != uid and (not user or user['role'] != 'admin'):
            return False
        db.execute('DELETE FROM group_messages WHERE id=?', (mid,))
        db.commit()
        return True


class VoiceRoom:
    """Голосовые комнаты (как в Discord) — управляют состоянием участников.
    Сам WebRTC-аудио идёт peer-to-peer (mesh) через Socket.IO сигналинг."""

    @staticmethod
    def create(group_id, name='Голосовая'):
        db = get_db()
        cur = db.execute('INSERT INTO voice_rooms (group_id, name) VALUES (?,?)',
                         (group_id, name))
        db.commit()
        return cur.lastrowid

    @staticmethod
    def get_by_group(group_id):
        db = get_db()
        return db.execute('''
            SELECT vr.*,
                   (SELECT COUNT(*) FROM voice_room_state WHERE room_id=vr.id) as participants_count
            FROM voice_rooms vr WHERE vr.group_id=? ORDER BY vr.created_at ASC
        ''', (group_id,)).fetchall()

    @staticmethod
    def get(room_id):
        db = get_db()
        return db.execute('SELECT * FROM voice_rooms WHERE id=?', (room_id,)).fetchone()

    @staticmethod
    def get_participants(room_id):
        db = get_db()
        return db.execute('''
            SELECT vrs.user_id, vrs.muted, u.username, u.display_name, u.avatar
            FROM voice_room_state vrs JOIN users u ON vrs.user_id=u.id
            WHERE vrs.room_id=? ORDER BY vrs.joined_at ASC
        ''', (room_id,)).fetchall()

    @staticmethod
    def join(room_id, uid):
        db = get_db()
        db.execute('INSERT OR IGNORE INTO voice_room_state (room_id, user_id) VALUES (?,?)',
                   (room_id, uid))
        db.commit()

    @staticmethod
    def leave(room_id, uid):
        db = get_db()
        db.execute('DELETE FROM voice_room_state WHERE room_id=? AND user_id=?', (room_id, uid))
        db.commit()

    @staticmethod
    def set_muted(room_id, uid, muted):
        db = get_db()
        db.execute('UPDATE voice_room_state SET muted=? WHERE room_id=? AND user_id=?',
                   (1 if muted else 0, room_id, uid))
        db.commit()

    @staticmethod
    def leave_all_rooms(uid):
        """Покинуть все голосовые комнаты (при выходе)."""
        db = get_db()
        rows = db.execute('SELECT room_id FROM voice_room_state WHERE user_id=?', (uid,)).fetchall()
        db.execute('DELETE FROM voice_room_state WHERE user_id=?', (uid,))
        db.commit()
        return [r['room_id'] for r in rows]


class SiteSettings:
    # In-memory кэш, чтобы не дёргать БД на каждом HTTP-запросе.
    _cache = None

    @classmethod
    def _load_cache(cls):
        db = get_db()
        rows = db.execute('SELECT * FROM settings').fetchall()
        cls._cache = {r['key']: r['value'] for r in rows}
        return cls._cache

    @classmethod
    def get(cls, key, default=None):
        if cls._cache is None:
            cls._load_cache()
        return cls._cache.get(key, default)

    @classmethod
    def get_all(cls):
        if cls._cache is None:
            cls._load_cache()
        return dict(cls._cache)

    @classmethod
    def set(cls, key, value):
        db = get_db()
        db.execute('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?',
                   (key, value, value))
        db.commit()
        if cls._cache is not None:
            cls._cache[key] = value


class Story:
    """Истории — исчезающие фото/видео на 24 часа."""
    LIFETIME_HOURS = 24

    @staticmethod
    def create(user_id, media, media_type='image', caption=None):
        db = get_db()
        db.execute('INSERT INTO stories (user_id, media, media_type, caption) VALUES (?, ?, ?, ?)',
                   (user_id, media, media_type, caption))
        db.commit()
        return db.execute('SELECT * FROM stories WHERE id = last_insert_rowid()').fetchone()

    @staticmethod
    def get(sid):
        db = get_db()
        return db.execute('SELECT * FROM stories WHERE id = ?', (sid,)).fetchone()

    @staticmethod
    def cleanup_expired():
        """Удаляет истории старше 24 часов. Возвращает количество удалённых."""
        db = get_db()
        cur = db.execute(
            "DELETE FROM stories WHERE created_at < datetime('now', ?)",
            (f'-{Story.LIFETIME_HOURS} hours',)
        )
        db.commit()
        return cur.rowcount

    @staticmethod
    def get_active_for_user(viewer_id):
        """Активные истории сгруппированные по пользователям для rings-бара.
        Возвращает список: {user_id, username, display_name, avatar, verified,
                            stories: [{id, media, media_type, caption, created_at, seen}]}
        """
        db = get_db()
        rows = db.execute(
            f"""SELECT s.id, s.user_id, s.media, s.media_type, s.caption, s.created_at,
                       u.username, u.display_name, u.avatar, u.verified
                FROM stories s
                JOIN users u ON u.id = s.user_id
                WHERE s.created_at >= datetime('now', '-{Story.LIFETIME_HOURS} hours')
                ORDER BY s.user_id, s.created_at DESC""",
        ).fetchall()
        # Какие уже видел viewer
        seen_ids = set()
        if viewer_id:
            sv = db.execute('SELECT story_id FROM story_views WHERE viewer_id = ?', (viewer_id,)).fetchall()
            seen_ids = {r['story_id'] for r in sv}
        # Группируем по пользователю
        grouped = {}
        order = []
        for r in rows:
            uid = r['user_id']
            if uid not in grouped:
                grouped[uid] = {
                    'user_id': uid,
                    'username': r['username'],
                    'display_name': r['display_name'],
                    'avatar': r['avatar'],
                    'verified': r['verified'],
                    'stories': [],
                }
                order.append(uid)
            grouped[uid]['stories'].append({
                'id': r['id'],
                'media': r['media'],
                'media_type': r['media_type'],
                'caption': r['caption'],
                'created_at': r['created_at'],
                'seen': r['id'] in seen_ids,
            })
        return [grouped[uid] for uid in order]

    @staticmethod
    def get_user_stories(uid):
        """Все активные истории конкретного пользователя (для просмотрщика)."""
        db = get_db()
        return db.execute(
            f"""SELECT * FROM stories
                WHERE user_id = ? AND created_at >= datetime('now', '-{Story.LIFETIME_HOURS} hours')
                ORDER BY created_at ASC""",
            (uid,)
        ).fetchall()

    @staticmethod
    def delete(sid, uid, force=False):
        db = get_db()
        s = Story.get(sid)
        if not s:
            return False
        if s['user_id'] != uid and not force:
            return False
        db.execute('DELETE FROM stories WHERE id = ?', (sid,))
        db.commit()
        return True


class StoryView:
    """Просмотры историй (один просмотр на пользователя)."""

    @staticmethod
    def record(story_id, viewer_id):
        db = get_db()
        try:
            db.execute('INSERT OR IGNORE INTO story_views (story_id, viewer_id) VALUES (?, ?)',
                       (story_id, viewer_id))
            db.commit()
        except Exception:
            pass

    @staticmethod
    def count(story_id):
        db = get_db()
        return db.execute('SELECT COUNT(*) c FROM story_views WHERE story_id = ?', (story_id,)).fetchone()['c']

    @staticmethod
    def viewers(story_id):
        """Кто просмотрел историю (с инфой о пользователе)."""
        db = get_db()
        return db.execute(
            """SELECT u.id, u.username, u.display_name, u.avatar, u.verified, sv.viewed_at
               FROM story_views sv JOIN users u ON u.id = sv.viewer_id
               WHERE sv.story_id = ? ORDER BY sv.viewed_at DESC""",
            (story_id,)
        ).fetchall()


class PushSubscription:
    """Web Push подписки (VAPID)."""

    @staticmethod
    def subscribe(user_id, endpoint, p256dh, auth):
        db = get_db()
        try:
            db.execute('''INSERT OR IGNORE INTO push_subscriptions
                          (user_id, endpoint, p256dh, auth)
                          VALUES (?, ?, ?, ?)''', (user_id, endpoint, p256dh, auth))
            db.commit()
        except Exception:
            pass

    @staticmethod
    def get_by_user(user_id):
        db = get_db()
        return db.execute('SELECT * FROM push_subscriptions WHERE user_id=?', (user_id,)).fetchall()

    @staticmethod
    def delete(user_id, endpoint):
        db = get_db()
        db.execute('DELETE FROM push_subscriptions WHERE user_id=? AND endpoint=?', (user_id, endpoint))
        db.commit()

    @staticmethod
    def delete_by_endpoint(endpoint):
        """Удаляет подписку если сервер push вернул 410/404."""
        db = get_db()
        db.execute('DELETE FROM push_subscriptions WHERE endpoint=?', (endpoint,))
        db.commit()
