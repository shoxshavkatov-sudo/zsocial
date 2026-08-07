"""WSGI entry point для production (gunicorn на Render).

Запуск: gunicorn --worker-class gevent --workers 1 --bind 0.0.0.0:$PORT wsgi:application
"""
from app import app, socketio

# application для gunicorn
application = socketio  # SocketIO Middleware оборачивает Flask app

if __name__ == '__main__':
    import os
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5050)))
