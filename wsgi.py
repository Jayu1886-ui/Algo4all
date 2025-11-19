# wsgi.py (FINAL CORRECTED VERSION)

# This file is the entrypoint for Gunicorn.
# All patching logic has been removed and is now handled by the --require flag in start.sh.

from app import create_app
import gevent.monkey
gevent.monkey.patch_all()  # Patches stdlib for gevent

flask_app, socketio = create_app()

# Required by Gunicorn
application = flask_app

if __name__ == "__main__":
    # Local dev server (HTTP or HTTPS)
    socketio.run(app, host='0.0.0.0', port=8088, server='gevent')


    
