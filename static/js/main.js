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
                '<div class="comment"><img src="' + (c.avatar_url || '/static/' + c.avatar) + '" onclick="location.href=\'/profile/' + c.username + '\'"><div class="comment-content"><div class="comment-bubble"><div class="c-author">' + esc(c.username) + (c.verified ? ' <svg class="icon icon-sm verified-mark"><use href="#i-check-badge"/></svg>' : '') + '</div><div class="c-text">' + esc(c.content) + '</div></div></div></div><div class="comment-time">' + c.time + '</div>'
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
                '<div class="comment"><img src="' + (c.avatar_url || '/static/' + c.avatar) + '" onclick="location.href=\'/profile/' + c.username + '\'"><div class="comment-content"><div class="comment-bubble"><div class="c-author">' + esc(c.username) + '</div><div class="c-text">' + esc(c.content) + '</div></div></div></div><div class="comment-time">' + c.time + '</div>'
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
