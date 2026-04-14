# =============================================================================
# altitude.py — Barometric altitude from pressure
# =============================================================================

from config import SEA_LEVEL_PRESSURE_HPA


def calc_altitude(pressure_hpa: float,
                  sea_level_hpa: float = SEA_LEVEL_PRESSURE_HPA) -> float | None:
    """
    Convert pressure (hPa) → altitude (metres) using the ISA barometric formula.

        altitude = 44330 * (1 - (P / P0) ^ 0.1903)

    Accurate to ±50 m below 12 km. Degrades above (±500 m at 30 km).
    Returns None if inputs are invalid.
    """
    if pressure_hpa is None or pressure_hpa <= 0:
        return None
    return round(44330.0 * (1.0 - (pressure_hpa / sea_level_hpa) ** 0.1903), 1)
