from pymodbus.client import ModbusTcpClient
from datetime import datetime
import time
import math
import os

from Modbus_TCPV3 import state
from db import init_db, insert_sample

# --- Config via environment (so it works on Edge/IEM too) ---
MASTER_IP = os.getenv("ENCODER_IP", "192.168.1.250")
MODBUS_PORT = int(os.getenv("ENCODER_PORT", "502"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "0.1"))

PDIN_BASE_ADDR = 0
WORD_COUNT = 16

HEARTBEAT_FILE = os.getenv("HEARTBEAT_FILE", "/tmp/collector_heartbeat.txt")
ENCODER_TIMEOUT = float(os.getenv("ENCODER_TIMEOUT", "3"))

# Baler variables from PLC
iBaleNumber = 0
iRamGoesForward = False

# Initialize variables
sBaleNumber = 0
sReading = True
sBaleReady = False
sPreviousRamGoesForward = False

sRounds = 0.0
sRoundCounter = 0.0
sEncoderPrevious = None
sOneRoundRaw = 35999.0
sDistance = 0.0

sBaleLength_Stroke = [0.0] * 10  # RAM to store bale lengths
sBale_length_Encoder = 0.0
sRounds_Encoder = 0.0
sRamdistance = 0.0

qBaleNumber = None
qBale_length_Encoder = 0.0
qBaleLength_Stroke = [0.0] * 10

def heartbeat():
    # Update heartbeat every loop. If this stops updating, watchdog will restart container.
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass

def make_encoder_client():
    return ModbusTcpClient(MASTER_IP, port=MODBUS_PORT, timeout=ENCODER_TIMEOUT)

client = None

init_db()

while True:
    heartbeat()

    # Always keep loop alive (never crash out)
    try:
        # PLC variables from Modbus_TCPV3 background thread
        iBaleNumber = int(state.BaleNumber)
        iRamGoesForward = bool(state.RamGoesForward)

        # Initialize sBaleNumber once from PLC if still 0
        if sBaleNumber == 0:
            sBaleNumber = iBaleNumber

        # Bale becomes "ready" when PLC bale number changes (and we already had a previous bale)
        if (iBaleNumber != sBaleNumber) and (sBaleNumber != 0):
            sBaleReady = True
        else:
            sBaleReady = False

        # When bale finished -> snapshot + reset
        if sBaleReady and iBaleNumber > 0:
            print("Bale is ready")
            print(f"sBaleReady: {sBaleReady}")

            sBale_length_Encoder = sDistance
            qBale_length_Encoder = sDistance
            sRounds_Encoder = round(sRounds, 2)

            # Copy stroke list into q list
            qBaleLength_Stroke = sBaleLength_Stroke[:]

            # Clear RAM for next bale
            sBaleLength_Stroke = [0.0] * 10

            qBaleNumber = sBaleNumber
            sBaleNumber = iBaleNumber

            sReading = False
            sRoundCounter = 0.0
            sDistance = 0.0
            sRamdistance = 0.0
            sRounds = 0.0

        elif not sBaleReady:
            sReading = True

        # --- Ensure encoder client connected (self-healing) ---
        if client is None:
            client = make_encoder_client()

        if not client.connect():
            # encoder unreachable right now
            time.sleep(1.0)
            continue

        if sReading:
            # Read encoder registers
            try:
                result = client.read_input_registers(address=PDIN_BASE_ADDR, count=WORD_COUNT)
                if (not result) or (not hasattr(result, "registers")):
                    raise RuntimeError("Failed to read registers")
            except Exception as e:
                print("Encoder read error:", e)
                try:
                    client.close()
                except Exception:
                    pass
                client = None
                time.sleep(1.0)
                continue

            # Rising/falling edge detection of ram forward signal
            if (iRamGoesForward is True) and (sPreviousRamGoesForward is False):  # Rising edge
                sPreviousRamGoesForward = True

            elif (iRamGoesForward is False) and (sPreviousRamGoesForward is True):  # Falling edge
                sPreviousRamGoesForward = False

                # Store ram stroke length when falling edge happens
                if sBaleNumber == iBaleNumber:
                    print("Set ram distance")
                    time.sleep(0.3)  # small settle time (was 3s; keep short to avoid "looks stuck")

                    # distance since last strokes
                    sRamdistance = sDistance - sum(sBaleLength_Stroke)
                    sRamdistance = round(sRamdistance, 2)

                    for i in range(10):
                        if sBaleLength_Stroke[i] == 0:
                            sBaleLength_Stroke[i] = sRamdistance
                            break

            # Process register data
            words = result.registers
            timestamp = datetime.now()

            data_valid = "YES" if words[1] != 0 else "NO"

            encoder_raw = int(words[2])
            if sEncoderPrevious is None:
                sEncoderPrevious = encoder_raw

            # Track difference with turn-over adjustment
            if (sEncoderPrevious - encoder_raw) > 30000:
                sRoundCounter += (sOneRoundRaw - sEncoderPrevious)
                sEncoderPrevious = 0
            elif (encoder_raw - sEncoderPrevious) > 30000:
                sRoundCounter -= (sOneRoundRaw - encoder_raw)
                sEncoderPrevious = sOneRoundRaw

            diff = encoder_raw - sEncoderPrevious
            sRoundCounter += diff
            sEncoderPrevious = encoder_raw

            sRounds = sRoundCounter / sOneRoundRaw
            sDistance = round((sRounds * math.pi * 23), 2)
            rounds = round(sRounds, 2)

            # Print results
            print(
                f"{timestamp} | data_valid: {data_valid} | BaleNumber i/s: {(sBaleNumber, iBaleNumber)} | "
                f"sBaleReady: {sBaleReady} | iRamGoesForward: {iRamGoesForward} | EncoderDisRaw: {words[2]:04d} | "
                f"Rounds: {rounds} | Distance: {sDistance} | sRamdistance: {sRamdistance} | "
                f"StrokeLength: {sBaleLength_Stroke[:]} | qBaleNumber {state.BaleNumber} | "
                f"qBale_Length: {qBale_length_Encoder} | qStrokeLength {qBaleLength_Stroke[:]}"
            )

            # Store into SQLite
            insert_sample(
                ts=timestamp,
                data_valid=(data_valid == "YES"),
                bale_s=int(sBaleNumber) if sBaleNumber is not None else None,
                bale_i=int(iBaleNumber) if iBaleNumber is not None else None,
                bale_ready=bool(sBaleReady),
                ram_forward=bool(iRamGoesForward),
                encoder_raw=int(words[2]) if words and len(words) > 2 else None,
                rounds=float(rounds) if rounds is not None else None,
                distance=float(sDistance) if sDistance is not None else None,
                ram_distance=float(sRamdistance) if sRamdistance is not None else None,
                stroke_list=[float(x) for x in sBaleLength_Stroke],
                q_bale_number=int(qBaleNumber) if qBaleNumber is not None else None,
                q_bale_length=float(qBale_length_Encoder) if qBale_length_Encoder is not None else None,
                q_stroke_list=[float(x) for x in qBaleLength_Stroke],
            )

        time.sleep(POLL_INTERVAL)

    except Exception as e:
        # Never stop working: print error and continue.
        print("Main loop error:", e)
        time.sleep(1.0)
        continue
