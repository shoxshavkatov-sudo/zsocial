"""Основные тесты ZSocial.

Покрытие:
- регистрация / логин (успех и неудача)
- создание поста
- лайк / комментарий / закладка
- follow
- отправка сообщения
- права доступа (не-админ не может в админку)
- группы: создание / вступление / пост в группе
- треды комментариев (parent_id)
- пагинация
"""
from tests.conftest import register, login, auth_client


# ==================== АУТЕНТИФИКАЦИЯ ====================

class TestAuth:
    def test_register_success(self, client):
        r = register(client, username='newuser')
        assert r.status_code == 200  # после редиректа на /feed

    def test_register_short_username_rejected(self, client):
        r = client.post('/register', data={
            'username': 'ab', 'email': 'ab@test.com',
            'password': 'Pass1234', 'confirm': 'Pass1234',
        })
        assert r.status_code == 200
        assert 'символ' in r.data.decode()

    def test_register_duplicate_rejected(self, app):
        register(app.test_client(), username='dup')
        # Вторая попытка с тем же username — новым клиентом
        c2 = app.test_client()
        r = c2.post('/register', data={
            'username': 'dup', 'email': 'dup2@test.com',
            'password': 'Pass1234', 'confirm': 'Pass1234',
        })
        assert 'занято' in r.data.decode()

    def test_login_success(self, app):
        client = auth_client(app, username='logintest')
        r = client.get('/feed')
        assert r.status_code == 200

    def test_login_wrong_password(self, client):
        register(client, username='pwuser')
        client.get('/logout')  # выходим
        r = client.post('/login', data={
            'login': 'pwuser', 'password': 'WrongPassword',
        }, follow_redirects=False)
        # Остаётся на странице логина (200) с flash
        assert r.status_code == 200

    def test_protected_route_redirects_anon(self, client):
        r = client.get('/feed')
        assert r.status_code == 302
        assert '/login' in r.headers.get('Location', '')


# ==================== ПОСТЫ ====================

class TestPosts:
    def test_create_post(self, app):
        client = auth_client(app, username='poster')
        r = client.post('/post/create', data={'content': 'Hello world!'})
        assert r.status_code == 302  # редирект на ленту после успеха
        # Проверим что пост реально в БД
        with app.app_context():
            from models import get_db
            db = get_db()
            row = db.execute("SELECT content FROM posts WHERE content = 'Hello world!'").fetchone()
            assert row is not None

    def test_empty_post_rejected(self, app):
        client = auth_client(app, username='poster2')
        r = client.post('/post/create', data={'content': ''})
        assert r.status_code == 302  # редирект с flash «Пост пуст»
        # Пустой пост не должен попасть в БД
        with app.app_context():
            from models import get_db
            db = get_db()
            count = db.execute("SELECT COUNT(*) c FROM posts WHERE content = ''").fetchone()['c']
            assert count == 0

    def test_post_appears_in_feed(self, app):
        client = auth_client(app, username='feeder')
        client.post('/post/create', data={'content': 'Unique feed text 12345'})
        r = client.get('/feed')
        assert b'Unique feed text 12345' in r.data


# ==================== ВЗАИМОДЕЙСТВИЯ ====================

class TestInteractions:
    def test_like_toggle(self, app):
        client = auth_client(app, username='liker')
        client.post('/post/create', data={'content': 'Like me'})
        r = client.post('/post/1/like')
        data = r.get_json()
        assert data['liked'] is True
        assert data['count'] >= 1
        # Снимаем лайк
        r2 = client.post('/post/1/like')
        assert r2.get_json()['liked'] is False

    def test_comment(self, app):
        client = auth_client(app, username='commenter')
        client.post('/post/create', data={'content': 'Comment me'})
        r = client.post('/post/1/comment', data={'content': 'First comment!'})
        assert r.status_code == 200
        assert r.get_json()['content'] == 'First comment!'

    def test_threaded_reply(self, app):
        client = auth_client(app, username='threader')
        client.post('/post/create', data={'content': 'Thread me'})
        # Корневой комментарий
        client.post('/post/1/comment', data={'content': 'Root comment'})
        # Ответ
        r = client.post('/post/1/comment', data={
            'content': 'Nested reply', 'parent_id': '1',
        })
        assert r.status_code == 200
        assert r.get_json()['parent_id'] == 1

    def test_bookmark_toggle(self, app):
        client = auth_client(app, username='bookmarker')
        client.post('/post/create', data={'content': 'Save me'})
        r = client.post('/post/1/bookmark')
        assert r.get_json()['saved'] is True


# ==================== ОПРОСЫ ====================

class TestPolls:
    def test_create_post_with_poll(self, app):
        client = auth_client(app, username='pollcreator')
        r = client.post('/post/create', data={
            'content': 'Какой язык лучше?',
            'poll_question': 'Любимый язык?',
            'poll_options': 'Python\nJavaScript\nRust',
        })
        assert r.status_code == 302
        with app.app_context():
            from models import Poll, get_db
            db = get_db()
            pid = db.execute('SELECT MAX(id) id FROM posts').fetchone()['id']
            poll = Poll.get_by_post(pid)
            assert poll is not None
            assert len(poll['options']) == 3

    def test_vote_in_poll(self, app):
        client = auth_client(app, username='pollvoter')
        client.post('/post/create', data={
            'content': 'Голосование!',
            'poll_question': 'Чай или кофе?',
            'poll_options': 'Чай\nКофе',
        })
        with app.app_context():
            from models import get_db
            db = get_db()
            opt_id = db.execute('SELECT id FROM poll_options LIMIT 1').fetchone()['id']
        r = client.post(f'/poll/{opt_id}/vote')
        assert r.status_code == 200
        data = r.get_json()
        assert data['ok'] is True
        assert data['poll']['total_votes'] >= 1

    def test_poll_vote_changes(self, app):
        """Пользователь может переголосовать (меняет выбор)."""
        client = auth_client(app, username='pollchanger')
        client.post('/post/create', data={
            'content': 'Переголосование',
            'poll_question': 'Q?',
            'poll_options': 'A\nB',
        })
        with app.app_context():
            from models import get_db
            db = get_db()
            opt_a = db.execute('SELECT id FROM poll_options ORDER BY id LIMIT 1').fetchone()['id']
            opt_b = db.execute('SELECT id FROM poll_options ORDER BY id DESC LIMIT 1').fetchone()['id']
        # Голосуем за A
        client.post(f'/poll/{opt_a}/vote')
        # Переголосовываем за B
        client.post(f'/poll/{opt_b}/vote')
        with app.app_context():
            from models import Poll, get_db
            db = get_db()
            pid = db.execute('SELECT MAX(id) id FROM posts').fetchone()['id']
            poll = Poll.get_by_post(pid)
            # Должен быть только 1 голос (за B)
            assert poll['total_votes'] == 1


# ==================== СООБЩЕНИЯ ====================

class TestMessaging:
    def test_send_message(self, app):
        # Два пользователя
        c1 = auth_client(app, username='msgsender')
        register(app.test_client(), username='msgreceiver')
        with app.app_context():
            from models import User
            receiver = User.get_by_username('msgreceiver')
            rid = receiver['id']
        r = c1.post('/chat/send', data={
            'receiver_id': rid, 'content': 'Hello there!',
        })
        assert r.status_code == 200


# ==================== ПРАВА ДОСТУПА ====================

class TestAccessControl:
    def test_non_admin_cannot_access_admin(self, app):
        client = auth_client(app, username='regularuser')
        r = client.get('/admin')
        # Не-админ → редирект (302)
        assert r.status_code == 302

    def test_anon_cannot_post(self, client):
        r = client.post('/post/create', data={'content': 'hacker attempt'})
        assert r.status_code == 302  # редирект на логин


# ==================== ГРУППЫ ====================

class TestGroups:
    def test_create_group(self, app):
        client = auth_client(app, username='groupowner')
        r = client.post('/group/create', data={
            'name': 'Test Group', 'description': 'A test community',
        })
        assert r.status_code == 302
        assert '/group/' in r.headers.get('Location', '')

    def test_group_page_loads(self, app):
        client = auth_client(app, username='groupowner2')
        client.post('/group/create', data={'name': 'Visible Group'})
        r = client.get('/group/visible-group')
        assert r.status_code == 200
        assert b'Visible Group' in r.data

    def test_join_group(self, app):
        # Создатель создаёт группу
        owner = auth_client(app, username='groupowner3')
        owner.post('/group/create', data={'name': 'Joinable Group'})
        # Другой пользователь вступает
        joiner = auth_client(app, username='joiner')
        r = joiner.post('/group/joinable-group/join')
        assert r.status_code == 200
        assert r.get_json()['joined'] is True

    def test_post_in_group(self, app):
        client = auth_client(app, username='groupposter')
        client.post('/group/create', data={'name': 'Postable Group'})
        r = client.post('/group/postable-group/post', data={
            'content': 'Group post here!',
        })
        assert r.status_code == 200
        assert r.get_json()['ok'] is True

    def test_non_member_cannot_post_in_group(self, app):
        owner = auth_client(app, username='gowner4')
        owner.post('/group/create', data={'name': 'Private Group X'})
        outsider = auth_client(app, username='outsider')
        r = outsider.post('/group/private-group-x/post', data={
            'content': 'Intrusion attempt',
        })
        assert r.status_code == 403


# ==================== ПАГИНАЦИЯ ====================

class TestPagination:
    def test_feed_pagination(self, app):
        client = auth_client(app, username='paginator')
        # Создаём 25 постов
        for i in range(25):
            client.post('/post/create', data={'content': f'Pagination post {i}'})
        # Страница 1 и 2 должны возвращать 200
        assert client.get('/feed?page=1').status_code == 200
        assert client.get('/feed?page=2').status_code == 200
