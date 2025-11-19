# In file: app/tasks/utils.py (FINAL, CLEANED, AND CORRECTED VERSION)

import os
import requests
import certifi
import redis, json 
import pandas as pd 
from datetime import date, datetime, timedelta, time
from dotenv import load_dotenv
from cryptography.fernet import Fernet
# --- Import the core extensions for shared tasks ---
from app.extensions import celery_app, cache # Note: No need for redis import here
# --------------------------------------------------

redis_client = redis.Redis(host="127.0.0.1", port=6379, db=0)
# --- Configuration & Key Prefixes ---
load_dotenv()
# Note: REDIS_URL and redis_client are removed as we use the Flask-Cache 'cache' instance.

# --- CRITICAL FIX: Use the exact key prefix from the working streamer ---
LTP_KEY_PREFIX = "LTP:" 
# -----------------------------------------------------------------------

OWNER_USER_ID = os.environ.get('OWNER_USER_ID', 'GLOBAL_TRADER') # Read Owner ID from .env


# --- ======================================================= ---
# --- CORE CRYPTO/HELPER FUNCTIONS                            ---
# --- ======================================================= ---

# --- REMOVED: process_initial_setup (Deprecated) ---

def decrypt_token(encrypted_token):
    """Decryption function (CRITICAL for user/owner tokens)."""
    if not encrypted_token:
        raise ValueError("Encrypted token is missing or empty.")
    
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise ValueError("Missing ENCRYPTION_KEY in environment variables.")
    
    try:
        f = Fernet(key.encode())
        # Ensure input is bytes for Fernet
        if isinstance(encrypted_token, str):
            encrypted_token = encrypted_token.encode()
            
        decrypted = f.decrypt(encrypted_token) 
        return decrypted.decode() 
    except Exception as e:
        raise ValueError(f"Token decryption failed: {e}")

def get_upstox_headers(access_token: str):
    """Prepares Upstox headers for API calls."""
    if not access_token:
        raise ValueError("Cannot create headers: Access token is None/empty.")
        
    return{'Accept': 'application/json', 'Api-Version': '2.0', 'Authorization': f'Bearer {access_token}'}

# --- OWNER CREDENTIAL HELPERS (GLOBAL DATA) ---
def get_owner_credentials():
    """
    Retrieves Owner Credentials (API Key/Secret/Token) for global data services.
    CRITICAL: Fetches the Access Token from AppSettings (securely stored).
    """
    from app import db, create_app 
    from app.models import AppSettings 

    # 1. Get static credentials (Key/Secret) from .env
    owner_api_key = os.environ.get('OWNER_API_KEY')
    owner_api_secret = os.environ.get('OWNER_API_SECRET')
    
    if not all([owner_api_key, owner_api_secret]):
        # Removed raise to allow the flow to warn and continue gracefully
        print("WARNING: Owner API Key/Secret missing from .env.")
        return None

    # 2. Get dynamic Access Token from DB (Requires App Context)
    app, _ = create_app()
    with app.app_context():
        # Retrieve the row containing the encrypted owner token
        token_setting = db.session.execute(
            db.select(AppSettings).filter_by(setting_name='owner_access_token')
        ).scalar_one_or_none()

        if token_setting and token_setting.secret_value:
            # secret_value property is assumed to return the DECRYPTED token string
            decrypted_token = token_setting.secret_value
            
            return {
                'api_key': owner_api_key,
                'api_secret': owner_api_secret,
                'access_token': decrypted_token, 
                'user_id': OWNER_USER_ID
            }
        else:
            print("WARNING: Owner Access Token not found in DB. Manual/Re-authentication is required.")
            return None
# --- USER SESSION HELPERS ---

def get_daily_session_for_user(user):
    """Checks token validity for a specific user using their decrypted token."""
    from app import db # Local import
    
    # CRITICAL FIX: The User model property handles decryption on read.
    current_decrypted_token = user.access_token 
    
    if not current_decrypted_token:
        return None
        
    # 2. Use the DECRYPTED token for API check
    headers = get_upstox_headers(current_decrypted_token)
    profile_url = "https://api.upstox.com/v2/user/profile"
    try:
        response = requests.get(profile_url, headers=headers, timeout=10, verify=certifi.where())
        if response.status_code == 200:
            print(f"  -> Access token for user {user.id} is still valid.")
            return current_decrypted_token
    except requests.exceptions.RequestException:
        pass 

    return None 

def is_upstox_session_valid(user):
    valid_token = get_daily_session_for_user(user)
    return valid_token is not None

# --- GENERAL UTILITIES ---

def get_live_ltp(symbol: str):
    """Fetch latest LTP data for a given symbol from Redis (shared with streamer)."""
    cache_key = f"LTP:{symbol}"
    data = redis_client.get(cache_key)
    if not data:
        return None

    if isinstance(data, bytes):
        data = data.decode('utf-8')

    try:
        live_data = json.loads(data)
        if "ltp" in live_data:
            return live_data
    except Exception as e:
        print(f"Error parsing LTP for {symbol}: {e} Data: {data}")

    return None

def get_cached_historical_data(instrument_key: str):
    """
    Retrieves cached historical data. (Used by T7: calculate_sma_for_closed_bar)
    """
    try:
        # --- CRITICAL FIX: Use Flask-Cache (cache) and the correct key ---
        cache_key = f"historical_data:{instrument_key}" # Key from task_1_fetch_hist
        cached_data = cache.get(cache_key) 
        
        if cached_data:
            # Data is a JSON string saved by task_1_fetch_hist
            data = json.loads(cached_data)
            return data
        return None
    except Exception as e:
        print(f"[CACHE ERROR] get_cached_historical_data failed: {e}")
        return None

def get_next_tuesday():
    """Gets the upcoming Tuesday expiry date (Tuesday is weekday 1)."""
    today = datetime.now()
    # Calculate days to next Tuesday (1)
    days_ahead = (1 - today.weekday() + 7) % 7 
    # If today is Tuesday, days_ahead is 0. If you want the NEXT Tuesday, add a check.
    if days_ahead == 0:
        days_ahead = 7
        
    return today.date() + timedelta(days=days_ahead)

def get_previous_working_day(date_today):
    """Gets the previous working day, skipping weekends."""
    prev_day = date_today - timedelta(days=1)
    # 5=Saturday, 6=Sunday
    while prev_day.weekday() >= 5: 
        prev_day -= timedelta(days=1)
    return prev_day

# --- REMOVED: merge_live_ltp_with_historical (Logic moved to task_merge.py) ---