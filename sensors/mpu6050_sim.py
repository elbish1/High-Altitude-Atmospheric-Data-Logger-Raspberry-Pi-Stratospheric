# =============================================================================
# sensors/mpu6050_sim.py — Simulated MPU6050 (Accelerometer + Gyroscope)
#
# Simulates realistic motion data for a balloon flight:
#   - Gentle pendulum sway during ascent (gyro oscillation)
#   - Near-zero acceleration at burst (freefall)
#   - High-impact spike on landing
# =============================================================================

import math
import time
import random

_start_time      = None
_FLIGHT_DURATION = 7200


def init_mpu6050():
    global _start_time
    _start_time = time.time()
    print("[MPU6050 SIM] Initialised — simulating motion sensor.")


def read_mpu6050() -> dict:
    """
    Return simulated 6-axis motion data.

    At rest: accel_z ≈ 9.81 m/s² (gravity), gyro ≈ 0 °/s.
    During ascent: small pendulum-like gyro oscillation.
    At burst: accel drops to ~0 (brief freefall).
    On landing: large accel spike.
    """
    if _start_time is None:
        elapsed = 0.0
    else:
        elapsed = time.time() - _start_time

    progress = min(elapsed / _FLIGHT_DURATION, 1.0)
    noise    = lambda s: random.gauss(0, s)

    # Slow pendulum spin — balloon rotates gently during ascent
    spin_rate = 2.0 * math.sin(elapsed * 0.3)   # °/s, oscillates slowly

    # At burst (progress ~0.5) accel drops sharply toward 0
    if 0.48 < progress < 0.52:
        accel_z = noise(0.5)          # near-zero in freefall
    elif progress > 0.98:
        accel_z = 9.81 + abs(noise(8.0))   # hard landing impact
    else:
        accel_z = 9.81 + noise(0.15)        # normal — gravity dominant

    return {
        "accel_x": round(noise(0.05),   4),
        "accel_y": round(noise(0.05),   4),
        "accel_z": round(accel_z,       4),
        "gyro_x":  round(noise(0.2),    4),
        "gyro_y":  round(noise(0.2),    4),
        "gyro_z":  round(spin_rate + noise(0.1), 4),
    }
