# FILE: app/tasks/task_sma.py
import pandas as pd
import json
import traceback
from datetime import datetime
import pytz
from app.extensions import celery_app, cache

@celery_app.task(bind=True, ignore_result=False)
def calculate_sma_for_closed_bar(self, instrument_key="NSE_INDEX|Nifty 50", interval="1m"):
    """Compute SMA(10,25,50,100) for entire merged candle data and cache full results."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n--- [TASK: SMA] Starting SMA calculation for {instrument_key} @ {now} ---")

    merged_cache_key = f"merged_data:{instrument_key}:{interval}"
    sma_cache_key = f"sma_data:{instrument_key}:{interval}"  # store full SMA data here

    # 1️⃣ Fetch merged candle data
    merged_json = cache.get(merged_cache_key)
    if not merged_json:
        print(f"    -> ⚠️ No merged data found in cache for {instrument_key}. Skipping SMA calc.")
        return None

    try:
        if isinstance(merged_json, bytes):
            merged_json = merged_json.decode("utf-8")

        data = json.loads(merged_json)
        merged_df = pd.DataFrame(data)

        # Ensure timestamp dtype
        merged_df["timestamp"] = pd.to_datetime(merged_df["timestamp"], errors="coerce")
        merged_df = merged_df.sort_values("timestamp").reset_index(drop=True)

        # Ensure numeric close values
        merged_df["close"] = pd.to_numeric(merged_df["close"], errors="coerce")

    except Exception as e:
        print(f"    -> ❌ Error parsing merged data: {e}\n{traceback.format_exc()}")
        return None

    # 2️⃣ Compute SMAs on the FULL dataset
    for period in [10, 25, 50, 100]:
        merged_df[f"sma_{period}"] = merged_df["close"].rolling(window=period, min_periods=period).mean()

    # 3️⃣ Cache the FULL SMA dataset
    try:
        cache.set(sma_cache_key, merged_df.to_json(orient="records", date_format="iso"), timeout=300)
        print(f"    -> ✅ Cached FULL SMA(10,25,50,100) for {len(merged_df)} rows.")
    except Exception as e:
        print(f"    -> ❌ Failed to cache SMA data: {e}\n{traceback.format_exc()}")

    print(f"--- [TASK: SMA] Completed SMA Calculation for {instrument_key} ---\n")
    return None
