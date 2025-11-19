# app/tasks/task_merge.py (FINAL ROBUST VERSION)
import os
import pandas as pd
import json
from datetime import datetime
import pytz
from app.extensions import celery_app, cache
from app.extensions import socketio
from app.tasks.utils import get_live_ltp

# Helper function to conditionally localize or convert timezone
def localize_or_convert_to_ist(ts, ist):
    if pd.isna(ts):
        return ts
    # If timestamp is naive (no tz info), localize it to IST
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        return ts.tz_localize(ist)
    # If timestamp is tz-aware, convert it to IST
    elif ts.tzinfo != ist:
        return ts.tz_convert(ist)
    return ts # Already in IST

@celery_app.task(bind=True, ignore_result=False)
def merge_hist_live(self, instrument_key="NSE_INDEX|Nifty 50", interval="1m"):
    """
    Merge historical candle data with live LTP and persist merged_data.
    """
    ist = pytz.timezone("Asia/Kolkata")
    now_ist = datetime.now(ist)
    
    hist_cache_key = f"historical_data:{instrument_key}"
    merged_cache_key = f"merged_data:{instrument_key}:{interval}"

    # 1) Prefer previously merged data (so merged grows). If not present, load historical.
    df = None
    merged_json = cache.get(merged_cache_key)
    if merged_json:
        if isinstance(merged_json, bytes):
            merged_json = merged_json.decode("utf-8")
        try:
            df = pd.DataFrame(json.loads(merged_json))
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df["timestamp"] = df["timestamp"].apply(lambda ts: localize_or_convert_to_ist(ts, ist))
            
            df = df.sort_values("timestamp").reset_index(drop=True)
            print(f"[merge_hist_live] ✅ Loaded existing merged_data with {len(df)} rows.")
        except Exception as e:
            print(f"[merge_hist_live] ⚠️ Failed to parse merged_data, falling back to historical: {e}")
            df = None

    # 2) If no merged data, load historical_data (one-time base)
    if df is None:
        hist_json = cache.get(hist_cache_key)
        if not hist_json:
            print(f"[merge_hist_live] ⚠️ No historical data in cache for {instrument_key}")
            return None

        if isinstance(hist_json, bytes):
            hist_json = hist_json.decode("utf-8")

        try:
            df = pd.DataFrame(json.loads(hist_json))
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df["timestamp"] = df["timestamp"].apply(lambda ts: localize_or_convert_to_ist(ts, ist))
            
            df = df.sort_values("timestamp").reset_index(drop=True)
            print(f"[merge_hist_live] ✅ Loaded historical_data with {len(df)} rows.")
        except Exception as e:
            print(f"[merge_hist_live] ❌ Error loading historical: {e}")
            return None

    # 3) Get live LTP
    live_data = get_live_ltp(instrument_key)
    if not live_data or "ltp" not in live_data:
        print(f"[merge_hist_live] ⚠️ No live LTP for {instrument_key}")
        return None
    
    try:
        ltp = float(live_data["ltp"])
    except Exception:
        print(f"[merge_hist_live] ❌ Invalid LTP format: {live_data}")
        return None

    # 4) Determine last timestamp and current minute timestamp
    if df.empty:
        last_ts = None
    else:
        last_ts = df["timestamp"].iloc[-1]

    current_bar_ts = now_ist.replace(second=0, microsecond=0)

    # 5) CRITICAL FIX: Logic to UPDATE the last candle or APPEND a new one
    
    if last_ts is None or current_bar_ts > last_ts:
        # CASE A: APPEND a new candle (first run OR a new minute boundary crossed)
        new_row = {
            "timestamp": current_bar_ts,  # store as datetime (Timestamp)
            "open": ltp,
            "high": ltp,
            "low": ltp,
            "close": ltp,
            "volume": 0,
            "oi": 0,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        print(f"[merge_hist_live] ✅ Added new live candle @ {current_bar_ts} | LTP={ltp}")

    elif current_bar_ts == last_ts and not df.empty:
        # CASE B: UPDATE the existing, in-progress candle (same minute)
        last_idx = df.index[-1]
        
        df.at[last_idx, 'close'] = ltp
        df.at[last_idx, 'high'] = max(df.at[last_idx, 'high'], ltp)
        df.at[last_idx, 'low'] = min(df.at[last_idx, 'low'], ltp)
        
        print(f"[merge_hist_live] ✅ Updated live candle @ {current_bar_ts} | LTP={ltp}")

    else:
        print(f"[merge_hist_live] ⚠️ Skipping LTP operation. last_ts={last_ts}, current_bar_ts={current_bar_ts}")

    # 6) Final check and sort
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

    # 7) Persist merged_data to cache and disk
    try:
        cache.set(merged_cache_key, df.to_json(orient="records", date_format="iso"), timeout=300)
        os.makedirs("data", exist_ok=True)
        file_path = os.path.join("data", f"merged_data_{instrument_key.replace('|', '_')}_{interval}.csv")
        df.to_csv(file_path, index=False)
        print(f"[merge_hist_live] ✅ Saved merged candles ({len(df)}) to cache & {file_path}")
    except Exception as e:
        print(f"[merge_hist_live] ❌ Failed to persist merged data: {e}")

    try:
        socketio.emit(
            "merged_data_update",
            {"symbol": instrument_key, "interval": interval, "data": df.tail(2).to_dict(orient="records")},
            namespace="/stream"
        )
    except Exception:
        pass

    return None