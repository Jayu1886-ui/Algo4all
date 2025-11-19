# ============================================
# FILE: app/tasks/task_trend.py (FINAL CORRECTED VERSION)
# PURPOSE: Analyze trend (Bullish/Bearish) using LTP + SMA values
# ============================================

import json
import pandas as pd
from datetime import datetime
import pytz

from app.extensions import celery_app, cache
from app.tasks.utils import get_live_ltp # <-- IMPORTANT: Use the helper to get LTP


@celery_app.task(bind=True, ignore_result=False)
def analyze_trend(self, instrument_key="NSE_INDEX|Nifty 50", short_period=10, long_period=100, interval="1m"):
    """
    Analyze trend direction (CALL BUY / PUT BUY) based on:
      ✅ Bullish = LTP > SMA(10) > SMA(25) > SMA(50) > SMA(100)
      ✅ Bearish = LTP < SMA(10) < SMA(25) < SMA(50) < SMA(100)
    """
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n--- [TASK: TREND] Starting Trend Analysis for {instrument_key} @ {now} ---")

    # --- Step 1: Fetch SMA Data ---
    sma_cache_key = f"sma_data:{instrument_key}:{interval}"
    sma_json = cache.get(sma_cache_key)
    if not sma_json:
        print(f"    -> ⚠️ No SMA data found in cache at {sma_cache_key}. Skipping trend analysis.")
        return None

    try:
        sma_df = pd.DataFrame(json.loads(sma_json))
        sma_df["timestamp"] = pd.to_datetime(sma_df["timestamp"])
        sma_df = sma_df.sort_values("timestamp")
        latest_row = sma_df.iloc[-1]
    except Exception as e:
        print(f"    -> ❌ Error parsing SMA data: {e}")
        return None

    # --- Step 2: Fetch Latest LTP (Using Helper) ---
    # 💥 CRITICAL FIX: Use the get_live_ltp helper to retrieve and format the value
    live_data = get_live_ltp(instrument_key) 
    
    if not live_data or "ltp" not in live_data:
        print(f"    -> ⚠️ No live LTP found for {instrument_key}. Skipping trend analysis.")
        return None

    try:
        # The helper returns {'ltp': 'value_string'}
        ltp = float(live_data["ltp"])
    except ValueError:
        print(f"    -> ❌ Invalid LTP format returned by helper: {live_data['ltp']}")
        return None
    # ----------------------------------------------------

    sma_10 = latest_row.get("sma_10")
    sma_25 = latest_row.get("sma_25")
    sma_50 = latest_row.get("sma_50")
    sma_100 = latest_row.get("sma_100")

    # Ensure all SMAs are available and not NaN (since rolling average produces NaNs at the start)
    if any(pd.isna([sma_10, sma_25, sma_50, sma_100])):
        print(f"    -> ⚠️ SMA data incomplete (NaNs present), skipping trend check.")
        return None

    # --- Step 3: Determine Trend (FINAL CORRECTED LOGIC) ---
    trend_signal = "NEUTRAL"
    
    # SMAs Stacked Bullish
    stacked_bullish = (sma_10 > sma_25) and (sma_10 > sma_50) and (sma_10 > sma_100)
    
    # SMAs Stacked Bearish
    stacked_bearish = (sma_10 < sma_25) and (sma_10 < sma_50) and (sma_10 < sma_100)

    # Bullish condition: LTP > ALL SMAs AND SMAs are Stacked Bullish
    if (ltp > sma_10) and (ltp > sma_25) and (ltp > sma_50) and (ltp > sma_100) and stacked_bullish:
        trend_signal = "CALL BUY"

    # Bearish condition: LTP < ALL SMAs AND SMAs are Stacked Bearish
    elif (ltp < sma_10) and (ltp < sma_25) and (ltp < sma_50) and (ltp < sma_100) and stacked_bearish:
        trend_signal = "PUT BUY"

    # --- Step 4: Cache Trend Result ---
    trend_cache_key = "trend_signal:NSE_INDEX|Nifty 50"
    trend_payload = {
        "instrument": instrument_key,
        "ltp": ltp,
        "sma_10": sma_10,
        "sma_25": sma_25,
        "sma_50": sma_50,
        "sma_100": sma_100,
        "signal": trend_signal,
        "timestamp": now,
    }

    # Cache the JSON payload. Timeout should be very short as this runs often.
    cache.set(trend_cache_key, json.dumps(trend_payload), timeout=120) 
    
    print(f"    -> ✅ Trend: {trend_signal} | LTP: {ltp} | SMA10: {sma_10} | SMA25: {sma_25} | SMA50: {sma_50} | SMA100: {sma_100}")


    print(f"--- [TASK: TREND] Completed Trend Analysis for {instrument_key} ---\n")
    return trend_payload