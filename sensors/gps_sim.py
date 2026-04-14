# =============================================================================
# sensors/gps_sim.py — Simulated GPS (Lat, Lon, Altitude, Fix)
#
# Simulates a balloon drifting east with the jetstream from a launch site
# in Egypt. GPS fix is unavailable for the first 45 seconds (cold start).
# =============================================================================

import math
import time
import random

_start_time      = None
_FLIGHT_DURATION = 7200

# Launch site: Cairo area
_LAUNCH_LAT = 30.0444
_LAUNCH_LON = 31.2357


def init_gps():
    global _start_time
    _start_time = time.time()
    print("[GPS SIM] Initialised — simulating UART GPS receiver.")
    print("[GPS SIM] Note: GPS fix unavailable for first 45 seconds (cold start).")


def read_gps() -> dict:
    """
    Return simulated GPS data.

    - No fix for first 45 seconds (realistic cold-start delay)
    - Balloon drifts east at ~80 km/h (jetstream)
    - GPS altitude tracks barometric altitude with small offset
    """
    if _start_time is None:
        elapsed = 0.0
    else:
        elapsed = time.time() - _start_time

    # No fix during cold start
    if elapsed < 45:
        return {
            "lat":       None,
            "lon":       None,
            "alt_gps_m": None,
            "gps_fix":   False,
            "satellites": 0,
        }

    progress = min(elapsed / _FLIGHT_DURATION, 1.0)

    # Flight arc altitude
    frac     = (1 - abs(2 * progress - 1))   # triangle: 0→1→0
    altitude = frac * 32000

    # Drift: balloon moves east ~80 km/h = 0.000222° lon per second
    drift_lon = elapsed * 0.000222
    # Small northward drift
    drift_lat = elapsed * 0.000015

    noise = lambda s: random.gauss(0, s)

    return {
        "lat":        round(_LAUNCH_LAT + drift_lat + noise(0.00001), 6),
        "lon":        round(_LAUNCH_LON + drift_lon + noise(0.00001), 6),
        "alt_gps_m":  round(altitude + noise(5.0), 1),
        "gps_fix":    True,
        "satellites": random.randint(7, 12),
    }


def close_gps():
    print("[GPS SIM] Closed.")
