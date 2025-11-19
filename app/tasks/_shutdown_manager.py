# app/tasks/_shutdown_manager.py
import threading
import signal

STREAMER_STOP_EVENT = threading.Event()
SHUTDOWN_TRIGGERED = False

def set_shutdown_triggered():
    global SHUTDOWN_TRIGGERED
    if not SHUTDOWN_TRIGGERED:
        SHUTDOWN_TRIGGERED = True
        STREAMER_STOP_EVENT.set()
        print("\n[SHUTDOWN] GLOBAL STOP SIGNAL ACTIVATED.")

def is_shutdown_requested():
    return SHUTDOWN_TRIGGERED or STREAMER_STOP_EVENT.is_set()

def sigint_handler(sig, frame):
    print("\n[SHUTDOWN] Ctrl+C received. Initiating graceful shutdown...")
    set_shutdown_triggered()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
def initialize_signal_handler():
    # Only set the handler if we are in the main thread of the process
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, sigint_handler)
        print("[SHUTDOWN] SIGINT handler initialized.")