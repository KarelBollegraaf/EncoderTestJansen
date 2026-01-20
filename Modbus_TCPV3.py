"""
Modbus_TCPV3.py

Background Modbus polling module.

Reads:
- Bale number from %MW28000
- Event word  from %MW70

Exports:
- state (MachineState)  -> importable global state object
- start() / stop()      -> control polling thread

Environment variables (used on Edge / IEM / Docker):
- PLC_IP           (default: 192.168.1.15)
- PLC_PORT         (default: 502)
- PLC_DEVICE_ID    (default: 1)
- PLC_POLL_SEC     (default: 0.1)
- PLC_TIMEOUT_SEC  (default: 3.0)
"""

import os
import time
import threading
from pymodbus.client import ModbusTcpClient

# ---- Modbus Configuration (ENV first, fallback to defaults) ----
MODBUS_IP = os.getenv("PLC_IP", "192.168.1.15")
MODBUS_PORT = int(os.getenv("PLC_PORT", "502"))
DEVICE_ID = int(os.getenv("PLC_DEVICE_ID", "1"))

POLL_SEC = float(os.getenv("PLC_POLL_SEC", "0.1"))
TIMEOUT_SEC = float(os.getenv("PLC_TIMEOUT_SEC", "3.0"))

# MW addresses (Schneider notation %MWxxxx)
MW_BALE_NUMBER = 28000  # %MW28000
MW_EVENT_WORD = 70      # %MW70

# ---- Machine State Class ----
class MachineState:
    def __init__(self):
        self.BaleNumber = 0
        self.EventWord = 0

        # events you care about (extend if needed)
        self.RamGoesForward = False  # bit 0
        self.RamGoesReturn = False   # bit 1

        # optional list of active event names
        self.ActiveEvents = []

        # last successful update timestamp
        self.LastUpdateEpoch = 0.0

        # connection status
        self.Connected = False

    def update_from_modbus(self, bale_number: int, event_word: int):
        self.BaleNumber = int(bale_number)
        self.EventWord = int(event_word)

        # bit decoding
        self.RamGoesForward = ((self.EventWord >> 0) & 1) == 1
        self.RamGoesReturn  = ((self.EventWord >> 1) & 1) == 1

        names = []
        if self.RamGoesForward:
            names.append("RamGoesForward")
        if self.RamGoesReturn:
            names.append("RamGoesReturn")
        self.ActiveEvents = names

        self.LastUpdateEpoch = time.time()


# ---- Persistent state object (importable) ----
state = MachineState()

# ---- Internal worker thread ----
_stop_event = threading.Event()
_thread = None


def _read_word(client: ModbusTcpClient, address: int) -> int:
    """
    Read one holding register. Supports multiple pymodbus call signatures.
    """
    # Newer pymodbus (v3+) often uses device_id=
    try:
        resp = client.read_holding_registers(address, count=1, device_id=DEVICE_ID)
    except TypeError:
        # Older pymodbus uses unit= or slave=
        try:
            resp = client.read_holding_registers(address, count=1, unit=DEVICE_ID)
        except TypeError:
            resp = client.read_holding_registers(address, count=1, slave=DEVICE_ID)

    if resp is None or getattr(resp, "isError", lambda: True)():
        raise RuntimeError(f"Modbus error reading %MW{address}: {resp}")
    return int(resp.registers[0])


def _poll_loop():
    client = ModbusTcpClient(MODBUS_IP, port=MODBUS_PORT, timeout=TIMEOUT_SEC)

    # simple backoff so we don't hammer the network on failures
    backoff = 0.5
    max_backoff = 5.0

    while not _stop_event.is_set():
        try:
            if not client.connect():
                state.Connected = False
                time.sleep(backoff)
                backoff = min(max_backoff, backoff * 1.5)
                continue

            # connected
            state.Connected = True
            backoff = 0.5  # reset backoff after success

            bale_number = _read_word(client, MW_BALE_NUMBER)
            event_word = _read_word(client, MW_EVENT_WORD)

            state.update_from_modbus(bale_number, event_word)

            time.sleep(POLL_SEC)

        except Exception:
            # keep the thread alive; mark disconnected and retry
            state.Connected = False
            try:
                client.close()
            except Exception:
                pass
            time.sleep(backoff)
            backoff = min(max_backoff, backoff * 1.5)

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


# ---- Run behavior ----
if __name__ == "__main__":
    start()
    print("Modbus polling started (Ctrl+C to stop).")
    print(f"Using PLC_IP={MODBUS_IP} PLC_PORT={MODBUS_PORT} PLC_DEVICE_ID={DEVICE_ID} PLC_POLL_SEC={POLL_SEC}")
    try:
        while True:
            print(
                f"Connected: {state.Connected} | "
                f"BaleNumber: {state.BaleNumber} | EventWord: {state.EventWord} | "
                f"RamF: {state.RamGoesForward} | RamR: {state.RamGoesReturn} | "
                f"ActiveEvents: {state.ActiveEvents}"
            )
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop()
        print("Stopped.")
else:
    # Imported -> autostart in background (same pattern as your previous file)
    start()
