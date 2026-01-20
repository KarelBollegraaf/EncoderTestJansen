import os
import time
import threading
import uvicorn

HEARTBEAT_FILE = os.getenv("HEARTBEAT_FILE", "/tmp/collector_heartbeat.txt")
WATCHDOG_STALE_SEC = float(os.getenv("WATCHDOG_STALE_SEC", "20"))

def start_collector():
    # Import starts your collector loop
    import TestEncoderJanssenV3  # noqa: F401

def watchdog_loop(collector_thread: threading.Thread):
    while True:
        # if thread dies -> restart container
        if not collector_thread.is_alive():
            print("Collector thread died -> forcing restart")
            os._exit(1)

        # if heartbeat gets stale -> collector likely blocked -> restart
        try:
            mtime = os.path.getmtime(HEARTBEAT_FILE)
            if (time.time() - mtime) > WATCHDOG_STALE_SEC:
                print("Collector heartbeat stale -> forcing restart")
                os._exit(1)
        except FileNotFoundError:
            # allow startup grace
            pass
        except Exception as e:
            print("Watchdog error:", e)

        time.sleep(2)

if __name__ == "__main__":
    t = threading.Thread(target=start_collector, daemon=False)
    t.start()

    w = threading.Thread(target=watchdog_loop, args=(t,), daemon=True)
    w.start()

    uvicorn.run("webapp:app", host="0.0.0.0", port=8000, log_level="info")
