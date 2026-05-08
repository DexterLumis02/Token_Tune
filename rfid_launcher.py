import serial
import subprocess
import time
import psutil
import sys
import os

SERIAL_PORT = "COM3"
BAUDRATE = 115200

# Replace these with your actual card UIDs
ON_CARD = "AA BB CC DD"    # Example: turn ON GUI
OFF_CARD = "EE FF GG HH"   # Example: turn OFF GUI

process = None
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYER_FILE = os.path.join(BASE_DIR, "rfid_simple.py")

def pick_python_executable():
    candidates = []
    if os.name == "nt":
        candidates.extend([
            os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe"),
            os.path.join(BASE_DIR, "venv_gui", "Scripts", "python.exe"),
            os.path.join(BASE_DIR, "venv", "Scripts", "python.exe"),
        ])
    else:
        candidates.extend([
            os.path.join(BASE_DIR, ".venv", "bin", "python"),
            os.path.join(BASE_DIR, "venv_gui", "bin", "python"),
            os.path.join(BASE_DIR, "venv", "bin", "python"),
        ])

    for p in candidates:
        try:
            if p and os.path.exists(p):
                return p
        except Exception:
            pass
    return sys.executable

def is_running(proc):
    return proc and proc.poll() is None

def kill_process(proc):
    if proc and is_running(proc):
        proc.terminate()
        time.sleep(1)
        try:
            proc.kill()
        except Exception:
            pass

try:
    ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
    print("Listening for RFID cards...")
    while True:
        line = ser.readline().decode(errors="ignore").strip()
        if not line.startswith("Card UID:"):
            continue

        uid = line.replace("Card UID:", "").strip().upper()
        print("Detected UID:", uid)

        if uid == ON_CARD:
            if not is_running(process):
                print("🎵 Launching Music Player GUI...")
                #process = subprocess.Popen(["python", "rfid_simple.py"])
                process = subprocess.Popen([pick_python_executable(), PLAYER_FILE], cwd=BASE_DIR)

            else:
                print("GUI already running.")
        
        elif uid == OFF_CARD:
            print("🛑 Stopping Music Player GUI...")
            kill_process(process)
            process = None

        time.sleep(0.5)

except Exception as e:
    print("Error:", e)
