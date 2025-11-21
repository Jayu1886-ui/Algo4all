#!/bin/bash
# ==========================================================
#  ALGO4ALL - Unified Startup Script ✅ FINAL VERSION
# ==========================================================

# 1. Start PostgreSQL (REQUIRED BEFORE APP START)
echo "Starting PostgreSQL service..."
sudo service postgresql start
# Optional: Wait a few seconds for the DB to initialize fully
sleep 5

echo "---------------------------------------------"
echo "--- Starting ALGO4ALL Environment ---"
echo "---------------------------------------------"

# --- Step 1: Load .env variables ---
if [ -f .env ]; then
  echo "Loading .env variables..."
  export $(grep -v '^#' .env | xargs)
  echo ".env loaded successfully."
else
  echo "ERROR: .env file not found!"
  exit 1
fi

# --- Step 2: Check for access_token.txt ---
if [ ! -f "access_token.txt" ]; then
  echo "---------------------------------------------"
  echo "⚠️  Missing access_token.txt file."
  echo "➡️  Please log in once through the web app to generate a new Upstox access token."
  echo "---------------------------------------------"
  # Optional: uncomment next line to auto-exit instead of running partial services
  #exit 1
fi

# --- Step 3: Ensure Redis is running ---
if pgrep -x "redis-server" >/dev/null; then
  echo "Redis already running."
else
  echo "Starting Redis..."
  redis-server --daemonize yes
  echo "Redis started successfully."
fi

rm -f celerybeat-schedule*

# --- Step 4: Launch Celery Worker ---
echo "Launching Celery Worker..."
celery -A celery_app worker -P gevent -c 8 --loglevel=INFO &
CELERY_WORKER_PID=$!
echo "Celery Worker PID: $CELERY_WORKER_PID"

# --- Step 5: Launch Market Data Streamer ---
if [ ! -f "access_token.txt" ]; then
  echo "Access token file not found. Waiting 2 minuts..."
  sleep 180
fi

echo "Launching Market Data Streamer..."
python -m app.tasks.streamer.streamer &
STREAMER_PID=$!
echo "Streamer PID: $STREAMER_PID"

# --- Step 6: Launch Celery Beat ---
echo "Launching Celery Beat..."
celery -A celery_app beat --loglevel=INFO &
CELERY_BEAT_PID=$!
echo "Celery Beat PID: $CELERY_BEAT_PID"

# --- Step 7: Start Gunicorn (Flask + SocketIO) ---
echo "🌐 Launching Gunicorn Server (on localhost:8088)..."
gunicorn -c gunicorn.conf.py wsgi:application &
GUNICORN_PID=$!
echo "Gunicorn PID: $GUNICORN_PID"

# --- Final Summary ---
echo "---------------------------------------------"
echo "✅ All Services Started Successfully:"
echo "   Celery Worker : $CELERY_WORKER_PID"
echo "   Streamer      : $STREAMER_PID"
echo "   Celery Beat   : $CELERY_BEAT_PID"
echo "   Gunicorn      : $GUNICORN_PID"
echo "---------------------------------------------"


# 9️⃣ Trap interrupts (Ctrl+C) and shut down cleanly
# NOTE: TUNNEL_PID is now included in the kill list
trap "echo 'Stopping all ALGO4ALL services...'; \
kill $CELERY_WORKER_PID $CELERY_BEAT_PID $STREAMER_PID $GUNICORN_PID; \
echo '✅ All processes stopped. Exiting.'; exit" INT TERM

# 🔟 Wait indefinitely so background processes keep running
# This keeps the script active, preventing the background jobs from being terminated immediately.
wait
