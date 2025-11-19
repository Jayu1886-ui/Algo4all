# ================================================================
# File: app/tasks/task_1_fetch_hist.py (FINAL, ROBUST VERSION)
# ================================================================

import os
import json
import pandas as pd
from datetime import datetime
import pytz
import upstox_client
from upstox_client.rest import ApiException # <-- Import the specific error class
from app.extensions import celery_app, cache
from .utils import get_previous_working_day 

# --- CONFIG ---
HIST_CACHE_TIMEOUT = 86400        # 24 hours
NUM_HISTORICAL_DAYS = 4           # Fetch last 3 trading days
ACCESS_TOKEN_FILE = os.getenv("STREAMER_ACCESS_TOKEN_FILE", "/mnt/c/Users/Jayendra/Desktop/ALGO4ALL/access_token.txt")

# --- HELPER: Read access token from file (Kept simple, as the issue is not here) ---
def get_access_token_from_file():
    try:
        if os.path.exists(ACCESS_TOKEN_FILE):
            with open(ACCESS_TOKEN_FILE, "r") as f:
                token = f.read().strip()
                if token:
                    return token
        print(f"[TASK 1] ⚠️ access_token.txt missing or empty at: {ACCESS_TOKEN_FILE}")
        return None
    except Exception as e:
        print(f"[TASK 1] ⚠️ Failed to read access_token.txt: {e}")
        return None

# --- HELPER: Initialize Upstox API ---
def get_historical_api_instance(access_token):
    # ... (body remains the same)
    if not access_token:
        return None
    configuration = upstox_client.Configuration()
    configuration.access_token = access_token
    return upstox_client.HistoryV3Api(upstox_client.ApiClient(configuration))


# --- MAIN TASK ---
@celery_app.task(bind=True)
def fetch_hist_data(self, instrument_key="NSE_INDEX|Nifty 50", interval="1m"):
    """
    Fetches last 2 trading days of historical candle data for given instrument.
    """
    access_token = get_access_token_from_file()
    if not access_token:
        print("[TASK 1] ❌ Missing access token. Aborting historical fetch.")
        return None

    api_instance = get_historical_api_instance(access_token)
    if not api_instance:
        print("[TASK 1] ❌ Failed to initialize Upstox API instance.")
        return None

    print(f"\n--- [TASK 1] Starting Historical Fetch for {instrument_key} ---")

    # --- Date Range Setup ---
    ist = pytz.timezone("Asia/Kolkata")
    today_date = datetime.now(ist).date()
    last_working_day = get_previous_working_day(today_date)
    day_iterator = last_working_day
    for _ in range(NUM_HISTORICAL_DAYS - 1):
        day_iterator = get_previous_working_day(day_iterator)
    start_date_str = day_iterator.strftime("%Y-%m-%d")
    end_date_str = last_working_day.strftime("%Y-%m-%d")

    # --- Cache Key ---
    hist_cache_key = f"historical_data:{instrument_key}" 

    # Skip fetch if cache exists (GOOD FOR SCHEDULED RUN)
    if cache.get(hist_cache_key):
        print(f"[TASK 1] ✅ Cached data exists for {instrument_key}. Skipping API fetch.")
        return None

    # --- API Fetch (VERBOSE DEBUGGING) ---
    candles = []
    try:
        response = api_instance.get_historical_candle_data1(
            instrument_key,
            "minutes",
            "1",
            end_date_str,
            start_date_str
        )
        candles = (
            response.data.candles
            if (response and response.data and response.data.candles)
            else []
        )
        
        if not candles:
             print(f"[TASK 1] ⚠️ Upstox API returned 0 candles for {start_date_str} to {end_date_str}. Check market status.")
             
    except ApiException as e:
        # CRITICAL DEBUG: Print the API-specific error body (401, 403, etc.)
        print(f"[TASK 1] ❌ CRITICAL API Error (Status {e.status}): {e.body}")
        
    except Exception as e:
        # Generic error handling
        print(f"[TASK 1] ❌ Unexpected Error during API call: {e}")

    # --- Process and Cache ---
    if candles:
        df = pd.DataFrame(
            candles,
            columns=["timestamp", "open", "high", "low", "close", "volume", "oi"],
        )
        # Save the full DataFrame as a JSON string to cache
        cache.set(hist_cache_key, df.to_json(orient="records"), timeout=HIST_CACHE_TIMEOUT)
        print(f"[TASK 1] ✅ Cached {len(df)} 1-min candles for {instrument_key}.")
    else:
        print(f"[TASK 1] ❌ No historical data returned for {instrument_key}. Data fetch failed.")

    print("[TASK 1] Historical Fetch Complete.\n")
    return None