# Industrial IoT Ball Bearing Production Simulation

This project is a Python-based software simulation of a parallelized ball bearing manufacturing line. It incorporates an Industrial Internet of Things (IIoT) architecture by streaming real-time production telemetry to a containerized InfluxDB and Grafana stack, providing a true SCADA-level dashboard experience.

## System Architecture

The project is divided into three distinct operational layers:

1.  **The Edge Device (Python Backend):** The `bearing_production.py` script acts as the machine controller. It utilizes multi-threading to parallelize the manufacturing of four distinct components (outer ring, inner ring, steel balls, and cage). It includes hardcoded stochastic defect rates, Quality Control (QC) stations, and a final assembly/packaging process.
2.  **The Historian (InfluxDB via Docker):** A containerized time-series database optimized for high-frequency sensor data. A background telemetry thread in the Python script samples the machine state every second and pushes it synchronously to the database.
3.  **The SCADA Dashboard (Grafana via Docker):** A containerized analytical dashboard that connects directly to InfluxDB. It visualizes total units shipped, reject counts, simulated temperature, and the chronological machine state (Running, E-Stop, Soft Halt).

## Features

* **True Parallel Manufacturing:** Components are produced in independent threads rather than sequentially.
* **Hardware-Level Interrupts:** Utilizes the Windows `msvcrt` library for instantaneous keyboard polling, allowing for true, non-blocking Emergency Stops (E-Stops) and Soft Halts.
* **Decoupled Telemetry:** The database communication runs on a separate daemon thread, ensuring network latency does not bottleneck the physical manufacturing simulation.
* **Auto-Provisioned Infrastructure:** A single `docker-compose.yml` file handles the complete setup of the database and dashboard, including initial buckets, organizations, and authentication tokens.

## Prerequisites

To run this simulation, you will need:

* **Python 3.9+** (Must be run on a Windows machine due to the `msvcrt` library requirement for hardware interrupts).
* **Docker Desktop** (For running the database and dashboard containers).

## Installation & Setup

### 1. Start the IIoT Infrastructure
Navigate to the project root directory where the `docker-compose.yml` file is located and start the containers in the background:
```bash
docker-compose up -d
```
*Note: This will automatically provision an InfluxDB bucket named `factory` and an organization named `srh_university`.*

### 2. Install Python Dependencies
Install the required InfluxDB Python client:
```bash
pip install influxdb-client
```

### 3. Configure Grafana Dashboard
1. Open a browser and navigate to `http://localhost:3000`.
2. Log in using the credentials defined in the Docker compose file (Default: User: `admin` | Pass: `srh_admin_2026!`).
3. Add **InfluxDB** as a new data source using the Flux query language.
   * **URL:** `http://influxdb:8086`
   * **Organization:** `srh_university`
   * **Token:** `srh-secret-token-2026`
   * **Default Bucket:** `factory`
4. Build your visual panels (Stat counters for shipped/rejects, State Timeline for machine status).

## Usage

Start the production simulation by running the main Python script:
```bash
python bearing_production.py
```

### Controls
While the script is running, you can interact with the machine state instantly using your keyboard (no need to press Enter):

* `[R]` - **Resume / Start:** Begins or resumes parallel production.
* `[S]` - **Soft Halt:** Signals the machine to finish assembling the current bearing in progress before pausing gracefully.
* `[E]` - **Emergency Stop:** Instantly freezes all production threads.
* `[Q]` - **Quit:** Gracefully shuts down the simulation and the telemetry thread.

## License
This project was developed for the Advanced Programming / Applied Mechatronics course at SRH University of Applied Sciences Heidelberg.
