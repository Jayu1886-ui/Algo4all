# gunicorn.conf.py (FINAL CORRECTED GUNICORN VERSION)



# Server socket
bind = "0.0.0.0:10000"

# Worker processes
workers = 1

# Use the gevent worker class for high performance.
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"

# Timeout
timeout = 120

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Do NOT preload the app when using gevent.
preload_app = False