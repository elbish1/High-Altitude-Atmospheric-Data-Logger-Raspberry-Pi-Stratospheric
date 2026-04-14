# High-Altitude Atmospheric Data Logger (HAB Payload) - Raspberry Pi Stratospheric Project

An **IoT high-altitude balloon (HAB) payload** that logs atmospheric + motion + GPS data to **CSV** and provides a **live ground-monitor GUI** (Windows simulation).  
Designed to be portable: the core loop stays the same, and you **swap simulated sensors for real Raspberry Pi sensor readers** when deploying.

---

## Project goals

- **Measure the atmosphere** during ascent/descent: temperature, pressure, humidity.
- **Track motion** (payload swing, burst/freefall, landing impact).
- **Track position** with GPS (latitude/longitude/altitude).
- **Log reliably to a CSV file** that survives crashes (flush + fsync).
- **Enable monitoring** via a real-time dashboard (Windows GUI in this repo).
- **Prepare for real flight deployment** on Raspberry Pi Zero 2 W with real sensors + LoRa telemetry.

---

## What’s in this repo (Windows simulation)

This folder is a **Windows simulation environment** that produces realistic flight-like data and files:

- **Sensor simulation** (BME280, MPU6050, GPS) that follows a realistic HAB flight profile
- **Crash-safe CSV logger** in `flight_data/`
- **Simulated camera** that writes PNG images to `photos/`
- Optional **Tkinter GUI dashboard** for live monitoring

> On real Raspberry Pi hardware, you keep `main.py` and the logging workflow, and replace the simulated sensor imports with real sensor readers.

---

## System architecture (concept)

**Payload (flight computer):**

- Raspberry Pi Zero 2 W  
- Sensors:
  - BME280 (Temp/Pressure/Humidity) via **I2C**
  - MPU6050 (Accel/Gyro) via **I2C**
  - u-blox NEO-6M (GPS) via **UART**
- Storage: MicroSD card (CSV logs + photos)
- Telemetry (planned): LoRa SX1276 via **SPI** to a ground station
- Power: Li-Po + boost converter to 5V, charging/protection module, insulation

**Ground station (concept):**

- LoRa receiver + computer for decoding/plotting and tracking

---

## Hardware list (from project PDF)

This is the recommended hardware stack for the real payload:

| # | Component | Role |
|---:|---|---|
| 1 | **Raspberry Pi Zero 2 W** | Flight computer (“brain”) |
| 2 | **BME280** | Temperature / Pressure / Humidity |
| 3 | **MPU6050** | 3-axis Accelerometer + Gyroscope (IMU) |
| 4 | **u-blox NEO-6M GPS** | Position & Altitude tracking (UART) |
| 5 | **LoRa SX1276 Ra-02 (433MHz)** | Long-range telemetry (SPI) |
| 6 | **Li-Po Battery** | Main power source |
| 7 | **MT3608 Boost Converter** | Step-up 3.7V → 5V |
| 8 | **TP4056 Charging Module** | Battery charging & protection |
| 9 | **MicroSD Card (32GB)** | OS + data logging storage |

### Important voltage notes (read before wiring)

- **BME280**: **3.3V only** (do **not** power from 5V).
- **LoRa SX1276 (Ra-02)**: **3.3V only** (5V can permanently damage the module).
- **MPU6050**: common GY-521 modules often accept 5V due to onboard regulation, but safest is **3.3V** unless your exact board is confirmed 5V-tolerant.

---

## Wiring overview (real Raspberry Pi deployment)

This repo is Windows simulation, but these are the typical Raspberry Pi interfaces you will use:

### I2C (BME280 + MPU6050 on the same bus)

- Raspberry Pi I2C pins: **SDA (GPIO2)**, **SCL (GPIO3)**, **3.3V**, **GND**
- **BME280 I2C address**: `0x76` or `0x77` (depends on SDO pin)
- **MPU6050 I2C address**: `0x68` or `0x69` (depends on AD0 pin)

### UART (GPS NEO-6M)

- GPS TX → Raspberry Pi RX (UART)
- GPS RX → Raspberry Pi TX (UART)
- Set baud rate typically **9600**

> Note from the hardware guide: GPS must be configured for **Airborne Mode** if you expect operation above ~18 km.

### SPI (LoRa SX1276)

- LoRa uses SPI (SCK, MOSI, MISO, CS) + extra pins (RST, DIO0 depending on library)

---

## Software workflow (how the code runs)

### 1) Start up

- Create `flight_data/` if missing
- Initialize sensor drivers (in this repo: **simulators**)
- Initialize simulated camera (`photos/`)
- Create a new timestamped CSV file and write the header

### 2) Main loop (every `LOOP_INTERVAL` seconds)

- Read BME280 → temperature/pressure/humidity
- Read MPU6050 → accel/gyro
- Read GPS → lat/lon/alt/fix/satellites
- Compute **barometric altitude** from pressure
- Append one row to CSV (**flush + fsync**)
- Optionally capture an image every `PHOTO_INTERVAL`
- If GUI is enabled, update a shared state dict for the dashboard

### 3) Shutdown

- Ctrl+C stops cleanly and closes GPS/camera handlers

---

## Data format (CSV output)

CSV files are written into `flight_data/` as:

- `flight_YYYY-MM-DD_HH-MM-SS.csv`

Header columns (see `config.py`):

- `timestamp`
- `temperature_c`, `pressure_hpa`, `humidity_pct`
- `altitude_baro_m` (computed)
- `accel_x`, `accel_y`, `accel_z`
- `gyro_x`, `gyro_y`, `gyro_z`
- `lat`, `lon`, `alt_gps_m`, `gps_fix`, `satellites`

### Barometric altitude formula

The code uses the ISA barometric approximation:

\[
\text{altitude} = 44330 \times \left(1 - \left(\frac{P}{P_0}\right)^{0.1903}\right)
\]

Where:

- \(P\) is measured pressure (hPa)
- \(P_0\) is sea-level reference pressure (default: 1013.25 hPa)

> Accuracy is best at lower altitudes and degrades in the stratosphere, but it remains useful for trend/shape of flight.

---

## Run on Windows (simulation)

### Prerequisites

- **Python 3.10+** recommended
- No external dependencies required for simulation (uses Python stdlib only)

### Run headless (console + CSV)

```bash
python main.py
```

### Run with GUI dashboard

```bash
python main.py --gui
```

### Outputs you should see

- New CSV created in `flight_data/`
- `system.log` for warnings/errors
- New fake images created in `photos/` every `PHOTO_INTERVAL` seconds

---

## Moving from Windows SIM → Real Raspberry Pi (deployment checklist)

### 1) Replace simulated sensor modules

In `main.py`, these lines are the “swap point”:

- `from sensors.bme280_sim import ...`
- `from sensors.mpu6050_sim import ...`
- `from sensors.gps_sim import ...`

On the Raspberry Pi, replace them with real sensor readers (I2C + UART) while keeping:

- `_collect()`
- `sensor_loop()`
- `logger.py` CSV writing
- GUI (optional; typically ground station runs GUI instead)

### 2) Install Raspberry Pi dependencies (typical)

The file `requirements_windows.txt` lists suggested packages for real Pi usage, e.g.:

- BME280: `adafruit-circuitpython-bme280` + `adafruit-blinka`
- GPS UART: `pyserial`, `pynmea2`
- Camera: `picamera2`

### 3) GPS airborne mode

Ensure the GPS is configured for **Airborne Mode** before flight (per hardware guide), otherwise it may stop reporting above ~18 km due to COCOM limits.

### 4) Power + insulation

At high altitude, cold temperatures reduce effective Li-Po capacity. Use insulation and verify:

- stable 5V rail for Pi
- 3.3V-only modules protected from 5V

---

## Troubleshooting

- **No GPS data at start (SIM)**: expected for the first ~45 seconds (cold start simulation).
- **CSV not updating**: check `flight_data/system.log` for write errors.
- **GUI is frozen**: run `python main.py --gui` (Tkinter must run on the main thread on Windows).
- **LoRa module not working on real hardware**: double-check it is powered with **3.3V**, SPI wiring, and antenna connection.

---

## Folder structure

- `main.py`: entry point (headless or `--gui`)
- `config.py`: timing, folders, and CSV columns
- `logger.py`: crash-safe CSV writer
- `altitude.py`: barometric altitude calculator
- `camera.py`: Windows simulated camera (writes minimal PNGs)
- `gui.py`: Tkinter ground monitor + graphs + credits page
- `sensors/`: simulated sensor modules
- `flight_data/`: generated CSV logs + `system.log`
- `photos/`: generated images (created at runtime)

---

## Credits & acknowledgements

### Course / Institution

- **Course**: INTERNET OF THINGS (CCS 329)
- **Institution**: Al Ryada University for Science and Technology  
- **Faculty**: Faculty of Computers and Artificial Intelligence  
- **Group**: S1  
- **Semester**: Spring 2025–2026  

### Submitted to

- **Dr. Eman Salah** - with sincere appreciation for her guidance, feedback, and support.

### Team members

Shoutout to the team who designed, implemented, tested, and documented this project:

1. Yousef Amr Abdelazeem Elbish
   LinkedIn: https://linkedin.com/in/elbish1
   Portfolio: https://yousef-elbish.vercel.app  
2. Noor Mohamed Elmansy
   LinkedIn: https://www.linkedin.com/in/noor-elmansy-309b99313
   Portfolio: https://noor-portofolio.netlify.app  
3. Fatma Mohamed Soliman
   LinkedIn: https://www.linkedin.com/in/fatma-mohamed-b5982029
   Portfolio: https://cute-twilight-78cf35.netlify.app/  
4. Ahmed Kamel Hassanin
   LinkedIn: https://www.linkedin.com/in/ahmed-kamel-4b161828a  
5. Abanoub Amir George
   LinkedIn: https://www.linkedin.com/in/abanoub-amir-6a1b512a3  
6. Nada Wesam Alhlwany
   LinkedIn: https://www.linkedin.com/in/nada-wesam  
7. Sohaila Adel Nassar
   LinkedIn: https://www.linkedin.com/in/sohaila-adel-2b01502b8  
8. Mahmoud Abdelghany Depian
   LinkedIn: https://www.linkedin.com/in/mahmoud-depian  
9. Adham Sameh
   LinkedIn: https://www.linkedin.com/in/adham-sameh-8b2a6b378  
10. Ola Zaher Mohamed
    LinkedIn: https://www.linkedin.com/in/ola-zaher  
11. Mohamed Abdallah Mohamed (ID: 2301202)  

---

## License

Educational / academic project. If you need an explicit open-source license file, add `LICENSE` (MIT/Apache-2.0/etc.) depending on your course policy.

