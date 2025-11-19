# In file: app/tasks/task_order_manager.py (FINAL CORRECTED & COMPATIBLE)

import json
import datetime
import requests
import certifi
import upstox_client
from upstox_client.rest import ApiException
from requests.exceptions import RequestException
from dotenv import load_dotenv
import redis  # kept if needed elsewhere, not used for cache reads below

# --- Use app.extensions for cache, socketio, db ---
from app.extensions import celery_app, cache, socketio, db
from flask import current_app
# --------------------------------------------------

from app.models import User
from .utils import get_upstox_headers, get_live_ltp

load_dotenv()

# --- Constants & key patterns (must match producer tasks) ---
NIFTY_INDEX_KEY = "NSE_INDEX|Nifty 50"
NIFTY_50_NAME = "Nifty 50"

TREND_SIGNAL_KEY = f"trend_signal:{NIFTY_INDEX_KEY}"   # written by task_trend.py
GLOBAL_OPTION_KEY = "option_chain:GLOBAL"              # written by task_9_option_chain.py
# active trade key pattern: f"active_trade_{user.id}"

# Keep a raw redis client only if you need it for other uses (not used for reading cache keys here)
REDIS_CLIENT = redis.from_url("redis://localhost:6379/0")


# -----------------------
# Helper utilities
# -----------------------
def _normalize_cached_value(val):
    """Convert bytes to str, leave str alone, return None for falsy."""
    if val is None:
        return None
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            try:
                return val.decode("latin-1")
            except Exception:
                return None
    if isinstance(val, str):
        return val
    # If some libs return dict directly (unlikely), stringify
    try:
        return json.dumps(val)
    except Exception:
        return None


# --- 1️⃣ API HELPER FUNCTIONS ---
def place_market_order(instrument_token, quantity, transaction_type, headers):
    print(f"    -> Placing MARKET {transaction_type} order for {instrument_token}...")
    payload = {
        "quantity": int(quantity),
        "product": "I",
        "validity": "DAY",
        "price": 0,
        "instrument_token": instrument_token,
        "order_type": "MARKET",
        "transaction_type": transaction_type.upper(),
        "disclosed_quantity": 0,
        "trigger_price": 0,
        "is_amo": False
    }
    url = "https://api.upstox.com/v2/order/place"
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10, verify=certifi.where())
        response.raise_for_status()
        order_id = response.json().get("data", {}).get("order_id")
        print(f"    -> ✅ Order placed successfully. ID: {order_id}")
        return order_id
    except RequestException as e:
        if e.response is not None:
            try:
                print(f"    -> ⚠️ Order placement failed: {e.response.json()}")
            except Exception:
                pass
        print(f"    -> ⚠️ Order placement failed: {e}")
        return None


def get_order_fill_price(order_id, access_token):
    try:
        api_instance = upstox_client.OrderApi()

        # Correct Upstox V2 method
        response = api_instance.get_order_details(
            order_id=order_id,
            api_version="2.0",
            authorization=access_token
        )

        # Convert OrderData to dict
        if hasattr(response, "to_dict"):
            od = response.to_dict()
        else:
            od = json.loads(json.dumps(response, default=lambda o: o.__dict__))

        status = str(od.get("status", "")).lower()

        if status == "complete":
            return float(od.get("average_price") or 0)

        return None

    except Exception as e:
        print("Error fetching order fill price:", e)
        return None


# --- 2️⃣ CORE ORDER MANAGEMENT TASK ---
@celery_app.task(bind=True, ignore_result=True)
def manage_orders(self, user_id: int):
    """
    Core Order Management Task.
    Emits market_state to frontend and executes trades when signal+option meta exist.
    """
    try:
        user = db.session.get(User, user_id)
        if not user or not getattr(user, "is_trading_on", False) or not getattr(user, "access_token", None):
            print(f"--- [TASK order_mgmt: {user_id}] Skipped: User inactive or token missing. ---")
            return

        headers = get_upstox_headers(user.access_token)

        # --- Read cached items using the same cache the producer tasks use ---
        raw_signal = _normalize_cached_value(cache.get(TREND_SIGNAL_KEY))
        raw_option = _normalize_cached_value(cache.get(GLOBAL_OPTION_KEY))

        signal_frame = None
        option_meta = None

        # Try to load JSON if present
        if raw_signal:
            try:
                signal_frame = json.loads(raw_signal)
            except Exception:
                print(f"--- [TASK order_mgmt: {user_id}] Invalid JSON in trend cache value. raw_signal={raw_signal}")
                signal_frame = None

        if raw_option:
            try:
                option_meta = json.loads(raw_option)
            except Exception:
                print(f"--- [TASK order_mgmt: {user_id}] Invalid JSON in option cache value. raw_option={raw_option}")
                option_meta = None

        # Compose market_state payload expected by main.js
        # Use defaults where data is missing so frontend doesn't break
        nifty_payload = {}
        if signal_frame:
            # Ensure fields exist and are typed properly
            nifty_payload = {
                "ltp": signal_frame.get("ltp"),
                "signal": signal_frame.get("signal"),
                "sma_10": signal_frame.get("sma_10"),
                "sma_25": signal_frame.get("sma_25"),
                "sma_50": signal_frame.get("sma_50"),
                "sma_100": signal_frame.get("sma_100"),
            }

        final_trade_instruments = option_meta if option_meta else {}

        market_state = {
            "overall_market_trend": (signal_frame.get("signal") if signal_frame else "NEUTRAL"),
            "indices_data": {NIFTY_50_NAME: nifty_payload},
            "final_trade_instruments": final_trade_instruments,
            "active_trade": None,
        }

        # Retrieve active trade if any (cache uses same 'cache' instance)
        active_trade_key = f"active_trade_{user.id}"
        raw_trade_json = _normalize_cached_value(cache.get(active_trade_key))
        if raw_trade_json:
            try:
                active_trade_data = json.loads(raw_trade_json)
                market_state["active_trade"] = active_trade_data
            except Exception:
                # corrupt active trade -> delete and ignore
                try:
                    cache.delete(active_trade_key)
                except Exception:
                    pass
                market_state["active_trade"] = None

        # Emit market update to the user's room so frontend updates even when trades are not executed
        try:
            socketio.emit("market_update", market_state, room=str(user.id))
        except Exception as e:
            print(f"--- [TASK order_mgmt: {user_id}] Failed to emit market_update: {e}")

        # --- Decide to trade only if both signal and option meta are available ---
        if not signal_frame or not option_meta:
            # Debug prints to assist troubleshooting
            if not signal_frame:
                print(f"--- [TASK order_mgmt: {user_id}] No trend signal available (key tried: {TREND_SIGNAL_KEY}).")
            if not option_meta:
                print(f"--- [TASK order_mgmt: {user_id}] No option_meta available (key tried: {GLOBAL_OPTION_KEY}).")
            print(f"--- [TASK order_mgmt: {user_id}] Skipping trade decision this run. ---")
            return

        # --- Trading decision & execution ---
        decide_and_execute_trade(market_state, user, headers, active_trade_key)

        print(f"--- [TASK order_mgmt: {user_id}] Task Complete ---")

    except Exception as e:
        print(f"--- [TASK order_mgmt: {user_id}] Error during execution: {e} ---")
        if db.session.is_active:
            db.session.rollback()
        raise
    finally:
        # Prevent DB connection leaks
        db.session.remove()


# --- 3️⃣ DECISION LOGIC ---
def decide_and_execute_trade(market_state, user, headers, active_trade_key):
    """Decides whether to enter a CALL or PUT trade."""
    now = datetime.datetime.now().time()
    if not (datetime.time(9, 30) <= now <= datetime.time(15, 15)):
        return

    overall_trend = market_state.get("overall_market_trend")
    trade_meta = market_state.get("final_trade_instruments", {})

    target_option, trade_type = None, None
    if overall_trend == "CALL BUY" and trade_meta.get("atm_call"):
        target_option = trade_meta["atm_call"]
        trade_type = "CALL"
    elif overall_trend == "PUT BUY" and trade_meta.get("atm_put"):
        target_option = trade_meta["atm_put"]
        trade_type = "PUT"

    if not target_option:
        return

    # Limit daily trades per user
    today = datetime.date.today().isoformat()
    count_key = f"{trade_type.lower()}_trade_count_{user.id}_{today}"
    current_trades_raw = cache.get(count_key)
    current_trades = 0
    if current_trades_raw:
        try:
            if isinstance(current_trades_raw, bytes):
                current_trades = int(current_trades_raw.decode("utf-8"))
            else:
                current_trades = int(current_trades_raw)
        except Exception:
            current_trades = 0

    if current_trades >= 4:
        print(f"    -> Daily trade limit reached for {trade_type} trades.")
        return

    instrument_token = target_option.get("instrument_key")
    if not instrument_token:
        print("    -> ⚠️ No instrument_token in target_option. Aborting trade.")
        return

    entry_order_id = place_market_order(instrument_token, user.quantity, "BUY", headers)
    if not entry_order_id:
        return

    entry_price = get_order_fill_price(entry_order_id, user.access_token)
    if not entry_price:
        return

    # Update trade count in cache
    try:
        cache.set(count_key, str(current_trades + 1), timeout=86400)
    except Exception:
        pass

    trade_details = {
        "type": trade_type,
        "instrument_token": instrument_token,
        "quantity": user.quantity,
        "entry_price": entry_price,
        "entry_order_id": entry_order_id,
        "entry_time": datetime.datetime.now().isoformat(),
    }
    try:
        cache.set(active_trade_key, json.dumps(trade_details), timeout=86400)
    except Exception:
        pass

    # Notify clients
    try:
        socketio.emit("trade_notification", {"message": f"{trade_type} Trade Entered!"}, room=str(user.id))
    except Exception:
        pass


# --- 4️⃣ TRADE MANAGEMENT LOGIC ---
def manage_active_trade(trade, market_state, user, headers, active_trade_key):
    """Manages open position based on SL/TP/Time."""
    now = datetime.datetime.now().time()

    # Auto square-off
    if now >= datetime.time(15, 15):
        exit_side = "SELL" if trade["type"] == "CALL" else "BUY"
        place_market_order(trade["instrument_token"], trade["quantity"], exit_side, headers)
        try:
            cache.delete(active_trade_key)
        except Exception:
            pass
        try:
            socketio.emit("trade_notification", {"message": f"Exited {trade['type']} (Auto Square-Off)"}, room=str(user.id))
        except Exception:
            pass
        return

    nifty_signal_data = market_state.get("indices_data", {}).get(NIFTY_50_NAME, {}) or {}
    try:
        nifty_ltp_float = float(nifty_signal_data.get("ltp")) if nifty_signal_data.get("ltp") is not None else None
    except Exception:
        nifty_ltp_float = None

    try:
        nifty_sma25 = float(nifty_signal_data.get("sma_25")) if nifty_signal_data.get("sma_25") is not None else None
    except Exception:
        nifty_sma25 = None

    if not nifty_ltp_float or not nifty_sma25:
        print("    -> ⚠️ Missing Nifty LTP or SMA25 data for SL check.")
        return

    is_exit = False
    reason = None
    if trade["type"] == "CALL" and nifty_ltp_float < nifty_sma25:
        is_exit, reason = True, "Nifty LTP < SMA25 (CALL SL)"
    elif trade["type"] == "PUT" and nifty_ltp_float > nifty_sma25:
        is_exit, reason = True, "Nifty LTP > SMA25 (PUT SL)"

    if is_exit:
        exit_side = "SELL" if trade["type"] == "CALL" else "BUY"
        place_market_order(trade["instrument_token"], trade["quantity"], exit_side, headers)
        try:
            cache.delete(active_trade_key)
        except Exception:
            pass
        try:
            socketio.emit("trade_notification", {"message": f"Exited {trade['type']}: {reason}"}, room=str(user.id))
        except Exception:
            pass
        return

    print("    -> ✅ Active trade maintained. Waiting for exit signal.")
