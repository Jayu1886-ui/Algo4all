# In file: app/__init__.py (FINAL CLEAN & FIXED VERSION)

from flask import Flask 
from config import Config
from celery.schedules import crontab 
from datetime import timedelta 
from app.extensions import db, login_manager, cache, migrate, socketio, celery_app

def create_app(config_class=Config):
    """ Application Factory: Creates and configures both the Flask app and the Celery app. """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # --- 1. Initialize Flask extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    cache.init_app(app)
    socketio.init_app(app, message_queue=app.config.get('SOCKETIO_MESSAGE_QUEUE'))

    # --- 2. Configure the Celery App ---
    # This correctly loads CELERY_ prefixed settings from the config object.
    celery_app.config_from_object(app.config, namespace='CELERY')
    # REMOVED: celery_app.conf.update(app.config) - this line was redundant.

    # --- 2a. Define Celery Context Task wrapper ---
    class ContextTask(celery_app.Task):
        """Ensures each Celery task runs within Flask app context."""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    celery_app.Task = ContextTask
    app.extensions["celery"] = celery_app

    # --- 3. Register Blueprints ---
    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    from .main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    from .admin import admin as admin_blueprint
    app.register_blueprint(admin_blueprint, url_prefix='/admin')
    from .api import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')

    # --- 4. Configure Flask-Login ---
    login_manager.login_view = 'auth.login'
    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
        
    return app, socketio