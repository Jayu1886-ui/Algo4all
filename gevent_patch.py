# gevent_patch.py

from gevent import monkey
monkey.patch_all()
print("--- Gevent monkey patch applied ---")