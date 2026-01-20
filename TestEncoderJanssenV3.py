from pymodbus.client import ModbusTcpClient
from datetime import datetime
import time
import math
from Modbus_TCPV3 import state
from db import init_db, insert_sample

MASTER_IP = "192.168.1.250"
MODBUS_PORT = 502
PDIN_BASE_ADDR = 0   
WORD_COUNT = 16      

# Baler variables from PLC
iBaleNumber = 0 # must have
iRamGoesForward = None # must have

client = ModbusTcpClient(MASTER_IP, port=MODBUS_PORT)
if not client.connect():
    print("Failed to connect to TBEN-S2-4IOL")
    time.sleep(5)

# Initialize variables
sBaleNumber = 0 
sReading = True
sBaleReady = False
sPreviousRamGoesForward = False
sLast_angle = None
sRounds = None
sRoundCounter = 0
sEncoderPrevious = None 
sOneRoundRaw = 35999.0
sEncoder_raw = 0
sDistance = 0.0
sBaleLength_Stroke = [0] * 10 # RAM to store bale lengths
sBale_length_Encoder = 0.0
sRounds_Encoder = 0.0
sRamdistance = 0.0

qBaleNumber = None
qBale_length_Encoder = 0
qBaleLength_Stroke = [0] * 10

init_db()

# Main loop
try:
    while True:

        sBaleNumber = iBaleNumber if sBaleNumber is 0 else sBaleNumber


        # Baler variables from PLC
        iBaleNumber = state.BaleNumber if not 0 else None # must have
        iRamGoesForward = state.RamGoesForward

        if iBaleNumber != sBaleNumber and sBaleNumber is not 0:
            sBaleReady = True
        else:
            sBaleReady = False
        
        # Read Bale status from PLC
        if sBaleReady == True and iBaleNumber > 0:
            print("Bale is ready")
            print(f"sBaleReady: {sBaleReady}")
            sBale_length_Encoder = sDistance
            qBale_length_Encoder = sDistance
            sRounds_Encoder = round(sRounds, 2)
            qBaleLength_Stroke[0] = sBaleLength_Stroke[0]
            qBaleLength_Stroke[1] = sBaleLength_Stroke[1]
            qBaleLength_Stroke[2] = sBaleLength_Stroke[2]
            qBaleLength_Stroke[3] = sBaleLength_Stroke[3]
            qBaleLength_Stroke[4] = sBaleLength_Stroke[4]
            qBaleLength_Stroke[5] = sBaleLength_Stroke[5]
            qBaleLength_Stroke[6] = sBaleLength_Stroke[6]
            qBaleLength_Stroke[7] = sBaleLength_Stroke[7]
            qBaleLength_Stroke[8] = sBaleLength_Stroke[8]
            qBaleLength_Stroke[9] = sBaleLength_Stroke[9]
            sBaleLength_Stroke = [0] * 10 # Clear RAM for next bale
            qBaleNumber = sBaleNumber
            sBaleNumber = iBaleNumber
            sReading = False
            sRoundCounter = 0
            sDistance = 0.0
            sRamdistance = 0.0
            sRounds = 0.0
            
            
        elif sBaleReady == False:
            sReading = True
            # print("Bale not ready, started reading")

        if sReading == True:
            result = client.read_input_registers(address=PDIN_BASE_ADDR, count=WORD_COUNT)
            if not result or not hasattr(result, "registers"):
                print("Failed to read registers")
                time.sleep(5)
                continue

            

            if (iRamGoesForward == True and sPreviousRamGoesForward == False): # Rising edge
               sRamGoesForward = True 
               sPreviousRamGoesForward = iRamGoesForward 
            elif (iRamGoesForward == False and sPreviousRamGoesForward == True): # Falling edge
                    sPreviousRamGoesForward = iRamGoesForward 
                    sRamGoesForward = False
                    if sBaleNumber == iBaleNumber:
                        print("Set ram distance")
                        time.sleep(3)  # wait for ram to stop
                        sRamdistance = sDistance - sBaleLength_Stroke[0] - sBaleLength_Stroke[1] - sBaleLength_Stroke[2] - sBaleLength_Stroke[3] - sBaleLength_Stroke[4] - sBaleLength_Stroke[5] - sBaleLength_Stroke[6] - sBaleLength_Stroke[7] - sBaleLength_Stroke[8] - sBaleLength_Stroke[9]
                        sRamdistance = round(sRamdistance, 2)
                        for i in range(10):
                            if sBaleLength_Stroke[i] == 0:
                                sBaleLength_Stroke[i] = round(sRamdistance, 2)
                                break  # exit after placing the distance
                    
            

            # Read registers but do not process
            words = result.registers  # list of 16 words
            # Set time
            timestamp = datetime.now()

            # Word0: DI Input
            di_input = "ON" if words[0] != 0 else "OFF"

            # Word1: Data Valid
            data_valid = "YES" if words[1] != 0 else "NO"

            # Word2 = Encoder raw position
            encoder_raw = int(words[2]) # 16-bit encoder
            if sEncoderPrevious == None:
                sEncoderPrevious = encoder_raw

            # Track difference with turn over adjusment
            if sEncoderPrevious - encoder_raw > 30000:
                sRoundCounter += sOneRoundRaw - sEncoderPrevious
                sEncoderPrevious = 0
            elif encoder_raw - sEncoderPrevious > 30000:
                sRoundCounter -= sOneRoundRaw - encoder_raw
                sEncoderPrevious = sOneRoundRaw
            # track difference
            diff = encoder_raw - sEncoderPrevious
            sRoundCounter += (diff)
            sEncoderPrevious = encoder_raw
                
            # Calculate angle
            angle_deg = (encoder_raw / sOneRoundRaw) * 360.0  


            if sRounds == None:
                sRounds = 0.0

            sRounds = sRoundCounter / sOneRoundRaw    
            sDistance = round((sRounds * math.pi * 23),2)
            rounds = round(sRounds, 2)

            # Print results
            print(f"{timestamp} | data_valid: {data_valid} | BaleNumber i/s: {sBaleNumber, iBaleNumber} | sBaleReady: {sBaleReady} | iRamGoesForward: {iRamGoesForward} | EncoderDisRaw: {words[2]:04d} |" 
                f" Rounds: {rounds} | Distance: {sDistance} | sRamdistance: {sRamdistance} | StrokeLength: {sBaleLength_Stroke[:]} | qBaleNumber {state.BaleNumber} | qBale_Length: {qBale_length_Encoder} | qStrokeLength {qBaleLength_Stroke[:]}")

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

        time.sleep(0.1)
finally:
    client.close()
