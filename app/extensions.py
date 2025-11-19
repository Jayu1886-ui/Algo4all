# app/extensions.py
import os
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_caching import Cache
from flask_migrate import Migrate
from flask_socketio import SocketIO
from celery import Celery

# Flask extensions (unconfigured instances)
db = SQLAlchemy()
login_manager = LoginManager()
cache = Cache()
migrate = Migrate()

# SocketIO configured to use gevent async mode
socketio = SocketIO(async_mode="gevent", transports=["websocket", "polling"])
# extensions.py
socketio = SocketIO(cors_allowed_origins=["https://algo4all.in"], logger=True, engineio_logger=True)

# Single Celery instance configured from environment later in create_app()
# We create it with minimal args — configuration will be loaded in create_app()
celery_app = Celery(__name__)
