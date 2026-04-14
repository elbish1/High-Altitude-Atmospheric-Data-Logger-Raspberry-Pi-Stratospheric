# =============================================================================
# config.py — Central configuration for HAB Data Logger (Windows simulation)
# =============================================================================

import os

# --- Timing ---
LOOP_INTERVAL  = 1.0    # seconds between sensor reads
PHOTO_INTERVAL = 10.0   # seconds between fake camera captures

# --- Paths (Windows-safe using os.path) ---
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
FLIGHT_DIR = os.path.join(BASE_DIR, "flight_data")
PHOTO_DIR  = os.path.join(BASE_DIR, "photos")
LOG_FILE   = os.path.join(FLIGHT_DIR, "system.log")

# --- Pressure reference ---
SEA_LEVEL_PRESSURE_HPA = 1013.25

# --- CSV columns ---
CSV_HEADERS = [
    "timestamp",
    "temperature_c",
    "pressure_hpa",
    "humidity_pct",
    "altitude_baro_m",
    "accel_x", "accel_y", "accel_z",
    "gyro_x",  "gyro_y",  "gyro_z",
    "lat", "lon",
    "alt_gps_m",
    "gps_fix",
    "satellites",
]
