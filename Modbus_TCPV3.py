import os
import time
import threading
from pymodbus.client import ModbusTcpClient

def _clean(raw: str) -> str:
    if raw is None:
        return ""
    return raw.strip().strip('"').strip("'").strip()

def _env_str(name: str, default: str) -> str:
    return _clean(os.getenv(name, default))

def _env_int(name: str, default: int) -> int:
    return int(_clean(os.getenv(name, str(default))))

def _env_float(name: str, default: float) -> float:
    return float(_clean(os.getenv(name, str(default))))

# ---- Modbus Configuration ----
MODBUS_IP = _env_str("PLC_IP", "192.168.1.15")
MODBUS_PORT = _env_int("PLC_PORT", 502)
DEVICE_ID = _env_int("PLC_DEVICE_ID", 1)

MW_BALE_NUMBER = 28000  # %MW28000
MW_EVENT_WORD  = 70     # %MW70
POLL_SEC = _env_float("PLC_POLL_SEC", 0.1)

# ---- Machine State Class ----
class MachineState:
    def __init__(self):
        self.BaleNumber = 0
        self.EventWord = 0
        self.RamGoesForward = False
        self.RamGoesReturn = False
        self.ActiveEvents = []

    def update_from_modbus(self, bale_number: int, event_word: int):
        self.BaleNumber = bale_number
        self.EventWord = event_word

        # bit decoding
        self.RamGoesForward = ((event_word >> 0) & 1) == 1
        self.RamGoesReturn  = ((event_word >> 1) & 1) == 1

        names = []
        if self.RamGoesForward:
            names.append("RamGoesForward")
        if self.RamGoesReturn:
            names.append("RamGoesReturn")
        self.ActiveEvents = names


# ---- Persistent state object (importable) ----
state = MachineState()

# ---- Internal worker thread ----
_stop_event = threading.Event()
_thread = None

def _read_word(client: ModbusTcpClient, address: int) -> int:
    resp = client.read_holding_registers(address, count=1, device_id=DEVICE_ID)
    if resp.isError():
        raise RuntimeError(f"Modbus error reading %MW{address}: {resp}")
    return int(resp.registers[0])

def _poll_loop():
    client = ModbusTcpClient(MODBUS_IP, port=MODBUS_PORT, timeout=3)

    while not _stop_event.is_set():
        try:
            if not client.connect():
                time.sleep(1.0)
                continue

            bale_number = _read_word(client, MW_BALE_NUMBER)
            event_word  = _read_word(client, MW_EVENT_WORD)

            state.update_from_modbus(bale_number, event_word)
            time.sleep(POLL_SEC)

        except Exception:
            # don’t crash thread; retry
            time.sleep(1.0)

    try:
        client.close()
    except Exception:
        pass

def start():
    """Start background Modbus polling (non-blocking)."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_poll_loop, daemon=True)
    _thread.start()

def stop():
    """Stop background Modbus polling."""
    _stop_event.set()

# Imported -> non-blocking background loop
start()

if __name__ == "__main__":
    print("Modbus polling started (Ctrl+C to stop).")
    try:
        while True:
            print(
                f"BaleNumber: {state.BaleNumber} | EventWord: {state.EventWord} | "
                f"RamF: {state.RamGoesForward} | RamR: {state.RamGoesReturn}"
            )
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop()
        print("Stopped.")
