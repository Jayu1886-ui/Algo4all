import os
from dotenv import load_dotenv
from celery.schedules import crontab
from datetime import timedelta 

# --- NEW: Load the .env file at the top of your config ---
# This ensures that all os.environ.get() calls below this line
# will have access to the variables defined in your .env file.
load_dotenv()

class Config:
    """
    Base configuration class. Loads settings from environment variables.
    """
    # --- Flask and Extension Config ---
    # This correctly loads the secret key from your .env file.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'super-secret')
    OWNER_API_KEY = os.environ.get('OWNER_API_KEY')
    # NOTE: We only need the key here for comparison, but you can expose the secret too.
    OWNER_API_SECRET = os.environ.get('OWNER_API_SECRET')
    
    # This correctly loads the database URL from your .env file.
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 30,         
        "max_overflow": 45,      
        "pool_timeout": 30,      
        "pool_recycle": 3600,    
        "pool_pre_ping": True,
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # --- Redis Cache Configuration ---
    CACHE_TYPE = "RedisCache"
    CACHE_DEFAULT_TIMEOUT = 300
    CACHE_REDIS_URL = os.environ.get('REDIS_URL')

    # --- SocketIO Message Queue ---
    SOCKETIO_MESSAGE_QUEUE = os.environ.get('REDIS_URL')

    # --- REMOVED Upstox App Credentials ---
    # In the "Bring Your Own Key" model, the application does not have its own
    # master Client ID. Each user provides their own, which are stored in the database.
    # The only global Upstox setting we need is the Redirect URI.
    # UPSTOX_APP_CLIENT_ID="YOUR_REAL_UPSTOX_CLIENT_ID" # <-- REMOVED
    
    # --- MODIFIED: Load the Redirect URI from the .env file ---
    # This makes your .env file the single source of truth for all configurations.
    UPSTOX_REDIRECT_URI = os.environ.get ('UPSTOX_REDIRECT_URI')

    # --- Celery Configuration ---
    # This correctly loads the Redis URL from your .env file.
    CELERY_BROKER_URL = os.environ.get('REDIS_URL')
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL')
    
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TIMEZONE = "Asia/Kolkata"
    CELERY_TASK_TRACK_STARTED = True
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
    
    # --- Celery Beat Schedule ---
    CELERY_BEAT_SCHEDULE = { 
    "fetch-daily-hist": {
        "task": "app.tasks.task_1_fetch_hist.fetch_hist_data",
        "schedule": 60.0,
        "args":("NSE_INDEX|Nifty 50", "1m")
    },
    "merge-every-30sec": {
        "task": "app.tasks.task_merge.merge_hist_live",
        "schedule": 30.0,
        "args": ("NSE_INDEX|Nifty 50", "1m")
    },    
    "sma-every-32sec": {
        "task": "app.tasks.task_sma.calculate_sma_for_closed_bar",
        "schedule": 32.0,
        "args": ("NSE_INDEX|Nifty 50", "1m")
    },
    "trend-every-35sec": {
        "task": "app.tasks.task_trend.analyze_trend",
        "schedule": 35.0,
        "args": ("NSE_INDEX|Nifty 50", "1m")
    },
    "option-chain-every-300sec": {
        "task": "app.tasks.task_option_chain.fetch_option_data",
        "schedule": 300.0,
        "args": ("NSE_INDEX|Nifty 50",)
    },
    "order-manager-every-20sec": {
        "task": "app.tasks.task_order_manager.manage_orders",
        "schedule": 20.0,
        "args": [1],
    },
    "run-end-of-day-cleanup": {
        "task": "app.tasks.cleanup_task.end_of_day_cleanup",
        "schedule": crontab(hour=15, minute=30, day_of_week='mon-fri'),
        "args": ("NSE_INDEX|Nifty 50", 10, 25),
    }
}       

