# =============================================================================
# sensors/bme280_sim.py — Simulated BME280 (Temperature, Pressure, Humidity)
#
# Simulates a real balloon flight:
#   - Balloon rises for the first half of the simulation
#   - Pressure drops as altitude increases (physically accurate)
#   - Temperature drops into negatives as it climbs (stratosphere behaviour)
#   - Humidity drops to near 0% at high altitude
#
# On a real Pi this file is replaced by bme280_reader.py which talks to
# the actual sensor over I2C.
# =============================================================================

import math
import time
import random

# Simulation state — shared across calls to mimic a real flight profile
_start_time = None
_FLIGHT_DURATION = 7200   # simulate a 2-hour flight (seconds)
_MAX_ALTITUDE    = 32000  # metres — realistic HAB peak


def init_bme280():
    """Record the simulation start time. Call once at startup."""
    global _start_time
    _start_time = time.time()
    print("[BME280 SIM] Initialised — simulating atmospheric sensor.")


def _flight_fraction() -> float:
    """
    Returns a value 0.0 → 1.0 → 0.0 representing the balloon's
    position in the flight arc (ascent → burst → descent).
    """
    if _start_time is None:
        return 0.0
    elapsed  = time.time() - _start_time
    progress = min(elapsed / _FLIGHT_DURATION, 1.0)   # 0.0 at launch, 1.0 at end

    # Triangle wave: rises to 1.0 at midpoint, falls back to 0.0
    if progress < 0.5:
        return progress * 2          # 0.0 → 1.0  (ascent)
    else:
        return (1.0 - progress) * 2  # 1.0 → 0.0  (descent)


def read_bme280() -> dict:
    """
    Return simulated atmospheric readings.

    Altitude drives all other values via physically accurate relationships:
      - Pressure  : barometric formula (decreases exponentially with altitude)
      - Temperature: ISA lapse rate −6.5 °C/km in troposphere, then −55 °C plateau
      - Humidity  : drops off sharply above the tropopause (~12 km)
    """
    frac     = _flight_fraction()
    altitude = frac * _MAX_ALTITUDE   # metres

    # Pressure from barometric formula (inverse of altitude calculation)
    pressure = 1013.25 * ((1 - altitude / 44330.0) ** (1 / 0.1903))
    pressure = max(pressure, 1.0)   # floor at 1 hPa — sensor would read near 0

    # Temperature: −6.5 °C per 1000 m up to 11 km, then plateau at −56.5 °C
    if altitude <= 11000:
        temperature = 15.0 - (6.5 * altitude / 1000.0)
    else:
        temperature = -56.5

    # Humidity: 60% at ground, drops to ~0% above 15 km
    humidity = max(0.0, 60.0 * (1 - altitude / 15000.0))

    # Add small random noise (sensor always has some noise)
    noise = lambda scale: random.gauss(0, scale)

    return {
        "temperature_c": round(temperature + noise(0.1),  2),
        "pressure_hpa":  round(pressure    + noise(0.05), 2),
        "humidity_pct":  round(max(0.0, humidity + noise(0.5)), 2),
    }
