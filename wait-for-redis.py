# In file: wait-for-redis.py
import redis
import time
import os

retries = 5
delay = 5
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

for i in range(retries):
    try:
        r = redis.from_url(redis_url)
        r.ping()
        print("Redis is ready.")
        exit(0) # Exit with success
    except redis.exceptions.ConnectionError:
        print(f"Redis not ready yet. Waiting {delay}s... ({i+1}/{retries})")
        time.sleep(delay)

print("Could not connect to Redis after several attempts. Exiting.")
exit(1) # Exit with failure