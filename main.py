#!/usr/bin/env python3
# =============================================================================
# main.py — HAB Data Logger  (Windows simulation mode)
#
# USAGE (in PyCharm or CMD):
#   python main.py          ← headless, no window, just console + CSV
#   python main.py --gui    ← opens live Tkinter dashboard
#
# All hardware is simulated. Real balloon flight physics are modelled so
# the CSV data looks realistic. When you move this to a Raspberry Pi, you
# swap the three sim imports for the real sensor readers — nothing else changes.
# =============================================================================

import sys
import time
import signal
import logging
import threading
import os
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
from config import LOOP_INTERVAL, PHOTO_INTERVAL, LOG_FILE, FLIGHT_DIR

os.makedirs(FLIGHT_DIR, exist_ok=True)

# ── System logger (errors → system.log, not the flight CSV) ──────────────────
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# ── Sensor imports — SWAP THESE when moving to a real Raspberry Pi ────────────
#
#   Windows (simulation):          Real Pi:
#   ─────────────────────────────  ──────────────────────────────────────────
from sensors.bme280_sim  import init_bme280,  read_bme280   # → bme280_reader
from sensors.mpu6050_sim import init_mpu6050, read_mpu6050  # → mpu6050_reader
from sensors.gps_sim     import init_gps,     read_gps, close_gps  # → gps_reader

from altitude import calc_altitude
from logger   import init_log, log_row
from camera   import init_camera, capture_image, close_camera

# ── Shared state (sensor thread ↔ GUI thread) ─────────────────────────────────
shared_data = {}
data_lock   = threading.Lock()
_running    = True

SHOW_GUI = "--gui" in sys.argv


# =============================================================================
# Graceful shutdown
# =============================================================================

def _shutdown(sig, frame):
    global _running
    print("\n[Main] Shutting down...")
    _running = False
    close_gps()
    close_camera()
    sys.exit(0)

signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


# =============================================================================
# Collect all sensor data into one dict
# =============================================================================

def _collect() -> dict:
    """
    Read every sensor. Any failure → None values for that sensor.
    The loop never crashes because of a single bad sensor read.
    """
    data = {"timestamp": datetime.now().isoformat()}

    # BME280 — temperature, pressure, humidity
    try:
        data.update(read_bme280())
    except Exception as e:
        logging.warning(f"BME280 failed: {e}")
        data.update({"temperature_c": None, "pressure_hpa": None, "humidity_pct": None})

    # MPU6050 — accelerometer, gyroscope
    try:
        data.update(read_mpu6050())
    except Exception as e:
        logging.warning(f"MPU6050 failed: {e}")
        data.update({k: None for k in
                     ["accel_x","accel_y","accel_z","gyro_x","gyro_y","gyro_z"]})

    # GPS — position, altitude, fix status
    try:
        data.update(read_gps())
    except Exception as e:
        logging.warning(f"GPS failed: {e}")
        data.update({"lat": None, "lon": None,
                     "alt_gps_m": None, "gps_fix": False, "satellites": 0})

    # Barometric altitude derived from pressure
    data["altitude_baro_m"] = calc_altitude(data.get("pressure_hpa"))

    return data


# =============================================================================
# Main sensor loop
# =============================================================================

def sensor_loop():
    # ── Init hardware (or simulators) ─────────────────────────────────────────
    print("[Main] Initialising sensors...")
    for fn, name in [(init_bme280,  "BME280"),
                     (init_mpu6050, "MPU6050"),
                     (init_gps,     "GPS")]:
        try:
            fn()
        except Exception as e:
            logging.error(f"{name} init failed: {e}")
            print(f"[Main] WARNING: {name} unavailable - {e}")

    camera_ok = init_camera()
    csv_path  = init_log()

    print(f"\n[Main] Loop: every {LOOP_INTERVAL}s  |  Photo: every {PHOTO_INTERVAL}s")
    print(f"[Main] CSV  -> {csv_path}")
    print(f"[Main] Press Ctrl+C to stop.\n")
    print(f"  {'Time':12}  {'Baro Alt':>10}  {'GPS Alt':>10}  "
          f"{'Temp':>8}  {'Pressure':>10}  {'Fix'}")
    print("  " + "-" * 68)

    last_photo = 0.0

    while _running:
        t0   = time.time()
        data = _collect()

        # Write to CSV
        try:
            log_row(data)
        except Exception as e:
            logging.error(f"CSV write failed: {e}")

        # Camera capture on interval
        if camera_ok and (time.time() - last_photo >= PHOTO_INTERVAL):
            path = capture_image(altitude_m=data.get("altitude_baro_m"))
            if path:
                print(f"  [CAM] -> {os.path.basename(path)}")
            last_photo = time.time()

        # Push to GUI shared dict
        with data_lock:
            shared_data.update(data)

        # Console heartbeat — one line per loop
        alt_b = data.get("altitude_baro_m")
        alt_g = data.get("alt_gps_m")
        temp  = data.get("temperature_c")
        pres  = data.get("pressure_hpa")
        fix   = "YES" if data.get("gps_fix") else "NO "
        ts    = data["timestamp"][11:23]   # HH:MM:SS.ms

        print(
            f"  {ts}  "
            f"{str(alt_b) + ' m':>10}  "
            f"{str(alt_g) + ' m':>10}  "
            f"{str(temp) + ' °C':>8}  "
            f"{str(pres) + ' hPa':>10}  "
            f"{fix}"
        )

        # Sleep only what's left of LOOP_INTERVAL
        elapsed = time.time() - t0
        sleep   = LOOP_INTERVAL - elapsed
        if sleep > 0:
            time.sleep(sleep)
        else:
            logging.warning(f"Loop overran by {-sleep:.3f}s")


# =============================================================================
# Entry point
# =============================================================================

def main():
    if SHOW_GUI:
        # Sensor loop → background thread
        # Tkinter GUI  → main thread  (required by Tkinter on Windows)
        import tkinter as tk
        from gui import BalloonDashboard

        t = threading.Thread(target=sensor_loop, daemon=True, name="SensorLoop")
        t.start()

        root = tk.Tk()
        BalloonDashboard(root, shared_data, data_lock)
        root.mainloop()
    else:
        sensor_loop()


if __name__ == "__main__":
    main()
