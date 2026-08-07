"""WSGI entry point для production (gunicorn на Render).

Flask-SocketIO + gevent: gunicorn запускает этот файл,
engineio.middleware.WSGIApp оборачивает Flask app + SocketIO server.

Запуск: gunicorn --worker-class gevent --workers 1 --bind 0.0.0.0:$PORT wsgi:application
"""
from app import app, socketio
from engineio.middleware import WSGIApp as EngineIOMiddleware

# gunicorn ожидает WSGI callable.
# Оборачиваем Flask app в engineio middleware, чтобы WebSocket запросы
# уходили в SocketIO, а обычные HTTP — во Flask.
application = EngineIOMiddleware(socketio, app)

if __name__ == '__main__':
    import os
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5050)))
