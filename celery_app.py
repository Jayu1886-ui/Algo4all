# In file: celery_app.py (FINAL, CLEANED VERSION)

from dotenv import load_dotenv

# Ensure the .env file is loaded early for Celery CLI
load_dotenv() 

# Import the application factory from your app package
from app import create_app

# Call the application factory to get the fully configured Flask app
# We don't need socketio for Celery configuration.
flask_app, _ = create_app() 

# --- IMPORTANT ---
# We need a top-level variable named 'celery' for the Celery CLI to find.
# We get the fully configured Celery instance from the Flask app's extensions.
# This assumes create_app() correctly sets: app.extensions["celery"] = celery_app
celery = flask_app.extensions["celery"]

# 👇 NEW — explicitly import all task modules so the worker knows them
from app.tasks import (
    task_1_fetch_hist,
    task_merge,
    task_sma,
    task_trend,
    task_option_chain,
    task_order_manager,
    cleanup_task,
)