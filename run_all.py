import threading
import uvicorn

def start_collector():
    # this imports and runs your existing code file
    import TestEncoderJanssenV3  # noqa: F401

if __name__ == "__main__":
    t = threading.Thread(target=start_collector, daemon=True)
    t.start()

    uvicorn.run("webapp:app", host="0.0.0.0", port=8000, log_level="info")
