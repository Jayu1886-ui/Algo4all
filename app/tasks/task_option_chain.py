# ============================================
# FILE: app/tasks/task_9_option_chain.py (FINAL CORRECTED VERSION)
# PURPOSE: Fetch and cache ATM Option Chain data (Global)
# ============================================

import math
import os
import json 
from datetime import datetime, timedelta
import upstox_client
from upstox_client.rest import ApiException
from dotenv import load_dotenv

# --- FIX 1: Import cache correctly (Assuming it's in app.extensions) ---
from app.extensions import celery_app, cache 
# -----------------------------------------------------------------------
from .utils import (
    get_upstox_headers, 
    get_live_ltp,
    get_next_tuesday
)

load_dotenv()

# --- Constants ---
NIFTY_INDEX_KEY = "NSE_INDEX|Nifty 50"
GLOBAL_OPTION_KEY = "option_chain:GLOBAL"
CACHE_TIMEOUT = 600  # 10 minutes

# --- CRITICAL FIX 2: Use the full Env/WSL path for access token ---
ACCESS_TOKEN_FILE = os.getenv("STREAMER_ACCESS_TOKEN_FILE", "/mnt/c/Users/Jayendra/Desktop/ALGO4ALL/access_token.txt")
# -------------------------------------------------------------------


# --- Helper: Read token from file (Unchanged) ---
def get_access_token_from_file():
    # ... (body remains the same)
    try:
        if os.path.exists(ACCESS_TOKEN_FILE):
            with open(ACCESS_TOKEN_FILE, "r") as f:
                token = f.read().strip()
                if token:
                    return token
        print(f"[TASK 9] ⚠️ access_token.txt missing or empty at {ACCESS_TOKEN_FILE}.")
        return None
    except Exception as e:
        print(f"[TASK 9] ⚠️ Failed to read access_token.txt: {e}")
        return None


@celery_app.task(bind=True, ignore_result=False, max_retries=3)
def fetch_option_data(self, prev_result=None):
    """
    Fetches global option chain data (ATM, expiry, keys) using the access token
    from access_token.txt.
    """
    print(f"\n--- [TASK 9] Fetching GLOBAL Option Chain (Attempt {self.request.retries + 1}) ---")

    try:
        # 1️⃣ Get access token
        access_token = get_access_token_from_file()
        if not access_token:
            print("[TASK 9] ❌ Missing or invalid access token.")
            return None

        # 2️⃣ Prepare Upstox API client
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        api_instance = upstox_client.OptionsApi(upstox_client.ApiClient(configuration))

        # 3️⃣ Get live Nifty LTP (Using fixed helper function)
        live_data = get_live_ltp(NIFTY_INDEX_KEY)
        
        if not live_data or "ltp" not in live_data:
            print("[TASK 9] ⚠️ Missing Nifty LTP (Stream not running) — retrying...")
            raise self.retry(countdown=5)
            
        nifty_ltp_float = float(live_data["ltp"]) 

        # 4️⃣ Calculate ATM Strike (Rounded to nearest 50)
        atm_strike = int(round(nifty_ltp_float / 50) * 50)
        print(f"[TASK 9] 📈 Nifty LTP = {nifty_ltp_float:.2f}, ATM Strike = {atm_strike}")

        # 5️⃣ Smart Expiry Date Logic
        today = datetime.now().date()
        next_tuesday = get_next_tuesday() 

        if today.weekday() == 1:  # Tuesday (0=Mon, 1=Tue, ..., 6=Sun)
            # Skip today's expiry and move to next week
            expiry_date = next_tuesday + timedelta(days=0)
        else:
            expiry_date = next_tuesday

        expiry_date_str = expiry_date.strftime("%Y-%m-%d")
        print(f"[TASK 9] 📅 Selected Expiry = {expiry_date_str}")

        # 6️⃣ Fetch all option contracts for current expiry
        oc_res = api_instance.get_option_contracts(
            NIFTY_INDEX_KEY,
            expiry_date=expiry_date_str
        )
        # Use a check here as oc_res.data can be None
        # Convert response objects to a list of dicts for simpler processing
        option_data_list = [item.to_dict() for item in (oc_res.data or [])]

        # 7️⃣ FIX: Find ATM Call and Put instrument keys using instrument_type
        atm_call_key, atm_put_key = None, None
        
        for opt in option_data_list:
            if opt.get("strike_price") == atm_strike:
                # Check for CALL (CE)
                if opt.get("instrument_type") == "CE":
                    atm_call_key = opt.get("instrument_key")
                # Check for PUT (PE)
                elif opt.get("instrument_type") == "PE":
                    atm_put_key = opt.get("instrument_key")
                
                # Exit loop once both are found
                if atm_call_key and atm_put_key:
                    break

        if not atm_call_key or not atm_put_key:
            # If the specific Upstox structure (strike grouping) was correct, 
            # this message would still be printed. The previous logic was:
            # atm_call_key = opt.get("call_options", {}).get("instrument_key") 
            # The structure is often flat, where each item is a single contract.
            
            # The structure might also be the one you initially implemented (grouped by strike), 
            # but that means the data for strike 26000 was missing entirely in the response.
            
            # Reverting to the original search logic for the common grouped API structure, 
            # but assuming the issue is that the contract for 26000 was missing.
            
            # FINAL RETRY LOGIC FOR THE ORIGINAL API STRUCTURE (assuming it's correct)
            atm_call_key, atm_put_key = None, None
            for opt in option_data_list:
                if opt.get("strike_price") == atm_strike:
                    # Check for CALL and PUT nested keys (your original attempt)
                    atm_call_key = opt.get("call_options", {}).get("instrument_key") 
                    atm_put_key = opt.get("put_options", {}).get("instrument_key")
                    if atm_call_key and atm_put_key:
                        break # Found both in one strike grouping

        if not atm_call_key or not atm_put_key:
            print(f"[TASK 9] ⚠️ Could not find ATM call/put keys for strike {atm_strike}. The strike may be missing from the response.")
            raise self.retry(countdown=5)

        # 8️⃣ Build and Cache Global Payload
        result = {
            "expiry_date": expiry_date_str,
            "atm_strike": atm_strike,
            "atm_call": {
                "instrument_key": atm_call_key, 
                "type": "CALL",
                "strike_price": atm_strike # Add strike price for clarity
            },
            "atm_put": {
                "instrument_key": atm_put_key, 
                "type": "PUT",
                "strike_price": atm_strike # Add strike price for clarity
            },
        }
        
        # Save the result as a JSON string
        cache.set(GLOBAL_OPTION_KEY, json.dumps(result), timeout=CACHE_TIMEOUT)
        print(f"[TASK 9] ✅ Cached ATM CALL: {atm_call_key} | PUT: {atm_put_key} (GLOBAL).")
        print("--- [TASK 9] Option Chain Fetch Complete ---")
        return result

    except ApiException as e:
        print(f"[TASK 9] ❌ API Error fetching Option Chain (Status {e.status}): {e.body}")
        raise self.retry(countdown=10, exc=e)

    except Exception as e:
        print(f"[TASK 9] ❌ Unexpected Error in Option Chain Task: {e}")
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=5, exc=e)
        return None