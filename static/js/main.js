/* ============================================
   ZSocial — клиентская логика
   ============================================ */

// ===== ТЕМА =====
function getTheme() {
    return localStorage.getItem('zs-theme') || 'light';
}
function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('zs-theme', t);
    document.cookie = 'theme=' + t + ';path=/;max-age=31536000';
}
function toggleTheme() {
    applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
    // Обновить иконку
    const cur = getTheme();
    document.querySelectorAll('.bottombar-theme .icon use').forEach(u => {
        u.setAttribute('href', '#i-' + (cur === 'dark' ? 'sun' : 'moon'));
    });
    // Подсветка кнопок в настройках
    document.querySelectorAll('.theme-btn').forEach(b => {
        b.className = 'btn btn-sm ' + (b.dataset.theme === cur ? 'btn-primary' : 'btn-outline') + ' theme-btn';
    });
}
applyTheme(getTheme());

// Кнопки темы в настройках
document.addEventListener('DOMContentLoaded', () => {
    const cur = getTheme();
    document.querySelectorAll('.theme-btn').forEach(b => {
        b.addEventListener('click', () => { applyTheme(b.dataset.theme); toggleTheme(); });
        b.className = 'btn btn-sm ' + (b.dataset.theme === cur ? 'btn-primary' : 'btn-outline') + ' theme-btn';
    });

    // Chat scroll
    const cm = document.getElementById('chat-messages');
    if (cm) cm.scrollTop = cm.scrollHeight;

    // Закрытие меню по клику вне
    document.addEventListener('click', () => closeAllMenus());
});

// ===== УТИЛИТЫ =====
function esc(t) { const d = document.createElement('div'); d.textContent = t == null ? '' : String(t); return d.innerHTML; }
function flashToast(msg) {
    // используем стандартные flash из base
    const c = document.getElementById('flash-container');
    if (!c) return alert(msg);
    const el = document.createElement('div');
    el.className = 'flash flash-info';
    el.innerHTML = '<span>' + esc(msg) + '</span><svg class="icon icon-sm"><use href="#i-x"/></svg>';
    el.onclick = () => el.remove();
    c.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 300); }, 2500);
}

// ===== ПРЕВЬЮ ИЗОБРАЖЕНИЙ =====
function previewImg(input) {
    const p = document.getElementById('img-preview');
    if (!p || !input.files || !input.files[0]) return;
    const r = new FileReader();
    r.onload = e => p.innerHTML = '<img src="' + e.target.result + '">';
    r.readAsDataURL(input.files[0]);
}
function previewAvatar(input) { /* просто показываем что выбран */ }
function previewCover(input) {}

// ===== ЛАЙКИ =====
function toggleLike(pid, btn) {
    fetch('/post/' + pid + '/like', { method: 'POST' })
        .then(r => r.json())
        .then(d => {
            if (d.error) return flashToast(d.error);
            btn.classList.toggle('liked', d.liked);
            // обновить счётчик
            const card = document.getElementById('post-' + pid);
            let stats = card.querySelector('.post-stats');
            const cmt = card.querySelector('.post-action:nth-child(2)');
            const cmtCount = cmt ? cmt.querySelector('span') : null;
            const cmtN = cmtCount ? cmtCount.textContent.match(/\d+/) : null;
            const cmtText = cmtN ? cmtN[0] + ' комментариев' : '';
            const likeText = d.count > 0 ? d.count + ' отметок' : '';
            if (!stats && (d.count > 0 || cmtN)) {
                stats = document.createElement('div');
                stats.className = 'post-stats';
                card.querySelector('.post-actions').before(stats);
            }
            if (stats) {
                stats.innerHTML = '<span class="text-sm text-muted">' + (likeText && cmtText ? likeText + ' · ' + cmtText : likeText || cmtText) + '</span>';
            }
        })
        .catch(() => flashToast('Ошибка соединения'));
}

// ===== ЗАКЛАДКИ =====
function toggleBookmark(pid, btn) {
    fetch('/post/' + pid + '/bookmark', { method: 'POST' })
        .then(r => r.json())
        .then(d => {
            if (d.error) return flashToast(d.error);
            btn.classList.toggle('saved', d.saved);
            flashToast(d.saved ? 'В закладках' : 'Убрано из закладок');
        });
}

// ===== КОММЕНТАРИИ =====
function toggleComments(pid) {
    const sec = document.getElementById('comments-' + pid);
    if (!sec) return;
    if (sec.classList.contains('hidden')) {
        sec.classList.remove('hidden');
        loadComments(pid);
    } else {
        sec.classList.add('hidden');
    }
}
function loadComments(pid) {
    fetch('/post/' + pid + '/comments')
        .then(r => r.json())
        .then(list => {
            document.getElementById('comments-list-' + pid).innerHTML = list.map(c =>
                '<div class="comment"><img src="/static/' + c.avatar + '" onclick="location.href=\'/profile/' + c.username + '\'"><div class="comment-content"><div class="comment-bubble"><div class="c-author">' + esc(c.username) + (c.verified ? ' <svg class="icon icon-sm verified-mark"><use href="#i-check-badge"/></svg>' : '') + '</div><div class="c-text">' + esc(c.content) + '</div></div></div></div><div class="comment-time">' + c.time + '</div>'
            ).join('');
        });
}
function addComment(pid) {
    const inp = document.getElementById('cinput-' + pid);
    const txt = inp.value.trim();
    if (!txt) return;
    const fd = new FormData();
    fd.append('content', txt);
    fetch('/post/' + pid + '/comment', { method: 'POST', body: fd })
        .then(r => r.json())
        .then(c => {
            if (c.error) return flashToast(c.error);
            const list = document.getElementById('comments-list-' + pid);
            list.insertAdjacentHTML('beforeend',
                '<div class="comment"><img src="/static/' + c.avatar + '" onclick="location.href=\'/profile/' + c.username + '\'"><div class="comment-content"><div class="comment-bubble"><div class="c-author">' + esc(c.username) + '</div><div class="c-text">' + esc(c.content) + '</div></div></div></div><div class="comment-time">' + c.time + '</div>'
            );
            inp.value = '';
        });
}

// ===== ПОДПИСКИ =====
function toggleFollow(uid, btn) {
    fetch('/follow/' + uid, { method: 'POST' })
        .then(r => r.json())
        .then(d => {
            if (d.error) return flashToast(d.error);
            if (btn) {
                btn.textContent = d.following ? 'Вы подписаны' : 'Подписаться';
                btn.className = 'btn ' + (d.following ? 'btn-outline' : 'btn-primary');
            }
            const fc = document.getElementById('followers-count');
            if (fc) fc.textContent = d.count;
        });
}
function toggleFollowFromList(uid, btn) {
    fetch('/follow/' + uid, { method: 'POST' })
        .then(r => r.json())
        .then(d => {
            if (d.error) return;
            btn.textContent = d.following ? 'Читаю' : 'Читать';
            btn.className = 'btn ' + (d.following ? 'btn-outline' : 'btn-primary') + ' btn-sm';
        });
}

// ===== МЕНЮ ПОСТА =====
function togglePostMenu(e, pid, userId) {
    e.stopPropagation();
    closeAllMenus();
    const cu = document.body.dataset.userId;
    const isOwn = String(userId) === String(cu);
    const isAdmin = document.body.dataset.isAdmin === '1';
    const menu = document.createElement('div');
    menu.className = 'post-menu';
    let items = '';
    if (isOwn) items += '<button class="danger" onclick="deleteOwnPost(' + pid + ')"><svg class="icon icon-sm"><use href="#i-trash"/></svg> Удалить</button>';
    items += '<button onclick="copyLink(' + pid + ')"><svg class="icon icon-sm"><use href="#i-share"/></svg> Копировать ссылку</button>';
    if (!isOwn) items += '<button class="danger" onclick="reportPost(' + pid + ')"><svg class="icon icon-sm"><use href="#i-flag"/></svg> Пожаловаться</button>';
    if (isAdmin && !isOwn) items += '<button class="danger" onclick="deleteOwnPost(' + pid + ')"><svg class="icon icon-sm"><use href="#i-trash"/></svg> Удалить (админ)</button>';
    menu.innerHTML = items;
    document.body.appendChild(menu);
    const rect = e.currentTarget.getBoundingClientRect();
    menu.style.top = (rect.bottom + 4) + 'px';
    menu.style.right = (window.innerWidth - rect.right) + 'px';
}
function closeAllMenus() {
    document.querySelectorAll('.post-menu').forEach(m => m.remove());
}
function deleteOwnPost(pid) {
    if (!confirm('Удалить пост?')) return;
    const fd = new FormData();
    fetch('/post/' + pid + '/delete', { method: 'POST' })
        .then(() => {
            const p = document.getElementById('post-' + pid);
            if (p) p.remove();
            flashToast('Удалено');
        });
}
function copyLink(pid) { flashToast('Ссылка скопирована'); }
function reportPost(pid) { flashToast('Жалоба отправлена'); }
function sharePost(pid) { flashToast('Ссылка скопирована'); }

// ===== ХЕШТЕГИ =====
function searchTag(tag) {
    location.href = '/feed?tag=' + encodeURIComponent(tag);
}

// ===== ЗАГРУЗКА АВАТАРА/ОБЛОЖКИ (через settings form-submit) =====
function uploadAvatar(input) { /* форма отправится при сабмите */ }
function uploadCover(input) {}

// ===== АДМИН =====
function adminBan(uid) {
    if (!confirm('Изменить статус блокировки?')) return;
    fetch('/admin/user/' + uid + '/ban', { method: 'POST' })
        .then(r => r.json())
        .then(d => { if (!d.error) location.reload(); });
}
function adminVerify(uid) {
    fetch('/admin/user/' + uid + '/verify', { method: 'POST' })
        .then(r => r.json())
        .then(d => { if (!d.error) location.reload(); });
}
function adminRole(uid) {
    fetch('/admin/user/' + uid + '/role', { method: 'POST' })
        .then(r => r.json())
        .then(d => { if (!d.error) location.reload(); });
}

// ===== ЧАТ (WebSocket) =====
let chatSocket = null;
function initSocket(myId, partnerId) {
    if (typeof io === 'undefined') return;
    chatSocket = io();
    chatSocket.on('new_message', (data) => {
        if (data.sender_id !== partnerId && data.receiver_id !== partnerId) return;
        const container = document.getElementById('chat-messages');
        if (!container) return;
        const isMine = data.sender_id === myId;
        const div = document.createElement('div');
        div.className = 'msg ' + (isMine ? 'mine' : 'theirs');
        div.innerHTML = '<div class="msg-bubble">' + esc(data.content) + '</div><div class="msg-time">' + data.time + '</div>';
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    });
}
function sendMessage(partnerId) {
    const inp = document.getElementById('chat-input');
    const txt = inp.value.trim();
    if (!txt) return;
    const fd = new FormData();
    fd.append('receiver_id', partnerId);
    fd.append('content', txt);
    fetch('/chat/send', { method: 'POST', body: fd })
        .then(r => r.json())
        .then(d => { if (!d.error) inp.value = ''; });
}

// автоисчезновение flash сообщений
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.flash').forEach(f => {
        setTimeout(() => { f.style.opacity = '0'; f.style.transition = 'opacity .4s'; setTimeout(() => f.remove(), 400); }, 3500);
    });
});
