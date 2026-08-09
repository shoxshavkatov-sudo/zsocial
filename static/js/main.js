/* ============================================
   ZSocial — клиентская логика
   ============================================ */

// ===== CSRF: обёртка для AJAX + авто-инъекция в формы =====
// Глобально доступна, чтобы SPA-навигация могла пере-инъектить после смены страницы.
window.injectCSRF = function (root) {
    const token = (document.querySelector('meta[name="csrf-token"]') || {}).getAttribute ?
        document.querySelector('meta[name="csrf-token"]').getAttribute('content') : '';
    if (!token) return;
    const scope = root || document;
    scope.querySelectorAll('form[method="POST"], form[method="post"]').forEach(function (form) {
        if (form.querySelector('input[name="csrf_token"]')) return;
        const inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'csrf_token';
        inp.value = token;
        form.appendChild(inp);
    });
};
(function () {
    function getCSRF() {
        const m = document.querySelector('meta[name="csrf-token"]');
        return m ? m.getAttribute('content') : '';
    }
    // Переопределяем fetch: добавляем X-CSRFToken для mutating-запросов
    const _fetch = window.fetch;
    window.fetch = function (input, init) {
        init = init || {};
        const method = (init.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
            init.headers = init.headers || {};
            if (init.headers && typeof init.headers.set === 'function') {
                init.headers.set('X-CSRFToken', getCSRF());
            } else if (init.headers['X-CSRFToken'] === undefined) {
                init.headers['X-CSRFToken'] = getCSRF();
            }
        }
        return _fetch(input, init);
    };
    // Первичная инъекция на DOMContentLoaded
    document.addEventListener('DOMContentLoaded', function () { window.injectCSRF(); });
})();

// ===== ТЕМА =====
// Три темы: light → dark → black (OLED) → light
const THEME_ORDER = ['light', 'dark', 'black'];
// Иконка для каждой темы (показывает, ЧТО получится при переключении)
const THEME_ICON = { light: 'moon', dark: 'contrast', black: 'sun' };
function getTheme() {
    return localStorage.getItem('zs-theme') || 'light';
}
function applyTheme(t) {
    if (!THEME_ORDER.includes(t)) t = 'light';
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('zs-theme', t);
    document.cookie = 'theme=' + t + ';path=/;max-age=31536000';
}
function _themeIcon(t) { return THEME_ICON[t] || 'moon'; }
function toggleTheme() {
    const cur = getTheme();
    const next = THEME_ORDER[(THEME_ORDER.indexOf(cur) + 1) % THEME_ORDER.length];
    applyTheme(next);
    // Обновить иконку в навигации — показывает следующее состояние
    const showIcon = _themeIcon(next);
    document.querySelectorAll('.topbar-theme .icon use, .bottombar-theme .icon use').forEach(u => {
        u.setAttribute('href', '#i-' + showIcon);
    });
    // Подсветка кнопок в настройках
    document.querySelectorAll('.theme-btn').forEach(b => {
        b.className = 'btn btn-sm ' + (b.dataset.theme === next ? 'btn-primary' : 'btn-outline') + ' theme-btn';
    });
}
applyTheme(getTheme());
// При загрузке — выставить правильную иконку
document.addEventListener('DOMContentLoaded', () => {
    const showIcon = _themeIcon(getTheme());
    document.querySelectorAll('.topbar-theme .icon use, .bottombar-theme .icon use').forEach(u => {
        u.setAttribute('href', '#i-' + showIcon);
    });
});

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

// ===== ОПРОСЫ =====
function votePoll(postId, optionId) {
    fetch('/poll/' + optionId + '/vote', { method: 'POST' })
        .then(r => r.json())
        .then(d => {
            if (d.error) return flashToast(d.error);
            if (d.poll) {
                const box = document.getElementById('poll-' + postId);
                if (!box) return;
                const opts = d.poll.options;
                box.innerHTML = '<div class="poll-question">' + esc(d.poll.question) + '</div>' +
                    opts.map(o => '<div class="poll-option voted"><div class="poll-bar" style="width:' + o.percent + '%"></div><span class="poll-text">' + esc(o.text) + '</span><span class="poll-percent">' + o.percent + '%</span></div>').join('') +
                    '<div class="poll-meta">' + d.poll.total_votes + ' голосов</div>';
            }
        });
}
function loadComments(pid) {
    fetch('/post/' + pid + '/comments')
        .then(r => r.json())
        .then(list => {
            const root = list.filter(c => !c.parent_id);
            const replies = list.filter(c => c.parent_id);
            const html = root.map(c => {
                const kids = replies.filter(r => r.parent_id === c.id);
                let kidHTML = kids.map(k => commentHTML(k, true)).join('');
                return commentHTML(c, false) + kidHTML +
                    '<div class="reply-form" id="reply-form-' + c.id + '"><img src="' + (c.avatar_url || '/static/' + c.avatar) + '"><input placeholder="Ответ..." onkeypress="if(event.key===\'Enter\')submitReply(' + pid + ',' + c.id + ',this)"></div>';
            }).join('');
            document.getElementById('comments-list-' + pid).innerHTML = html;
        });
}
function commentHTML(c, isReply) {
    return '<div class="comment ' + (isReply ? 'reply' : '') + '"><img src="' + (c.avatar_url || '/static/' + c.avatar) + '" onclick="location.href=\'/profile/' + c.username + '\'"><div class="comment-content"><div class="comment-bubble"><div class="c-author">' + esc(c.username) + (c.verified ? ' <svg class="icon icon-sm verified-mark"><use href="#i-check-badge"/></svg>' : '') + '</div><div class="c-text">' + esc(c.content) + '</div></div>' + (isReply ? '' : '<button class="reply-btn" onclick="showReplyForm(' + c.id + ')">Ответить</button>') + '</div></div>';
}
function showReplyForm(cid) {
    const f = document.getElementById('reply-form-' + cid);
    if (f) { f.classList.add('visible'); f.querySelector('input').focus(); }
}
function submitReply(pid, parentId, inp) {
    const txt = inp.value.trim();
    if (!txt) return;
    const fd = new FormData();
    fd.append('content', txt);
    fd.append('parent_id', parentId);
    fetch('/post/' + pid + '/comment', { method: 'POST', body: fd })
        .then(r => r.json())
        .then(c => {
            if (c.error) return flashToast(c.error);
            loadComments(pid);
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
            loadComments(pid);
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
    if (isOwn) {
        items += '<button onclick="editPost(' + pid + ')"><svg class="icon icon-sm"><use href="#i-settings"/></svg> Изменить</button>';
        items += '<button class="danger" onclick="deleteOwnPost(' + pid + ')"><svg class="icon icon-sm"><use href="#i-trash"/></svg> Удалить</button>';
    }
    items += '<button onclick="doRepost(' + pid + ')"><svg class="icon icon-sm"><use href="#i-share"/></svg> Поделиться в ленту</button>';
    items += '<button onclick="copyLink(' + pid + ')"><svg class="icon icon-sm"><use href="#i-share"/></svg> Копировать ссылку</button>';
    if (!isOwn) items += '<button class="danger" onclick="reportPost(' + pid + ')"><svg class="icon icon-sm"><use href="#i-flag"/></svg> Пожаловаться</button>';
    if (isAdmin && !isOwn) items += '<button class="danger" onclick="deleteOwnPost(' + pid + ')"><svg class="icon icon-sm"><use href="#i-trash"/></svg> Удалить (админ)</button>';
    menu.innerHTML = items;
    document.body.appendChild(menu);
    const rect = e.currentTarget.getBoundingClientRect();
    menu.style.top = (rect.bottom + 4) + 'px';
    menu.style.right = (window.innerWidth - rect.right) + 'px';
}
function editPost(pid) {
    closeAllMenus();
    location.href = '/post/' + pid + '/edit';
}
function doRepost(pid) {
    closeAllMenus();
    const quote = prompt('Добавить комментарий к репосту (необязательно):');
    if (quote === null) return;
    fetch('/post/' + pid + '/repost', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({quote: quote}) })
        .then(r => r.json()).then(d => { if (d.error) return flashToast(d.error); flashToast('Поделились!'); })
        .catch(() => flashToast('Ошибка'));
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
function copyLink(pid) {
    const url = location.origin + '/feed#' + pid;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(() => flashToast('Ссылка скопирована')).catch(() => flashToast('Ошибка копирования'));
    } else {
        const ta = document.createElement('textarea'); ta.value = url; document.body.appendChild(ta);
        ta.select(); document.execCommand('copy'); ta.remove(); flashToast('Ссылка скопирована');
    }
}
function reportPost(pid) {
    const reason = prompt('Укажите причину жалобы (необязательно):');
    if (reason === null) return;
    fetch('/report', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({target_type:'post', target_id:pid, reason:reason||''}) })
        .then(r => r.json()).then(d => { if (d.error) return flashToast(d.error); flashToast('Жалоба отправлена'); })
        .catch(() => flashToast('Ошибка'));
}
function sharePost(pid) {
    const url = location.origin + '/feed#' + pid;
    if (navigator.share) {
        navigator.share({ title: document.title, url: url }).catch(() => {});
    } else {
        copyLink(pid);
    }
}

// ===== ХЕШТЕГИ =====
function searchTag(tag) {
    location.href = '/feed?tag=' + encodeURIComponent(tag);
}

// ===== LIGHTBOX (медиа-галерея) =====
function openLightbox(src) {
    const lb = document.createElement('div');
    lb.className = 'lightbox';
    lb.innerHTML = '<img src="' + src + '">';
    lb.onclick = () => lb.remove();
    document.body.appendChild(lb);
}

// ===== МОДАЛЬНОЕ ОКНО СОЗДАНИЯ ПОСТА (кнопка +) =====
let composeImage = null;
function openComposeModal() {
    document.getElementById('compose-modal').classList.add('visible');
    setTimeout(() => document.getElementById('compose-modal-text').focus(), 100);
}
function closeComposeModal() {
    document.getElementById('compose-modal').classList.remove('visible');
    document.getElementById('compose-modal-text').value = '';
    document.getElementById('compose-poll-question').value = '';
    document.getElementById('compose-poll-options').value = '';
    document.getElementById('compose-poll-box').style.display = 'none';
    removeComposeImage();
}
function previewComposeImage(inp) {
    if (!inp.files[0]) return;
    composeImage = inp.files[0];
    const r = new FileReader();
    r.onload = e => {
        const p = document.getElementById('compose-modal-preview');
        document.getElementById('compose-modal-preview-img').src = e.target.result;
        p.style.display = 'block';
    };
    r.readAsDataURL(composeImage);
}
function removeComposeImage() {
    composeImage = null;
    const p = document.getElementById('compose-modal-preview');
    p.style.display = 'none';
    document.getElementById('compose-modal-preview-img').src = '';
}
function submitComposeModal() {
    const content = document.getElementById('compose-modal-text').value.trim();
    const pollBox = document.getElementById('compose-poll-box');
    const hasPoll = pollBox.style.display !== 'none';
    const pollQ = document.getElementById('compose-poll-question').value.trim();
    const pollOpts = document.getElementById('compose-poll-options').value.trim();
    if (hasPoll && pollQ && pollOpts.split('\n').filter(o => o.trim()).length < 2) {
        return flashToast('Минимум 2 варианта опроса');
    }
    if (!content && !composeImage && !(hasPoll && pollQ && pollOpts)) return flashToast('Пусто');
    const fd = new FormData();
    fd.append('content', content);
    if (composeImage) fd.append('image', composeImage);
    if (hasPoll && pollQ && pollOpts) {
        fd.append('poll_question', pollQ);
        fd.append('poll_options', pollOpts);
    }
    fetch('/post/create', { method: 'POST', body: fd })
        .then(r => { if (r.redirected) { closeComposeModal(); location.reload(); } });
}
function togglePollInModal() {
    const box = document.getElementById('compose-poll-box');
    const btn = document.getElementById('poll-toggle-btn');
    const visible = box.style.display !== 'none';
    box.style.display = visible ? 'none' : 'block';
    btn.classList.toggle('active', !visible);
    if (!visible) document.getElementById('compose-poll-question').focus();
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
function adminResolveReport(rid) {
    fetch('/admin/report/' + rid + '/resolve', { method: 'POST' })
        .then(r => r.json())
        .then(d => { if (!d.error) { const row = document.getElementById('report-' + rid); if (row) row.remove(); flashToast('Жалоба закрыта'); } });
}
function adminDeletePost(pid, rid) {
    fetch('/admin/post/' + pid + '/delete', { method: 'POST' })
        .then(r => r.json())
        .then(d => { if (!d.error) { if (rid) adminResolveReport(rid); flashToast('Пост удалён'); } });
}

// ===== ЧАТ (WebSocket) =====
let chatSocket = null;
let typingTimer = null;
let isTyping = false;
const REACTION_EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🙏'];

function initSocket(myId, partnerId) {
    if (typeof io === 'undefined') return;
    chatSocket = io();

    chatSocket.on('new_message', (data) => {
        if (data.sender_id !== partnerId && data.receiver_id !== partnerId) return;
        const container = document.getElementById('chat-messages');
        if (!container) return;
        // скрываем индикатор печати когда пришло сообщение
        hideTyping();
        appendMessage(container, data, myId);
        container.scrollTop = container.scrollHeight;
    });

    // Индикатор «печатает»
    chatSocket.on('typing', (d) => { if (d.from === partnerId) showTyping(); });
    chatSocket.on('stop_typing', (d) => { if (d.from === partnerId) hideTyping(); });

    // Удаление сообщения
    chatSocket.on('message_deleted', (d) => {
        const el = document.getElementById('msg-' + d.id);
        if (el) el.remove();
    });

    // Реакции
    chatSocket.on('message_reaction', (d) => renderReactions(d.id, d.reactions));
}

function showTyping() {
    const t = document.getElementById('typing-indicator');
    if (t) t.classList.add('visible');
}
function hideTyping() {
    const t = document.getElementById('typing-indicator');
    if (t) t.classList.remove('visible');
}

// Отправка индикатора печати при вводе
function notifyTyping(partnerId) {
    if (!chatSocket) return;
    if (!isTyping) {
        isTyping = true;
        chatSocket.emit('typing', { to: partnerId });
    }
    clearTimeout(typingTimer);
    typingTimer = setTimeout(() => {
        isTyping = false;
        chatSocket.emit('stop_typing', { to: partnerId });
    }, 2000);
}

// Удаление сообщения
function deleteMsg(mid) {
    if (!confirm('Удалить сообщение?')) return;
    fetch('/chat/' + mid + '/delete', { method: 'POST' })
        .then(r => r.json())
        .then(d => { if (d.error) flashToast(d.error); });
}

// Реакции
function showReactionPicker(mid, e) {
    e.stopPropagation();
    document.querySelectorAll('.reaction-picker').forEach(p => p.remove());
    const picker = document.createElement('div');
    picker.className = 'reaction-picker';
    picker.innerHTML = REACTION_EMOJIS.map(em => `<button onclick="toggleReaction(${mid}, '${em}')">${em}</button>`).join('');
    document.body.appendChild(picker);
    const rect = e.currentTarget.getBoundingClientRect();
    picker.style.top = (rect.top - 40) + 'px';
    picker.style.left = rect.left + 'px';
    setTimeout(() => document.addEventListener('click', () => picker.remove(), { once: true }), 10);
}
function toggleReaction(mid, emoji) {
    document.querySelectorAll('.reaction-picker').forEach(p => p.remove());
    fetch('/chat/' + mid + '/react', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({emoji}) })
        .then(r => r.json()).then(d => { if (d.error) flashToast(d.error); });
}
function renderReactions(mid, reactions) {
    const msg = document.getElementById('msg-' + mid);
    if (!msg) return;
    let bar = msg.querySelector('.msg-reactions');
    if (!reactions || reactions.length === 0) { if (bar) bar.remove(); return; }
    if (!bar) { bar = document.createElement('div'); bar.className = 'msg-reactions'; msg.appendChild(bar); }
    bar.innerHTML = reactions.map(r => `<span class="msg-reaction"><span class="reaction-emoji">${r.emoji}</span><span class="reaction-count">${r.count}</span></span>`).join('');
}

function renderMessageHTML(data, isMine) {
    const t = data.msg_type || 'text';
    let inner = '';
    if (t === 'audio' && data.file_url_full) {
        inner = `<div class="msg-bubble voice-msg">
            <button class="voice-play-btn" onclick="playVoice(this)" data-src="${data.file_url_full}"><svg class="icon"><use href="#i-play"/></svg></button>
            <div class="voice-waveform">${Array.from({length:20},(_,i)=>`<div class="wave-bar" style="height:${i%3===0?100:i%2===0?60:40}%;animation-delay:${i*0.05}s"></div>`).join('')}</div>
            <span class="voice-duration">${fmtDuration(data.duration||0)}</span>
            <audio src="${data.file_url_full}" preload="none"></audio>
        </div>`;
    } else if (t === 'image' && data.file_url_full) {
        inner = `<img src="${data.file_url_full}" class="msg-image" onclick="window.open('${data.file_url_full}')">`;
    } else if (t === 'video' && data.file_url_full) {
        inner = `<video src="${data.file_url_full}" class="msg-video" controls></video>`;
    } else if (t === 'file' && data.file_url_full) {
        inner = `<div class="msg-bubble msg-file">
            <div class="msg-file-icon"><svg class="icon"><use href="#i-file"/></svg></div>
            <div class="msg-file-info"><div class="msg-file-name">${esc(data.file_name||'Файл')}</div><div class="msg-file-size">${Math.round((data.file_size||0)/1024)} КБ</div></div>
            <a href="${data.file_url_full}" download style="color:inherit"><svg class="icon"><use href="#i-share"/></svg></a>
        </div>`;
    } else {
        inner = `<div class="msg-bubble">${esc(data.content)}</div>`;
    }
    return inner + `<div class="msg-time">${data.time}</div>`;
}

function appendMessage(container, data, myId) {
    const isMine = data.sender_id === myId;
    const div = document.createElement('div');
    div.className = 'msg ' + (isMine ? 'mine' : 'theirs');
    div.innerHTML = renderMessageHTML(data, isMine);
    container.appendChild(div);
}

function fmtDuration(sec) {
    const m = Math.floor(sec/60), s = sec%60;
    return String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
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

// ===== ОТПРАВКА ФАЙЛОВ =====
function sendFile(partnerId, input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    const fd = new FormData();
    fd.append('receiver_id', partnerId);
    fd.append('content', '');
    fd.append('file', file);
    // показываем превью
    showSendingIndicator();
    fetch('/chat/send', { method: 'POST', body: fd })
        .then(r => r.json())
        .then(d => { hideSendingIndicator(); if (d.error) flashToast(d.error); input.value=''; });
}

// ===== ЗАПИСЬ ГОЛОСА (MediaRecorder) =====
let mediaRecorder = null;
let audioChunks = [];
let recordStream = null;
let recordTimer = null;
let recordSeconds = 0;

async function toggleRecording(partnerId, btn) {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        stopAndSendRecording(partnerId);
        return;
    }
    try {
        recordStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioChunks = [];
        // Выбираем подходящий mimeType
        let opts = {};
        if (MediaRecorder.isTypeSupported('audio/webm')) opts.mimeType = 'audio/webm';
        else if (MediaRecorder.isTypeSupported('audio/mp4')) opts.mimeType = 'audio/mp4';
        mediaRecorder = new MediaRecorder(recordStream, opts);
        mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
        mediaRecorder.onstop = () => { recordStream.getTracks().forEach(t => t.stop()); };
        mediaRecorder.start();
        recordSeconds = 0;
        updateRecTime();
        recordTimer = setInterval(() => { recordSeconds++; updateRecTime(); }, 1000);
        document.getElementById('voice-recording-bar').classList.remove('hidden');
        btn.classList.add('recording');
        btn.innerHTML = '<svg class="icon"><use href="#i-pause"/></svg>';
    } catch (e) {
        flashToast('Нет доступа к микрофону');
    }
}

function updateRecTime() {
    const el = document.getElementById('rec-time');
    if (el) el.textContent = fmtDuration(recordSeconds);
}

function cancelRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
    }
    clearInterval(recordTimer);
    document.getElementById('voice-recording-bar').classList.add('hidden');
    const btn = document.getElementById('mic-btn');
    if (btn) { btn.classList.remove('recording'); btn.innerHTML = '<svg class="icon"><use href="#i-mic"/></svg>'; }
    audioChunks = [];
}

function stopAndSendRecording(partnerId) {
    if (!mediaRecorder || mediaRecorder.state !== 'recording') return;
    const duration = recordSeconds;
    mediaRecorder.onstop = async () => {
        recordStream.getTracks().forEach(t => t.stop());
        const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
        const ext = (mediaRecorder.mimeType || 'audio/webm').includes('mp4') ? 'm4a' : 'webm';
        const file = new File([blob], `voice_${Date.now()}.${ext}`, { type: blob.type });
        const fd = new FormData();
        fd.append('receiver_id', partnerId);
        fd.append('content', '');
        fd.append('msg_type', 'audio');
        fd.append('duration', duration);
        fd.append('file', file);
        showSendingIndicator();
        try {
            await fetch('/chat/send', { method: 'POST', body: fd });
        } finally {
            hideSendingIndicator();
        }
    };
    mediaRecorder.stop();
    clearInterval(recordTimer);
    document.getElementById('voice-recording-bar').classList.add('hidden');
    const btn = document.getElementById('mic-btn');
    if (btn) { btn.classList.remove('recording'); btn.innerHTML = '<svg class="icon"><use href="#i-mic"/></svg>'; }
}

// ===== ВОСПРОИЗВЕДЕНИЕ ГОЛОСОВОГО =====
let currentAudio = null;
function playVoice(btn) {
    const audio = btn.parentElement.querySelector('audio');
    if (!audio) return;
    if (currentAudio && currentAudio !== audio) {
        currentAudio.pause();
        // сбросить иконку прошлого
        document.querySelectorAll('.voice-play-btn').forEach(b => b.innerHTML = '<svg class="icon"><use href="#i-play"/></svg>');
    }
    currentAudio = audio;
    if (audio.paused) {
        audio.play();
        btn.innerHTML = '<svg class="icon"><use href="#i-pause"/></svg>';
        audio.onended = () => { btn.innerHTML = '<svg class="icon"><use href="#i-play"/></svg>'; };
    } else {
        audio.pause();
        btn.innerHTML = '<svg class="icon"><use href="#i-play"/></svg>';
    }
}

// ===== ИНДИКАТОР ОТПРАВКИ =====
function showSendingIndicator() {
    const area = document.getElementById('chat-preview-area');
    if (area) area.innerHTML = '<div class="chat-preview"><div class="spinner"></div><div class="preview-info">Отправка...</div></div>';
}
function hideSendingIndicator() {
    const area = document.getElementById('chat-preview-area');
    if (area) area.innerHTML = '';
}

// автоисчезновение flash сообщений
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.flash').forEach(f => {
        setTimeout(() => { f.style.opacity = '0'; f.style.transition = 'opacity .4s'; setTimeout(() => f.remove(), 400); }, 3500);
    });
});


// ===================================================================
//  ВЕБ-ЗВОНКИ (WebRTC + Socket.IO сигналинг)
//  Голосовые и видеозвонки 1-на-1 прямо из чата.
// ===================================================================
let pc = null;           // RTCPeerConnection
let localStream = null;  // моя камера/микрофон
let callPartnerId = null;
let callPartnerName = '';
let isCaller = false;
let callWithVideo = false;
let callTimer = null;
let callStartTime = 0;
let pendingCandidates = [];  // ICE-кандидаты, пришедшие ДО setRemoteDescription

// ICE-серверы: STUN (для лёгких NAT) + TURN (для симметричного/жёсткого NAT,
// например мобильные операторы). Несколько публичных STUN + TURN-серверы.
const ICE_SERVERS = {
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
        { urls: 'stun:stun2.l.google.com:19302' },
        { urls: 'stun:stun3.l.google.com:19302' },
        { urls: 'stun:stun4.l.google.com:19302' },
        // Metered TURN — для строгих NAT (симметричный/жёсткий).
        { urls: 'turn:a.relay.metered.ca:80',    username: 'e593c81e73a1556cc6bf0a96', credential: 'kTKCzKpzH+Go1aBw' },
        { urls: 'turn:a.relay.metered.ca:443',   username: 'e593c81e73a1556cc6bf0a96', credential: 'kTKCzKpzH+Go1aBw' },
        { urls: 'turn:a.relay.metered.ca:443?transport=tcp', username: 'e593c81e73a1556cc6bf0a96', credential: 'kTKCzKpzH+Go1aBw' },
    ],
    iceTransportPolicy: 'all',
};

function _ensureCallSocket() {
    // сокет чата уже создан в initSocket — переиспользуем его для звонков
    if (!chatSocket && typeof io !== 'undefined') {
        chatSocket = io();
        _registerCallListeners();
    } else if (chatSocket && !chatSocket._callBound) {
        _registerCallListeners();
    }
}

function _registerCallListeners() {
    if (!chatSocket) return;
    chatSocket._callBound = true;

    // Входящий звонок
    chatSocket.on('call_offer', (d) => {
        if (document.getElementById('call-overlay') && document.getElementById('call-overlay').classList.contains('active')) {
            // уже в звонке — отклоняем
            chatSocket.emit('call_reject', { to: d.from });
            return;
        }
        isCaller = false;
        callPartnerId = d.from;
        callPartnerName = d.from_name || 'Пользователь';
        callWithVideo = d.video;
        _showIncomingCall(d);
    });

    // Ответ (приняли мой offer)
    chatSocket.on('call_answer', async (d) => {
        if (!pc) return;
        try {
            await pc.setRemoteDescription(new RTCSessionDescription(d.sdp));
            // Применяем кандидаты, накопленные за время ожидания ответа
            for (const c of pendingCandidates) {
                try { await pc.addIceCandidate(c); } catch (e) {}
            }
            pendingCandidates = [];
            _setStatus('Соединение установлено');
            _startCallTimer();
        } catch (e) { console.error('setRemoteDescription (answer):', e); }
    });

    // ICE-кандидат от собеседника.
    // ВАЖНО: кандидаты могут прийти ДО того, как мы приняли звонок и создали pc
    // (на стороне callee) — буферизуем их и применяем после setRemoteDescription.
    chatSocket.on('call_ice', async (d) => {
        if (!d.candidate) return;
        try {
            if (pc && pc.remoteDescription) {
                await pc.addIceCandidate(new RTCIceCandidate(d.candidate));
            } else {
                pendingCandidates.push(new RTCIceCandidate(d.candidate));
            }
        } catch (e) { console.warn('addIceCandidate:', e); }
    });

    // Завершение звонка собеседником
    chatSocket.on('call_end', () => _endCall('remote'));
    // Отклонение звонка
    chatSocket.on('call_reject', () => {
        _endCall('rejected');
        flashToast('Звонок отклонён');
    });
}

// ─── Инициация звонка ───
async function startCall(partnerId, partnerName, video) {
    if (!chatSocket) { flashToast('Нет соединения'); return; }
    if (document.getElementById('call-overlay')?.classList.contains('active')) return;

    callPartnerId = partnerId;
    callPartnerName = partnerName || 'Собеседник';
    callWithVideo = !!video;
    isCaller = true;

    _showCallOverlay('active');
    _setStatus('Звоним...');

    try {
        localStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: callWithVideo ? { width: 640, height: 480 } : false,
        });
    } catch (e) {
        flashToast('Нет доступа к ' + (callWithVideo ? 'камере/микрофону' : 'микрофону'));
        _hideCallOverlay();
        return;
    }

    // Показываем локальное видео
    const lv = document.getElementById('local-video');
    if (lv) { lv.srcObject = localStream; lv.style.display = callWithVideo ? 'block' : 'none'; }

    _createPeerConnection();

    localStream.getTracks().forEach(t => pc.addTrack(t, localStream));

    try {
        const offer = await pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: callWithVideo });
        await pc.setLocalDescription(offer);
        chatSocket.emit('call_offer', {
            to: partnerId,
            from_name: document.body.dataset.userName || 'Я',
            video: callWithVideo,
            sdp: offer,
        });
    } catch (e) {
        console.error('createOffer:', e);
        _endCall('error');
    }
}

function _createPeerConnection() {
    pc = new RTCPeerConnection(ICE_SERVERS);

    // Отправляем свои ICE-кандидаты (trickle ICE)
    pc.onicecandidate = (e) => {
        if (e.candidate && chatSocket && callPartnerId) {
            chatSocket.emit('call_ice', { to: callPartnerId, candidate: e.candidate });
        }
    };

    // Поток собеседника (видео/аудио)
    pc.ontrack = (e) => {
        const rv = document.getElementById('remote-video');
        const ra = document.getElementById('remote-audio');
        if (rv && e.streams[0]) {
            rv.srcObject = e.streams[0];
            if (callWithVideo) rv.style.display = 'block';
        }
        if (ra && e.streams[0]) ra.srcObject = e.streams[0];
    };

    pc.oniceconnectionstatechange = () => {
        const st = pc.iceConnectionState;
        console.log('[call] ICE:', st);
        if (st === 'connected') {
            _setStatus('В разговоре');
        } else if (st === 'checking') {
            _setStatus('Соединение...');
        } else if (st === 'disconnected') {
            _setStatus('Сигнал потерян...');
        } else if (st === 'failed') {
            console.warn('[call] ICE failed — TURN мог быть недоступен');
            _setStatus('Сбой соединения');
            setTimeout(() => _endCall('failed'), 2000);
        }
    };

    pc.onconnectionstatechange = () => {
        console.log('[call] PC:', pc.connectionState);
        if (pc.connectionState === 'failed') {
            _setStatus('Сбой соединения');
            setTimeout(() => _endCall('failed'), 2000);
        }
    };
}

// ─── Входящий звонок (показываем окно «Входящий звонок») ───
let pendingOffer = null;  // SDP offer от звонящего

function _showIncomingCall(d) {
    pendingOffer = d.sdp;  // сохраняем offer для acceptCall
    _showCallOverlay('incoming');
    document.getElementById('call-status').textContent = 'Входящий ' + (callWithVideo ? 'видеозвонок' : 'звонок');
    document.getElementById('call-name').textContent = callPartnerName;
}

async function acceptCall() {
    if (!pendingOffer) return;
    document.getElementById('incoming-buttons').style.display = 'none';
    document.getElementById('active-buttons').style.display = 'flex';
    _setStatus('Соединение...');

    try {
        localStream = await navigator.mediaDevices.getUserMedia({
            audio: true,
            video: callWithVideo ? { width: 640, height: 480 } : false,
        });
    } catch (e) {
        flashToast('Нет доступа к ' + (callWithVideo ? 'камере/микрофону' : 'микрофону'));
        chatSocket.emit('call_reject', { to: callPartnerId });
        _hideCallOverlay();
        return;
    }

    const lv = document.getElementById('local-video');
    if (lv) { lv.srcObject = localStream; lv.style.display = callWithVideo ? 'block' : 'none'; }

    _createPeerConnection();
    localStream.getTracks().forEach(t => pc.addTrack(t, localStream));

    try {
        await pc.setRemoteDescription(new RTCSessionDescription(pendingOffer));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        chatSocket.emit('call_answer', { to: callPartnerId, sdp: answer });
        // Применяем кандидаты, накопленные до принятия звонка
        for (const c of pendingCandidates) {
            try { await pc.addIceCandidate(c); } catch (e) {}
        }
        pendingCandidates = [];
        _startCallTimer();
    } catch (e) {
        console.error('acceptCall:', e);
        _endCall('error');
    }
}

function rejectCall() {
    if (chatSocket) chatSocket.emit('call_reject', { to: callPartnerId });
    pendingOffer = null;
    _hideCallOverlay();
}

// ─── Завершение звонка ───
function endCall() { _endCall('local'); }

function _endCall(reason) {
    if (chatSocket && callPartnerId && reason !== 'remote') {
        chatSocket.emit('call_end', { to: callPartnerId });
    }
    if (callTimer) { clearInterval(callTimer); callTimer = null; }
    if (pc) { try { pc.close(); } catch (e) {} pc = null; }
    if (localStream) {
        localStream.getTracks().forEach(t => t.stop());
        localStream = null;
    }
    pendingCandidates = [];
    callPartnerId = null;
    pendingOffer = null;
    _hideCallOverlay();
}

// ─── Управление: вкл/выкл микрофон и камеру ───
let micEnabled = true;
let camEnabled = true;
function toggleMic() {
    if (!localStream) return;
    micEnabled = !micEnabled;
    localStream.getAudioTracks().forEach(t => t.enabled = micEnabled);
    const btn = document.getElementById('btn-mic-toggle');
    if (btn) {
        btn.classList.toggle('off', !micEnabled);
        btn.querySelector('use').setAttribute('href', micEnabled ? '#i-mic' : '#i-mic-off');
    }
}
function toggleCam() {
    if (!localStream || !callWithVideo) return;
    camEnabled = !camEnabled;
    localStream.getVideoTracks().forEach(t => t.enabled = camEnabled);
    const btn = document.getElementById('btn-cam-toggle');
    if (btn) btn.classList.toggle('off', !camEnabled);
    const lv = document.getElementById('local-video');
    if (lv) lv.style.opacity = camEnabled ? '1' : '0.2';
}

// ─── UI оверлея ───
// showButtons: 'incoming' | 'active' | null (не менять)
function _showCallOverlay(showButtons) {
    let ov = document.getElementById('call-overlay');
    if (!ov) {
        // динамически создаём, если отсутствует (другая страница)
        return;
    }
    ov.classList.add('active');
    document.getElementById('call-name').textContent = callPartnerName || 'Собеседник';
    document.getElementById('call-type').textContent = callWithVideo ? 'Видеозвонок' : 'Голосовой звонок';
    document.getElementById('remote-video').style.display = callWithVideo ? 'block' : 'none';
    document.getElementById('local-video').style.display = callWithVideo ? 'block' : 'none';
    document.getElementById('avatar-call').style.display = callWithVideo ? 'none' : 'flex';
    document.getElementById('call-timer').textContent = '00:00';
    // Кнопки управляются вызывающей функцией, а не оверлеем
    if (showButtons === 'incoming') {
        document.getElementById('incoming-buttons').style.display = 'flex';
        document.getElementById('active-buttons').style.display = 'none';
    } else if (showButtons === 'active') {
        document.getElementById('incoming-buttons').style.display = 'none';
        document.getElementById('active-buttons').style.display = 'flex';
    }
}
function _hideCallOverlay() {
    const ov = document.getElementById('call-overlay');
    if (ov) ov.classList.remove('active');
    if (callTimer) { clearInterval(callTimer); callTimer = null; }
    const rv = document.getElementById('remote-video');
    const lv = document.getElementById('local-video');
    if (rv) rv.srcObject = null;
    if (lv) lv.srcObject = null;
}
function _setStatus(txt) {
    const el = document.getElementById('call-status');
    if (el) el.textContent = txt;
}
function _startCallTimer() {
    callStartTime = Date.now();
    callTimer = setInterval(() => {
        const s = Math.floor((Date.now() - callStartTime) / 1000);
        const m = Math.floor(s / 60).toString().padStart(2, '0');
        const ss = (s % 60).toString().padStart(2, '0');
        const el = document.getElementById('call-timer');
        if (el) el.textContent = m + ':' + ss;
    }, 1000);
}

// Авто-привязка слушателей звонков к сокету (если чат-страница)
document.addEventListener('DOMContentLoaded', () => {
    // initSocket уже вызывается в chat.html; слушатели навешиваются там же.
    // Эта подушка добавляет listener-ы, если сокет создан позже.
    const tryBind = setInterval(() => {
        if (chatSocket && !chatSocket._callBound) {
            _registerCallListeners();
            clearInterval(tryBind);
        }
    }, 1000);
    setTimeout(() => clearInterval(tryBind), 10000);
});


// ===================================================================
//  ГРУППОВОЙ ЧАТ (как в Telegram) + ГОЛОСОВЫЕ КОМНАТЫ (как в Discord)
// ===================================================================
let groupSocket = null;
let currentGroupId = null;
let groupTypingTimer = null;

function initGroupChat(groupId) {
    currentGroupId = groupId;
    if (typeof io === 'undefined') return;

    groupSocket = io();
    groupSocket.emit('group_join', { group_id: groupId });

    // Прокрутка вниз
    const c = document.getElementById('group-chat');
    if (c) c.scrollTop = c.scrollHeight;

    // Новое сообщение группы
    groupSocket.on('group_message', (d) => {
        if (d.group_id !== groupId) return;
        appendGroupMessage(d);
        if (c) c.scrollTop = c.scrollHeight;
        hideGroupTyping();
    });

    // Удаление сообщения
    groupSocket.on('group_message_deleted', (d) => {
        const el = document.getElementById('gcmsg-' + d.id);
        if (el) el.remove();
    });

    // Индикатор печати
    groupSocket.on('group_typing', (d) => {
        if (d.from === document.body.dataset.userId) return;
        showGroupTyping();
    });
    groupSocket.on('group_stop_typing', () => hideGroupTyping());

    // === Голосовые комнаты: сигналинг ===
    _bindVoiceEvents();
}

function sendGroupMessage(slug) {
    const inp = document.getElementById('gc-text-input');
    if (!inp) return;
    const content = inp.value.trim();
    if (!content) return;
    inp.value = '';
    if (groupSocket) groupSocket.emit('group_stop_typing', { group_id: currentGroupId });

    const fd = new FormData();
    fd.append('content', content);
    fetch('/group/' + slug + '/chat/send', {
        method: 'POST', body: fd,
        headers: { 'X-CSRFToken': (document.querySelector('meta[name=csrf-token]') || {}).content || '' }
    }).then(r => r.json()).then(d => {
        if (d.error) flashToast(d.error);
    }).catch(() => flashToast('Ошибка отправки'));
}

function sendGroupFile(slug, input) {
    if (!input.files[0]) return;
    const fd = new FormData();
    fd.append('content', '');
    fd.append('file', input.files[0]);
    fetch('/group/' + slug + '/chat/send', {
        method: 'POST', body: fd,
        headers: { 'X-CSRFToken': (document.querySelector('meta[name=csrf-token]') || {}).content || '' }
    }).then(r => r.json()).then(d => {
        if (d.error) flashToast(d.error);
        input.value = '';
    });
}

function deleteGroupMsg(mid, slug) {
    if (!confirm('Удалить сообщение?')) return;
    fetch('/group/' + slug + '/chat/delete/' + mid, {
        method: 'POST',
        headers: { 'X-CSRFToken': (document.querySelector('meta[name=csrf-token]') || {}).content || '' }
    }).then(r => r.json()).then(d => {
        if (d.error) flashToast(d.error);
    });
}

function appendGroupMessage(d) {
    const c = document.getElementById('group-chat');
    if (!c) return;
    const me = document.body.dataset.userId;
    const mine = (d.sender_id == me);
    // убираем заглушку «нет сообщений»
    const empty = c.querySelector('.gc-empty');
    if (empty) empty.remove();

    let mediaHTML = '';
    if (d.msg_type === 'image' && d.file_url) {
        mediaHTML = '<img class="gc-image" src="' + _mediaUrl(d.file_url) + '" onclick="openLightbox(\'' + _mediaUrl(d.file_url) + '\')">';
    } else if (d.msg_type === 'video' && d.file_url) {
        mediaHTML = '<video class="gc-video" src="' + _mediaUrl(d.file_url) + '" controls></video>';
    } else if (d.msg_type === 'file' && d.file_url) {
        mediaHTML = '<a class="gc-file" href="' + _mediaUrl(d.file_url) + '" download><svg class="icon"><use href="#i-file"/></svg><span>' + esc(d.file_name || 'Файл') + '</span></a>';
    }

    const div = document.createElement('div');
    div.className = 'gc-msg' + (mine ? ' mine' : '');
    div.id = 'gcmsg-' + d.id;
    div.innerHTML = (mine ? '' : '<img class="gc-avatar" src="' + _mediaUrl(d.sender_avatar) + '">') +
        '<div class="gc-bubble-wrap">' +
        (mine ? '' : '<div class="gc-sender">' + esc(d.sender_name) + '</div>') +
        mediaHTML +
        (d.content ? '<div class="gc-text">' + _urlize(d.content) + '</div>' : '') +
        '<div class="gc-meta">' + (d.created_at || 'сейчас') +
        (mine ? ' <button class="gc-del" onclick="deleteGroupMsg(' + d.id + ',\'' + _slug() + '\')" title="Удалить"><svg class="icon icon-sm"><use href="#i-trash"/></svg></button>' : '') +
        '</div></div>';
    c.appendChild(div);
}

function _mediaUrl(p) {
    if (!p) return '';
    if (p.startsWith('http') || p.startsWith('/')) return p;
    if (p.startsWith('uploads/')) return '/' + p;
    return '/static/' + p;
}
function _slug() {
    const gp = document.querySelector('.group-page');
    return gp ? gp.dataset.slug : '';
}
function _urlize(t) {
    return esc(t).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
}

function notifyGroupTyping(gid) {
    if (!groupSocket) return;
    groupSocket.emit('group_typing', { group_id: gid, name: document.body.dataset.userName });
    clearTimeout(groupTypingTimer);
    groupTypingTimer = setTimeout(() => {
        groupSocket.emit('group_stop_typing', { group_id: gid });
    }, 1500);
}
function showGroupTyping() {
    const t = document.getElementById('group-typing');
    if (t) t.classList.remove('hidden');
}
function hideGroupTyping() {
    const t = document.getElementById('group-typing');
    if (t) t.classList.add('hidden');
}

function joinGroup(slug) {
    fetch('/group/' + slug + '/join', {
        method: 'POST',
        headers: { 'X-CSRFToken': (document.querySelector('meta[name=csrf-token]') || {}).content || '' }
    }).then(r => r.json()).then(() => location.reload());
}
function leaveGroup(slug) {
    if (!confirm('Покинуть группу?')) return;
    fetch('/group/' + slug + '/join', {
        method: 'POST',
        headers: { 'X-CSRFToken': (document.querySelector('meta[name=csrf-token]') || {}).content || '' }
    }).then(r => r.json()).then(() => location.href = '/groups');
}

function createVoiceRoom(slug) {
    const inp = document.getElementById('voice-room-name');
    const name = (inp && inp.value.trim()) || 'Голосовая';
    const fd = new FormData();
    fd.append('name', name);
    // fetch-обёртка сама добавит X-CSRFToken
    fetch('/group/' + slug + '/voice/create', { method: 'POST', body: fd })
        .then(r => r.json())
        .then(d => {
            if (d.error) return flashToast(d.error);
            flashToast('Комната создана');
            // SPA: перезагружаем только содержимое группы
            setTimeout(() => {
                if (globalThis.__spaNavigate) globalThis.__spaNavigate(location.href, false);
                else location.reload();
            }, 400);
        })
        .catch(() => flashToast('Ошибка создания комнаты'));
}

// Свернуть/развернуть тело голосовой комнаты
function toggleVoiceRoom(roomId) {
    const room = document.querySelector('.voice-room[data-room-id="' + roomId + '"]');
    if (!room) return;
    const body = room.querySelector('.voice-room-body');
    if (body) body.style.display = (body.style.display === 'none') ? '' : 'none';
}


// ===================================================================
//  ГОЛОСОВЫЕ КОМНАТЫ — WebRTC mesh (peer-to-peer между всеми)
// ===================================================================
let voiceSocket = null;       // переиспользуем groupSocket
let voiceLocalStream = null;
let voicePeers = {};          // { userId: RTCPeerConnection }
let voiceCurrentRoom = null;
let voiceMuted = false;

function _bindVoiceEvents() {
    if (!groupSocket || groupSocket._voiceBound) return;
    groupSocket._voiceBound = true;
    voiceSocket = groupSocket;

    // Кто-то вошёл в комнату — инициируем к нему подключение
    voiceSocket.on('voice_user_joined', (d) => {
        if (!voiceCurrentRoom) return;
        // Новый участник: мы шлём ему offer (мы = «инициатор»)
        if (!voicePeers[d.user_id]) {
            _createVoicePeer(d.user_id, true);
        }
    });

    // Список уже присутствующих (при нашем входе)
    voiceSocket.on('voice_peers', (d) => {
        d.peers.forEach(p => {
            if (!voicePeers[p.user_id]) _createVoicePeer(p.user_id, true);
        });
    });

    // Кто-то вышел
    voiceSocket.on('voice_user_left', (d) => {
        _closeVoicePeer(d.user_id);
        _removeVoiceParticipantEl(d.user_id);
    });

    // Сигнал от другого пира (offer/answer/ICE)
    voiceSocket.on('voice_signal', (d) => {
        _handleVoiceSignal(d.from, d.signal);
    });

    // Кто-то вкл/выкл микрофон
    voiceSocket.on('voice_mute_changed', (d) => {
        const el = document.querySelector('.voice-participant[data-uid="' + d.user_id + '"] .vr-muted');
        if (d.muted && !el) {
            const p = document.querySelector('.voice-participant[data-uid="' + d.user_id + '"]');
            if (p) p.insertAdjacentHTML('beforeend', '<svg class="icon icon-sm vr-muted"><use href="#i-mic-off"/></svg>');
        } else if (!d.muted && el) {
            el.remove();
        }
    });
}

async function joinVoiceRoom(roomId) {
    if (voiceCurrentRoom) leaveVoiceRoom(voiceCurrentRoom);
    try {
        voiceLocalStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
        flashToast('Нет доступа к микрофону');
        return;
    }
    voiceCurrentRoom = roomId;
    voicePeers = {};
    voiceMuted = false;
    _bindVoiceEvents();
    voiceSocket.emit('voice_join', { room_id: roomId, name: document.body.dataset.userName });
    // Обновляем UI без перезагрузки: отмечаем комнату активной, показываем панель управления
    _refreshVoiceRoomUI(roomId, true);
}

function leaveVoiceRoom(roomId) {
    if (voiceSocket && roomId) {
        voiceSocket.emit('voice_leave', { room_id: roomId });
    }
    Object.keys(voicePeers).forEach(uid => _closeVoicePeer(uid));
    voicePeers = {};
    if (voiceLocalStream) {
        voiceLocalStream.getTracks().forEach(t => t.stop());
        voiceLocalStream = null;
    }
    voiceCurrentRoom = null;
    _refreshVoiceRoomUI(roomId, false);
}

function toggleVoiceMute(roomId) {
    voiceMuted = !voiceMuted;
    if (voiceLocalStream) {
        voiceLocalStream.getAudioTracks().forEach(t => t.enabled = !voiceMuted);
    }
    if (voiceSocket) voiceSocket.emit('voice_mute', { room_id: roomId, muted: voiceMuted });
    // Обновляем ВСЕ кнопки mute (в комнате + плавающая панель)
    document.querySelectorAll('#vc-mute-btn, .vf-mute-btn').forEach(btn => {
        btn.classList.toggle('muted', voiceMuted);
        btn.querySelector('use').setAttribute('href', voiceMuted ? '#i-mic-off' : '#i-mic');
    });
}

// Перерисовка UI голосовой комнаты при входе/выходе (без перезагрузки страницы)
function _refreshVoiceRoomUI(roomId, joined) {
    const room = document.querySelector('.voice-room[data-room-id="' + roomId + '"]');
    if (room) {
        room.classList.toggle('active', joined);
        const body = room.querySelector('.voice-room-body');
        if (body) {
            if (joined) {
                // Заменяем кнопку «Войти» на панель управления
                const joinBtn = body.querySelector('.vc-join');
                if (joinBtn) {
                    const ctrl = document.createElement('div');
                    ctrl.className = 'voice-controls';
                    ctrl.innerHTML =
                        '<span class="vc-status">Подключено</span>' +
                        '<button class="vc-btn" id="vc-mute-btn" onclick="toggleVoiceMute(' + roomId + ')" title="Микрофон">' +
                        '<svg class="icon"><use href="#i-mic"/></svg></button>' +
                        '<button class="vc-btn vc-leave" onclick="leaveVoiceRoom(' + roomId + ')" title="Покинуть">' +
                        '<svg class="icon"><use href="#i-phone-off"/></svg></button>';
                    joinBtn.replaceWith(ctrl);
                }
            } else {
                // Возвращаем кнопку «Войти»
                const ctrl = body.querySelector('.voice-controls');
                if (ctrl) {
                    const btn = document.createElement('button');
                    btn.className = 'btn btn-sm btn-primary vc-join';
                    btn.setAttribute('onclick', 'joinVoiceRoom(' + roomId + ')');
                    btn.innerHTML = '<svg class="icon icon-sm"><use href="#i-phone"/></svg> Войти';
                    ctrl.replaceWith(btn);
                }
            }
        }
    }
    // Плавающая панель управления (как в Discord) — всегда видна во время разговора
    _refreshVoiceFloat(joined);
}

function _refreshVoiceFloat(joined) {
    let f = document.getElementById('voice-float');
    if (!joined) { if (f) f.remove(); return; }
    const room = document.querySelector('.voice-room.active .vr-name');
    const name = room ? room.textContent.trim() : 'Голосовая';
    if (!f) {
        f = document.createElement('div');
        f.id = 'voice-float';
        f.className = 'voice-float';
        document.body.appendChild(f);
    }
    f.innerHTML =
        '<div class="vf-info"><span class="vf-name">' + esc(name) + '</span>' +
        '<span class="vf-status">Голосовой чат</span></div>' +
        '<button class="vc-btn vf-mute-btn" onclick="toggleVoiceMute(' + voiceCurrentRoom + ')" title="Микрофон">' +
        '<svg class="icon"><use href="#i-mic"/></svg></button>' +
        '<button class="vc-btn vc-leave" onclick="leaveVoiceRoom(' + voiceCurrentRoom + ')" title="Покинуть">' +
        '<svg class="icon"><use href="#i-phone-off"/></svg></button>';
}

function _createVoicePeer(userId, isOfferer) {
    if (!voiceLocalStream || voicePeers[userId]) return;
    const pc = new RTCPeerConnection(ICE_SERVERS);
    voicePeers[userId] = pc;

    voiceLocalStream.getTracks().forEach(t => pc.addTrack(t, voiceLocalStream));

    pc.onicecandidate = (e) => {
        if (e.candidate && voiceSocket) {
            voiceSocket.emit('voice_signal', { to: userId, signal: { ice: e.candidate } });
        }
    };
    pc.ontrack = (e) => {
        // Аудио от собеседника — просто проигрываем (элемент не виден)
        let a = document.getElementById('voice-audio-' + userId);
        if (!a) {
            a = document.createElement('audio');
            a.id = 'voice-audio-' + userId;
            a.autoplay = true;
            document.body.appendChild(a);
        }
        a.srcObject = e.streams[0];
    };
    pc.onconnectionstatechange = () => {
        if (pc.connectionState === 'disconnected' || pc.connectionState === 'failed') {
            _closeVoicePeer(userId);
        }
    };

    if (isOfferer) {
        pc.createOffer({ offerToReceiveAudio: true })
            .then(o => pc.setLocalDescription(o))
            .then(() => {
                voiceSocket.emit('voice_signal', { to: userId, signal: { sdp: pc.localDescription } });
            });
    }
    _addVoiceParticipantEl(userId);
}

async function _handleVoiceSignal(from, signal) {
    let pc = voicePeers[from];
    if (!pc) {
        // Кто-то шлёт нам сигнал — создаём пир как отвечающую сторону
        _createVoicePeer(from, false);
        pc = voicePeers[from];
    }
    if (!pc) return;
    try {
        if (signal.sdp) {
            await pc.setRemoteDescription(new RTCSessionDescription(signal.sdp));
            if (signal.sdp.type === 'offer') {
                const answer = await pc.createAnswer();
                await pc.setLocalDescription(answer);
                voiceSocket.emit('voice_signal', { to: from, signal: { sdp: pc.localDescription } });
            }
        } else if (signal.ice) {
            try { await pc.addIceCandidate(new RTCIceCandidate(signal.ice)); } catch (e) {}
        }
    } catch (e) { console.error('voice signal error:', e); }
}

function _closeVoicePeer(userId) {
    const pc = voicePeers[userId];
    if (pc) { try { pc.close(); } catch (e) {} delete voicePeers[userId]; }
    const a = document.getElementById('voice-audio-' + userId);
    if (a) a.remove();
}

function _addVoiceParticipantEl(userId) {
    const list = document.getElementById('vr-participants-' + voiceCurrentRoom);
    if (!list) return;
    if (list.querySelector('[data-uid="' + userId + '"]')) return;
    const name = 'Пользователь ' + userId;
    const div = document.createElement('div');
    div.className = 'voice-participant';
    div.dataset.uid = userId;
    div.innerHTML = '<img src="/static/img/default_avatar.svg" alt=""><span>' + esc(name) + '</span>';
    list.appendChild(div);
}
function _removeVoiceParticipantEl(userId) {
    const el = document.querySelector('.voice-participant[data-uid="' + userId + '"]');
    if (el) el.remove();
}


// ===================================================================
//  SPA-НАВИГАЦИЯ (плавные переходы без перезагрузки страницы)
//  PJAX: перехватываем внутренние ссылки, грузим страницу через fetch,
//  меняем содержимое <main id="app-main"> с плавной анимацией.
//  Используем View Transitions API где поддерживается, fallback на CSS.
// ===================================================================
(function () {
    'use strict';

    const SPA_SELECTOR = 'a[href]:not([target="_blank"]):not([download])';
    let spaEnabled = 'PushManager' in window && history.pushState;
    let isNavigating = false;

    function _sameOrigin(url) {
        try { return new URL(url, location.href).origin === location.origin; }
        catch (e) { return false; }
    }

    // Внутренние ссылки, которые не должны идти через SPA:
    // якоря, внешние, загрузки, и страницы с особыми состояниями (логаут).
    function _shouldSpa(url) {
        if (!spaEnabled || !_sameOrigin(url)) return false;
        const u = new URL(url, location.href);
        // Разрешаем только GET-страницы приложения.
        if (u.hash && u.pathname === location.pathname) return false;
        if (/\/(logout|uploads\/)/.test(u.pathname)) return false;
        return true;
    }

    function _applyTransition(updateFn) {
        const wrap = () => {
            updateFn();
            // Прокрутка наверх после смены страницы
            window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
        };
        if (document.startViewTransition) {
            document.startViewTransition(wrap);
        } else {
            // Fallback: плавный fade через класс
            const main = document.getElementById('app-main');
            if (main) {
                main.classList.add('spa-leaving');
                setTimeout(() => { wrap(); main.classList.remove('spa-leaving'); main.classList.add('spa-entering'); }, 160);
                setTimeout(() => main.classList.remove('spa-entering'), 320);
            } else {
                wrap();
            }
        }
    }

    async function _navigate(url, push) {
        if (isNavigating) return;
        isNavigating = true;
        document.body.classList.add('spa-loading');
        try {
            const resp = await fetch(url, { headers: { 'X-SPA': '1' }, credentials: 'same-origin' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const ct = resp.headers.get('Content-Type') || '';
            if (!ct.includes('text/html')) { location.href = url; return; }
            const html = await resp.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const newMain = doc.getElementById('app-main');
            if (!newMain) { location.href = url; return; }

            _applyTransition(() => {
                const oldMain = document.getElementById('app-main');
                if (oldMain) oldMain.replaceWith(newMain);
                // Обновляем заголовок
                document.title = doc.title || document.title;
                // Меняем активные подсветки в навигации
                const ep = newMain.getAttribute('data-endpoint');
                _updateNavActive(ep);
                // Переносим flash-сообщения
                _syncFlashes(doc);
                // Пере-инъектируем CSRF в формы новой страницы
                if (window.injectCSRF) window.injectCSRF(newMain);
                // Выполняем инлайн-скрипты новой страницы:
                // 1) внутри <main> (встроенные в тело страницы)
                _runInlineScripts(newMain);
                // 2) вне <main> — это {% block scripts %} из base.html
                doc.querySelectorAll('body > script:not([src])').forEach(old => {
                    const s = document.createElement('script');
                    s.textContent = old.textContent;
                    document.body.appendChild(s);
                    // Выполняется один раз при вставке; убираем после.
                    setTimeout(() => s.remove(), 0);
                });
                // 3) data-init атрибут для страниц вроде чата
                if (ep === 'chat') _initChatAfterSpa(newMain);
            });

            if (push !== false) history.pushState({ spa: true, url }, '', url);
        } catch (e) {
            console.warn('SPA nav failed, fallback:', e);
            location.href = url;
        } finally {
            isNavigating = false;
            document.body.classList.remove('spa-loading');
        }
    }

    function _updateNavActive(endpoint) {
        document.querySelectorAll('.topbar-item, .bottombar-item').forEach(btn => {
            btn.classList.remove('active');
        });
        if (!endpoint) return;
        const map = {
            feed: '.bottombar-item[title="Лента"]',
            chat: '.bottombar-item[title="Сообщения"]',
            people: '.topbar-item[title="Поиск людей"]',
            groups: '.topbar-item[title="Группы"]',
            bookmarks: '.topbar-item[title="Закладки"]',
            notifications: '.topbar-item[title="Уведомления"]',
            admin: '.topbar-item[title="Админ-панель"]',
            profile: '.bottombar-item[title="Профиль"]',
            settings: '.bottombar-item[title="Профиль"]',
        };
        const sel = map[endpoint];
        if (sel) { const el = document.querySelector(sel); if (el) el.classList.add('active'); }
    }

    function _syncFlashes(doc) {
        const cont = document.getElementById('flash-container');
        if (!cont) return;
        cont.innerHTML = '';
        const newFlashes = doc.querySelectorAll('#flash-container > .flash');
        newFlashes.forEach(f => cont.appendChild(f.cloneNode(true)));
        // авто-скрытие через 4с
        setTimeout(() => {
            cont.querySelectorAll('.flash').forEach(f => { f.style.opacity = '0'; setTimeout(() => f.remove(), 300); });
        }, 4000);
    }

    function _runInlineScripts(root) {
        // Инлайн-скрипты НЕ выполняются при вставке через innerHTML/replaceWith,
        // поэтому перепривязываем их вручную.
        root.querySelectorAll('script').forEach(old => {
            const s = document.createElement('script');
            if (old.src) { s.src = old.src; } else { s.textContent = old.textContent; }
            old.replaceWith(s);
        });
    }

    // Перехват кликов по ссылкам <a>
    document.addEventListener('click', (e) => {
        const a = e.target.closest(SPA_SELECTOR);
        if (!a) return;
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        const href = a.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
        if (!_shouldSpa(a.href)) return;
        e.preventDefault();
        _navigate(a.href, true);
    }, true);

    // Перехват location.href через monkey-patch (кнопки используют onclick)
    // Нельзя переопределить location.href как сеттер в большинстве браузеров,
    // поэтому задаём обработчик на capture-фазе для кликов по [onclick*=location.href]
    document.addEventListener('click', (e) => {
        const el = e.target.closest('[onclick*="location.href"]');
        if (!el) return;
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        const m = (el.getAttribute('onclick') || '').match(/location\.href\s*=\s*['"]([^'"]+)['"]/);
        if (!m) return;
        const url = m[1];
        if (!_shouldSpa(url)) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        _navigate(new URL(url, location.href).href, true);
    }, true);

    // Кнопки «назад/вперёд»
    window.addEventListener('popstate', (e) => {
        const url = (e.state && e.state.url) || location.href;
        _navigate(url, false);
    });

    // Предзагрузка при наведении на ссылку (быстрее переход)
    let preloadAbort = null;
    document.addEventListener('mouseover', (e) => {
        const a = e.target.closest(SPA_SELECTOR);
        if (!a || !_shouldSpa(a.href)) return;
        if (a.dataset.preloaded) return;
        a.dataset.preloaded = '1';
        // Просто прогреваем соединение (dns/prefetch), без полной загрузки
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = a.href;
        document.head.appendChild(link);
    }, { passive: true });

    // Помечаем начальное состояние
    history.replaceState({ spa: true, url: location.href }, '', location.href);

    // Экспортируем _navigate для использования вне IIFE (напр., createVoiceRoom)
    globalThis.__spaNavigate = function (url, push) { _navigate(url, push); };

    // ===== Инциализация чата после SPA-перехода =====
    // Пересоздаём состояние сокета/звонков при заходе на страницу чата.
    window._initChatAfterSpa = function (root) {
        // Сбрасываем старый сокет чата, чтобы не было дублей слушателей
        try { if (window.chatSocket) { window.chatSocket.disconnect(); window.chatSocket = null; } } catch (e) {}
        const uid = document.body.getAttribute('data-user-id');
        if (!uid) return;
        // partnerId берём из data-атрибута, который chat.html выставляет на .chat-page
        const chatPage = root.querySelector('#chat-page');
        const partnerId = chatPage ? chatPage.getAttribute('data-partner-id') : null;
        if (window.initSocket && partnerId) {
            // Небольшая задержка — даём сокету подключиться
            setTimeout(() => {
                try { window.initSocket(Number(uid), Number(partnerId)); } catch (e) { console.warn(e); }
                if (window._registerCallListeners) window._registerCallListeners();
            }, 80);
        }
        // Скролл вниз + скрытие баров на мобиле
        const c = document.getElementById('chat-messages');
        if (c) c.scrollTop = c.scrollHeight;
        if (window.innerWidth <= 768 && chatPage && chatPage.classList.contains('show-window')) {
            document.body.classList.add('chat-active');
        }
    };
})();

