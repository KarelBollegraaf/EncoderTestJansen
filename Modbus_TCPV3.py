"""
Modbus_TCPV3.py

Background Modbus polling module.

Reads (Schneider notation %MWxxxx):
- Bale number from %MW28000
- Event word  from %MW70

Exports:
- state (MachineState)  -> importable global state object
- start() / stop()      -> control polling thread

Environment variables:
- PLC_IP           (default: 192.168.1.15)
- PLC_PORT         (default: 502)          <-- accepts 502, "502", '502'
- PLC_DEVICE_ID    (default: 1)            <-- accepts 1, "1", '1'
- PLC_POLL_SEC     (default: 0.1)          <-- accepts 0.1, "0.1", '0.1'
- PLC_TIMEOUT_SEC  (default: 3.0)
"""

import os
import time
import threading
from pymodbus.client import ModbusTcpClient

# -------- robust env parsing (handles '"502"' and similar) --------
def _clean_env(raw: str) -> str:
    if raw is None:
        return ""
    return raw.strip().strip('"').strip("'").strip()

def _env_str(name: str, default: str) -> str:
    return _clean_env(os.getenv(name, default))

def _env_int(name: str, default: int) -> int:
    raw = _clean_env(os.getenv(name, str(default)))
    return int(raw)

def _env_float(name: str, default: float) -> float:
    raw = _clean_env(os.getenv(name, str(default)))
    return float(raw)


# ---- Modbus Configuration (ENV first, fallback defaults) ----
MODBUS_IP = _env_str("PLC_IP", "192.168.1.15")
MODBUS_PORT = _env_int("PLC_PORT", 502)
DEVICE_ID = _env_int("PLC_DEVICE_ID", 1)

POLL_SEC = _env_float("PLC_POLL_SEC", 0.1)
TIMEOUT_SEC = _env_float("PLC_TIMEOUT_SEC", 3.0)

# MW addresses
MW_BALE_NUMBER = 28000  # %MW28000
MW_EVENT_WORD = 70      # %MW70


class MachineState:
    """
    Keep names compatible with your existing code/logs as much as possible.
    """
    def __init__(self):
        # raw values
        self.qBaleNumber = 0
        self.EventWord = 0

        # decoded bits
        self.EventIdentifier = [0] * 16  # list of 16 bits
        self.iRamGoesForward = False
        self.iRamGoesReturn = False

        # optional flags (safe defaults)
        self.sBaleReady = False
        self.sBaleFinished = False

        # status
        self.Connected = False
        self.LastUpdateEpoch = 0.0

    def update_from_modbus(self, bale_number: int, event_word: int):
        self.qBaleNumber = int(bale_number)
        self.EventWord = int(event_word)

        # decode to 16 bits
        bits = []
        for i in range(16):
            bits.append((self.EventWord >> i) & 1)
        self.EventIdentifier = bits

        # common signals (adjust bit positions if your PLC differs)
        self.iRamGoesForward = bits[0] == 1
        self.iRamGoesReturn = bits[1] == 1

        self.LastUpdateEpoch = time.time()


# importable singleton
state = MachineState()

_stop_event = threading.Event()
_thread = None


def _read_word(client: ModbusTcpClient, address: int) -> int:
    """
    Read one holding register. Supports multiple pymodbus call signatures.
    """
    try:
        resp = client.read_holding_registers(address, count=1, device_id=DEVICE_ID)
    except TypeError:
        try:
            resp = client.read_holding_registers(address, count=1, unit=DEVICE_ID)
        except TypeError:
            resp = client.read_holding_registers(address, count=1, slave=DEVICE_ID)

    if resp is None or getattr(resp, "isError", lambda: True)():
        raise RuntimeError(f"Modbus error reading %MW{address}: {resp}")
    return int(resp.registers[0])


def _poll_loop():
    client = ModbusTcpClient(MODBUS_IP, port=MODBUS_PORT, timeout=TIMEOUT_SEC)

    backoff = 0.5
    max_backoff = 5.0

    while not _stop_event.is_set():
        try:
            if not client.connect():
                state.Connected = False
                time.sleep(backoff)
                backoff = min(max_backoff, backoff * 1.5)
                continue

            state.Connected = True
            backoff = 0.5

            bale_number = _read_word(client, MW_BALE_NUMBER)
            event_word = _read_word(client, MW_EVENT_WORD)

            state.update_from_modbus(bale_number, event_word)

            time.sleep(POLL_SEC)

        except Exception:
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
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_poll_loop, daemon=True)
    _thread.start()


def stop():
    _stop_event.set()


# autostart when imported (same behavior as before)
start()
