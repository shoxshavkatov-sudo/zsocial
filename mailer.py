"""Email-уведомления для ZSocial (SMTP через stdlib).

Если MAIL_ENABLED != '1' или нет SMTP-настроек — работает в режиме no-op
(пишет в лог, не отправляет). Отправка идёт в фоновом потоке, чтобы не
блокировать HTTP-запрос.
"""
import os
import smtplib
import ssl
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def _cfg():
    return {
        'enabled': os.environ.get('MAIL_ENABLED', '0') == '1',
        'host': os.environ.get('SMTP_HOST', ''),
        'port': int(os.environ.get('SMTP_PORT', '587')),
        'user': os.environ.get('SMTP_USER', ''),
        'pass': os.environ.get('SMTP_PASS', ''),
        'from': os.environ.get('SMTP_FROM', '') or os.environ.get('SMTP_USER', ''),
        'site': os.environ.get('SITE_NAME', 'ZSocial'),
    }


def _send(to_addr, subject, body):
    """Низкоуровневая отправка. Возвращает True при успехе."""
    c = _cfg()
    if not c['enabled'] or not c['host'] or not c['user'] or not c['pass']:
        # no-op режим: просто логируем
        print(f"[mailer] (no-op) → {to_addr}: {subject}")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{c['site']} <{c['from']}>"
        msg['To'] = to_addr
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        context = ssl.create_default_context()
        with smtplib.SMTP(c['host'], c['port']) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(c['user'], c['pass'])
            server.sendmail(c['from'], to_addr, msg.as_string())
        return True
    except Exception as e:
        print(f"[mailer] Ошибка отправки на {to_addr}: {e}")
        return False


def send_async(to_addr, subject, body):
    """Отправляет письмо в фоновом потоке (не блокирует запрос)."""
    t = threading.Thread(target=_send, args=(to_addr, subject, body), daemon=True)
    t.start()


# ===== Шаблоны писем =====
def notify_like(to_addr, actor_name, post_preview):
    send_async(to_addr, f'👍 {actor_name} оценил(а) вашу публикацию',
               f'{actor_name} поставил(а) лайк вашему посту:\n\n"{post_preview}"\n\n— ZSocial')


def notify_comment(to_addr, actor_name, post_preview):
    send_async(to_addr, f'💬 {actor_name} прокомментировал(а) вашу публикацию',
               f'{actor_name} оставил(а) комментарий под вашим постом:\n\n"{post_preview}"\n\n— ZSocial')


def notify_follow(to_addr, actor_name):
    send_async(to_addr, f'👥 {actor_name} подписался(ась) на вас',
               f'У вас новый подписчик: {actor_name}.\n\n— ZSocial')
