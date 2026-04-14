# =============================================================================
# logger.py — CSV flight data logger (crash-safe)
# =============================================================================

import csv
import os
from datetime import datetime

from config import FLIGHT_DIR, CSV_HEADERS

_FILENAME = os.path.join(
    FLIGHT_DIR,
    f"flight_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
)


def init_log() -> str:
    """Create directory and write CSV header. Returns the CSV file path."""
    os.makedirs(FLIGHT_DIR, exist_ok=True)

    if not os.path.exists(_FILENAME) or os.path.getsize(_FILENAME) == 0:
        with open(_FILENAME, "w", newline="") as f:
            csv.writer(f).writerow(CSV_HEADERS)

    # Avoid non-ASCII glyphs to keep Windows console encodings happy.
    print(f"[Logger] CSV -> {_FILENAME}")
    return _FILENAME


def log_row(data: dict):
    """
    Append one row to the CSV and flush to disk immediately.
    On Windows, os.fsync() ensures data survives a crash.
    """
    row = [data.get(h) for h in CSV_HEADERS]
    with open(_FILENAME, "a", newline="") as f:
        csv.writer(f).writerow(row)
        f.flush()
        os.fsync(f.fileno())
