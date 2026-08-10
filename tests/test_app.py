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
        r = client.post('/group/postable-group/chat/send', data={
            'content': 'Group message here!',
        })
        assert r.status_code == 200
        assert r.get_json()['ok'] is True

    def test_non_member_cannot_post_in_group(self, app):
        owner = auth_client(app, username='gowner4')
        owner.post('/group/create', data={'name': 'Private Group X'})
        outsider = auth_client(app, username='outsider')
        r = outsider.post('/group/private-group-x/chat/send', data={
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


# ==================== ИСТОРИИ (Stories) ====================

class TestStories:
    def test_create_story(self, app):
        import io
        client = auth_client(app, username='storyteller')
        img = io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
        img.name = 'story.png'
        r = client.post('/story/create', data={
            'media': (img, 'story.png'),
            'caption': 'Test story',
        }, content_type='multipart/form-data')
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('ok') or data.get('story_id') or data.get('id')

    def test_story_appears_in_api(self, app):
        import io
        client = auth_client(app, username='storyteller2')
        img = io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
        img.name = 'story.png'
        client.post('/story/create', data={
            'media': (img, 'story.png'),
            'caption': 'API story',
        }, content_type='multipart/form-data')
        r = client.get('/api/stories')
        assert r.status_code == 200
        data = r.get_json()
        assert 'groups' in data
        assert isinstance(data['groups'], list)
        assert len(data['groups']) >= 1

    def test_delete_own_story(self, app):
        import io
        client = auth_client(app, username='storydeleter')
        img = io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
        img.name = 'story.png'
        client.post('/story/create', data={
            'media': (img, 'story.png'),
            'caption': 'Delete me',
        }, content_type='multipart/form-data')
        with app.app_context():
            from models import get_db
            db = get_db()
            sid = db.execute('SELECT MAX(id) id FROM stories').fetchone()['id']
        r = client.post(f'/story/{sid}/delete')
        assert r.status_code == 200


# ==================== ОБЗОР (Explore) ====================

class TestExplore:
    def test_explore_page_loads(self, app):
        client = auth_client(app, username='explorer')
        r = client.get('/explore')
        assert r.status_code == 200
        assert b'explore-page' in r.data or 'Обзор' in r.data.decode()

    def test_explore_shows_trending(self, app):
        client = auth_client(app, username='trendposter')
        client.post('/post/create', data={'content': 'Тренд #мастхи #код'})
        r = client.get('/explore')
        assert r.status_code == 200
        html = r.data.decode()
        assert 'мастхи' in html or 'код' in html

    def test_explore_popular_posts(self, app):
        client = auth_client(app, username='popposter')
        client.post('/post/create', data={'content': 'Popular content'})
        r = client.get('/explore')
        assert r.status_code == 200


# ==================== МЕССЕНДЖЕР: ОТВЕТ/РЕДАКТ ====================

class TestMessengerAdvanced:
    def test_reply_to_message(self, app):
        c1 = auth_client(app, username='replier')
        register(app.test_client(), username='replytarget')
        with app.app_context():
            from models import User
            receiver = User.get_by_username('replytarget')
            rid = receiver['id']
        # Исходное сообщение
        c1.post('/chat/send', data={'receiver_id': rid, 'content': 'Original msg'})
        with app.app_context():
            from models import get_db
            db = get_db()
            msg_id = db.execute('SELECT MAX(id) id FROM messages').fetchone()['id']
        # Ответ
        r = c1.post('/chat/send', data={
            'receiver_id': rid, 'content': 'Reply text',
            'reply_to_id': msg_id,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('reply_to_id') == msg_id

    def test_edit_message(self, app):
        c1 = auth_client(app, username='editor')
        register(app.test_client(), username='editreceiver')
        with app.app_context():
            from models import User
            receiver = User.get_by_username('editreceiver')
            rid = receiver['id']
        c1.post('/chat/send', data={'receiver_id': rid, 'content': 'Original'})
        with app.app_context():
            from models import get_db
            db = get_db()
            msg_id = db.execute('SELECT MAX(id) id FROM messages').fetchone()['id']
        r = c1.post(f'/chat/{msg_id}/edit', data={'content': 'Edited text'})
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('edited') is True
        # Проверяем в БД
        with app.app_context():
            from models import get_db
            db = get_db()
            row = db.execute('SELECT content, edited_at FROM messages WHERE id=?', (msg_id,)).fetchone()
            assert row['content'] == 'Edited text'
            assert row['edited_at'] is not None

    def test_mark_messages_read(self, app):
        c1 = auth_client(app, username='reader1')
        register(app.test_client(), username='reader2')
        with app.app_context():
            from models import User
            sender = User.get_by_username('reader1')
            receiver = User.get_by_username('reader2')
            sid, rid = sender['id'], receiver['id']
        c1.post('/chat/send', data={'receiver_id': rid, 'content': 'Unread msg'})
        # Читаем как получатель, передаём sender_id как partner
        c2 = auth_client(app, username='reader2')
        r = c2.post(f'/chat/{sid}/read')
        assert r.status_code == 200
        with app.app_context():
            from models import get_db
            db = get_db()
            count = db.execute('SELECT COUNT(*) c FROM messages WHERE sender_id=? AND is_read=1', (sid,)).fetchone()['c']
            assert count >= 1


# ==================== PWA ====================

class TestPWA:
    def test_manifest_json(self, client):
        r = client.get('/manifest.json')
        assert r.status_code == 200
        data = r.get_json()
        assert data.get('name') or data.get('short_name')

    def test_service_worker(self, client):
        r = client.get('/sw.js')
        assert r.status_code == 200
        assert b'ServiceWorker' in r.data or b'serviceWorker' in r.data or b'cache' in r.data


# ==================== WEB PUSH (VAPID) ====================

class TestWebPush:
    def test_vapid_public_key_endpoint(self, client):
        """Публичный VAPID ключ доступен без авторизации."""
        r = client.get('/api/vapid-public')
        assert r.status_code == 200
        data = r.get_json()
        assert 'publicKey' in data
        assert len(data['publicKey']) > 50

    def test_subscribe_requires_auth(self, client):
        """Push подписка требует авторизации."""
        r = client.post('/push/subscribe', json={
            'endpoint': 'https://fcm.googleapis.com/test',
            'keys': {'p256dh': 'abc', 'auth': 'def'},
        })
        assert r.status_code == 302  # редирект на логин

    def test_subscribe_and_persist(self, app):
        """Авторизованный пользователь может подписаться."""
        client = auth_client(app, username='pusher')
        r = client.post('/push/subscribe', json={
            'endpoint': 'https://fcm.googleapis.com/test123',
            'keys': {'p256dh': 'p256key', 'auth': 'authkey'},
        })
        assert r.status_code == 200
        assert r.get_json()['ok'] is True
        # Проверяем что подписка в БД
        with app.app_context():
            from models import PushSubscription, User
            u = User.get_by_username('pusher')
            subs = PushSubscription.get_by_user(u['id'])
            assert len(subs) >= 1
            assert subs[0]['endpoint'] == 'https://fcm.googleapis.com/test123'

    def test_unsubscribe(self, app):
        """Удаление подписки."""
        client = auth_client(app, username='pusher2')
        client.post('/push/subscribe', json={
            'endpoint': 'https://fcm.googleapis.com/test456',
            'keys': {'p256dh': 'k1', 'auth': 'k2'},
        })
        r = client.post('/push/unsubscribe', json={
            'endpoint': 'https://fcm.googleapis.com/test456',
        })
        assert r.status_code == 200
        assert r.get_json()['ok'] is True

    def test_duplicate_subscribe_idempotent(self, app):
        """Повторная подписка с тем же endpoint не дублирует запись."""
        client = auth_client(app, username='pusher3')
        for _ in range(3):
            client.post('/push/subscribe', json={
                'endpoint': 'https://example.com/push/same',
                'keys': {'p256dh': 'a', 'auth': 'b'},
            })
        with app.app_context():
            from models import PushSubscription, get_db
            db = get_db()
            count = db.execute("SELECT COUNT(*) c FROM push_subscriptions WHERE endpoint='https://example.com/push/same'").fetchone()['c']
            assert count == 1


# ==================== ПОИСК ПО СООБЩЕНИЯМ ====================

class TestMessageSearch:
    def test_search_finds_messages(self, app):
        c1 = auth_client(app, username='searcher1')
        register(app.test_client(), username='searchtarget1')
        with app.app_context():
            from models import User
            rid = User.get_by_username('searchtarget1')['id']
        c1.post('/chat/send', data={'receiver_id': rid, 'content': 'Important keyword Python'})
        c1.post('/chat/send', data={'receiver_id': rid, 'content': 'Other message without keyword'})
        r = c1.get(f'/chat/{rid}/search?q=Python')
        assert r.status_code == 200
        results = r.get_json()['results']
        assert len(results) == 1
        assert 'Python' in results[0]['content']

    def test_search_empty_query(self, app):
        c1 = auth_client(app, username='searcher2')
        register(app.test_client(), username='searchtarget2')
        with app.app_context():
            from models import User
            rid = User.get_by_username('searchtarget2')['id']
        r = c1.get(f'/chat/{rid}/search?q=')
        assert r.status_code == 200
        assert len(r.get_json()['results']) == 0


# ==================== ПЕРЕСЫЛКА СООБЩЕНИЙ ====================

class TestMessageForward:
    def test_forward_message(self, app):
        c1 = auth_client(app, username='forwarder')
        register(app.test_client(), username='fwd_target')
        register(app.test_client(), username='fwd_receiver')
        with app.app_context():
            from models import User
            tid = User.get_by_username('fwd_target')['id']
            rid = User.get_by_username('fwd_receiver')['id']
        # Отправляем исходное сообщение
        c1.post('/chat/send', data={'receiver_id': tid, 'content': 'Original to forward'})
        with app.app_context():
            from models import get_db
            mid = get_db().execute('SELECT MAX(id) id FROM messages').fetchone()['id']
        # Пересылаем
        r = c1.post(f'/chat/{mid}/forward', json={'to_user_id': rid})
        assert r.status_code == 200
        assert r.get_json()['ok'] is True
        # Проверяем что пересланное сообщение в БД с пометкой
        with app.app_context():
            from models import get_db
            fwd = get_db().execute('SELECT * FROM messages WHERE forwarded_from_name IS NOT NULL ORDER BY id DESC LIMIT 1').fetchone()
            assert fwd is not None
            assert fwd['content'] == 'Original to forward'
            assert fwd['forwarded_from_name'] == 'forwarder'


# ==================== ЗАРЕП СООБЩЕНИЙ ====================

class TestMessagePin:
    def test_pin_message(self, app):
        c1 = auth_client(app, username='pinner')
        register(app.test_client(), username='pintarget')
        with app.app_context():
            from models import User
            rid = User.get_by_username('pintarget')['id']
        c1.post('/chat/send', data={'receiver_id': rid, 'content': 'Pin me please'})
        with app.app_context():
            from models import get_db
            mid = get_db().execute('SELECT MAX(id) id FROM messages').fetchone()['id']
        r = c1.post(f'/chat/{mid}/pin')
        assert r.status_code == 200
        assert r.get_json()['pinned'] is True
        # Проверяем в БД
        with app.app_context():
            from models import get_db
            m = get_db().execute('SELECT is_pinned FROM messages WHERE id=?', (mid,)).fetchone()
            assert m['is_pinned'] == 1

    def test_unpin_message(self, app):
        c1 = auth_client(app, username='pinner2')
        register(app.test_client(), username='pintarget2')
        with app.app_context():
            from models import User
            rid = User.get_by_username('pintarget2')['id']
        c1.post('/chat/send', data={'receiver_id': rid, 'content': 'Pin and unpin'})
        with app.app_context():
            from models import get_db
            mid = get_db().execute('SELECT MAX(id) id FROM messages').fetchone()['id']
        c1.post(f'/chat/{mid}/pin')  # pin
        r = c1.post(f'/chat/{mid}/pin')  # unpin
        assert r.status_code == 200
        assert r.get_json()['pinned'] is False

    def test_get_pinned(self, app):
        c1 = auth_client(app, username='pinner3')
        register(app.test_client(), username='pintarget3')
        with app.app_context():
            from models import User, Message
            rid = User.get_by_username('pintarget3')['id']
            uid = User.get_by_username('pinner3')['id']
        c1.post('/chat/send', data={'receiver_id': rid, 'content': 'Pinned content'})
        with app.app_context():
            from models import get_db
            mid = get_db().execute('SELECT MAX(id) id FROM messages').fetchone()['id']
        c1.post(f'/chat/{mid}/pin')
        with app.app_context():
            from models import Message
            pinned = Message.get_pinned(uid, rid)
            assert pinned is not None
            assert pinned['content'] == 'Pinned content'


# ==================== МУЗЫКА В ПРОФИЛЕ ====================

class TestProfileMusic:
    def test_upload_requires_auth(self, client):
        r = client.post('/profile/music/upload')
        assert r.status_code == 302  # redirect to login

    def test_upload_music(self, app):
        import io
        client = auth_client(app, username='musiclover')
        mp3 = io.BytesIO(b'ID3' + b'\x00' * 200)
        mp3.name = 'song.mp3'
        r = client.post('/profile/music/upload', data={
            'music': (mp3, 'song.mp3'),
            'title': 'My Song',
        }, content_type='multipart/form-data')
        assert r.status_code == 200
        data = r.get_json()
        assert data['ok'] is True
        assert data['title'] == 'My Song'
        # Проверяем в БД
        with app.app_context():
            from models import User
            u = User.get_by_username('musiclover')
            assert u['profile_music'] is not None
            assert u['profile_music_title'] == 'My Song'

    def test_remove_music(self, app):
        import io
        client = auth_client(app, username='musiclover2')
        mp3 = io.BytesIO(b'ID3' + b'\x00' * 200)
        mp3.name = 'song.mp3'
        client.post('/profile/music/upload', data={
            'music': (mp3, 'song.mp3'),
            'title': 'Temp Song',
        }, content_type='multipart/form-data')
        r = client.post('/profile/music/remove')
        assert r.status_code == 200
        assert r.get_json()['ok'] is True
        with app.app_context():
            from models import User
            u = User.get_by_username('musiclover2')
            assert u['profile_music'] is None

    def test_reject_non_audio(self, app):
        import io
        client = auth_client(app, username='musiclover3')
        txt = io.BytesIO(b'not a music file')
        txt.name = 'file.txt'
        r = client.post('/profile/music/upload', data={
            'music': (txt, 'file.txt'),
        }, content_type='multipart/form-data')
        assert r.status_code == 400


# ==================== API USER ID ====================

class TestApiUserId:
    def test_get_user_id(self, app):
        auth_client(app, username='apiuser')
        client = auth_client(app, username='apicaller')
        r = client.get('/api/user/id?username=apiuser')
        assert r.status_code == 200
        data = r.get_json()
        assert data['id'] is not None
        assert data['username'] == 'apiuser'

    def test_get_user_id_not_found(self, app):
        client = auth_client(app, username='apicaller2')
        r = client.get('/api/user/id?username=nonexistent')
        assert r.status_code == 404


# ==================== ПЕРСИСТЕНТНОСТЬ ДАННЫХ ====================

class TestDataPersistence:
    def test_post_survives_reinit(self, app):
        """Данные сохраняются после повторной инициализации БД."""
        client = auth_client(app, username='persistuser')
        client.post('/post/create', data={'content': 'Persistence test 12345'})
        # Повторно инициализируем БД (имитация рестарта)
        with app.app_context():
            from models import init_db, migrate_db, get_db
            init_db()
            migrate_db()
            db = get_db()
            row = db.execute("SELECT content FROM posts WHERE content = 'Persistence test 12345'").fetchone()
            assert row is not None

    def test_message_survives_reinit(self, app):
        c1 = auth_client(app, username='persistmsg')
        register(app.test_client(), username='persistrecv')
        with app.app_context():
            from models import User
            rid = User.get_by_username('persistrecv')['id']
        c1.post('/chat/send', data={'receiver_id': rid, 'content': 'Persist message'})
        with app.app_context():
            from models import init_db, migrate_db, get_db
            init_db()
            migrate_db()
            db = get_db()
            row = db.execute("SELECT content FROM messages WHERE content = 'Persist message'").fetchone()
            assert row is not None
