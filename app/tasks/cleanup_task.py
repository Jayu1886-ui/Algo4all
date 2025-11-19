# In file: app/tasks/cleanup_task.py  ✅ FINAL VERSION

import os
from app.extensions import celery_app
from app import cache
from app.extensions import cache

@celery_app.task(bind=True, ignore_result=True)
def end_of_day_cleanup(self, symbol, fast, slow):
    """
    Scheduled task to perform end-of-day cleanup:
      1️⃣ Remove per-user cached market states from Redis.
      2️⃣ Delete the global access_token.txt file (used by the streamer/system).
    """
    from app.models import User

    print("\n---------------------------------------------")
    print("--- 🧹 STARTING END OF DAY CLEANUP TASK ---")
    print("---------------------------------------------")

    # --- Step 1: Clean Redis cache keys for all users ---
    all_users = User.query.all()
    print(f"Found {len(all_users)} users in DB for cleanup...")

    deleted_count = 0
    for user in all_users:
        cache_key = f"market_state_{user.id}"
        if cache.delete(cache_key):
            print(f"  ✅ Deleted cache key: {cache_key}")
            deleted_count += 1
        else:
            print(f"  ⚠️ Cache key not found: {cache_key}")

    print(f"🗑️ Redis Cleanup Completed: {deleted_count} keys removed.")

    # --- Step 2: Remove global access_token.txt file ---
    token_file = "access_token.txt"
    if os.path.exists(token_file):
        try:
            os.remove(token_file)
            print(f"✅ Successfully removed: {token_file}")
        except Exception as e:
            print(f"❌ Error deleting {token_file}: {e}")
    else:
        print("ℹ️ No access_token.txt found to delete.")

    print("---------------------------------------------")
    print("--- ✅ END OF DAY CLEANUP COMPLETED ---")
    print("---------------------------------------------\n")
