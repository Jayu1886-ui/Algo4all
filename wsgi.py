from gevent import monkey
monkey.patch_all()

from app import create_app

flask_app, socketio = create_app()
application = flask_app
