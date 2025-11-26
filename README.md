# RangePlotter

**Simple large-radius viewshed and visibility  analysis**

RangePlotter is a command line, python-based geospatial utility designed to calculate accurate large-radius sensor coverage maps for visualisation in an appropriate viewer (such as Google Earth). Unlike pure geometric tools, RangePlotter integrates high-resolution (30m) global terrain data (Copernicus GLO-30) to determine exactly where a sensor can see, accounting for Earth curvature, atmospheric refraction, and terrain masking (viewsheds).

## Use Cases

*   **Radar Network Visualisation**: Optimize site selection by visualizing coverage gaps and terrain shadowing.
*   **Telecommunications**: Analyze line-of-sight for microwave links or radio towers.
*   **Gap Analysis**: Identify blind spots in existing sensor networks.

---

## Quick Start Guide

1. Install
2. Connect your (free) Copernicus account
3. Provide a .kml file (e.g. exported from Google Earth) with one or more placemarks
4. Run './rangeplotter viewshed' to calculate the viewshed around your placemark
5. Import the output .kml file to Google Earth to see your viewshed

See below for lots more detail...

---

## Installation

### Option 1: Standalone Binary (Recommended for Linux Users)
No Python environment required.

1.  **Download** the latest release archive (`rangeplotter_vX.Y.Z_linux.zip`) from the [GitHub Releases page](https://github.com/renwell-studio/rangeplotter/releases).
2.  **Unzip** the archive:
    ```bash
    unzip rangeplotter_vX.Y.Z_linux.zip
    cd rangeplotter_vX.Y.Z_linux
    ```
3.  **Install / Upgrade**:
    Run the included script to set up the executable and preserve your existing configuration if upgrading:
    ```bash
    chmod +x install_or_upgrade.sh
    ./install_or_upgrade.sh
    ```
    *This script will make `rangeplotter` executable and ensure your `config/` and `working_files/` are safe.*

4.  **Run**:
    ```bash
    ./rangeplotter --help
    ```

### Option 2: Python Wheel (Cross-Platform / Advanced)
For users who have Python installed (Linux, macOS, Windows) and prefer using `pip`.

1.  **Download** the `.whl` file from the [GitHub Releases page](https://github.com/renwell-studio/rangeplotter/releases).
2.  **Install**:
    ```bash
    pip install rangeplotter-0.1.5-py3-none-any.whl
    ```
3.  **Run**:
    ```bash
    rangeplotter --help
    ```

### Option 3: Python Source (For Developers)
1.  Clone the repository:
    ```bash
    git clone https://github.com/renwell-studio/rangeplotter.git
    cd rangeplotter
    ```
2.  Set up environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
    ```
3.  Run via module:
    ```bash
    python -m rangeplotter.cli.main --help
    ```

---

## Credentials (Copernicus DEM)

RangePlotter automatically downloads terrain data from the **Copernicus Data Space Ecosystem (CDSE)**. You need a free account to access this data.

### Step 1: Register
Create a free account at [dataspace.copernicus.eu](https://dataspace.copernicus.eu/).

### Step 2: Configure Credentials
You have two options for providing credentials. We recommend **Option B** (Refresh Token) for security, as it avoids storing your password in plain text.

#### Option A: Username & Password (Simplest)
Create a `.env` file in the folder where you run the tool:
```bash
COPERNICUS_USERNAME=your_email@example.com
COPERNICUS_PASSWORD=your_password
```

#### Option B: Refresh Token (Secure)
1.  Create a temporary `.env` file with your username and password as above.
2.  Run the helper command to generate a long-lived refresh token:
    ```bash
    ./rangeplotter extract-refresh-token
    ```
3.  Copy the output line starting with `COPERNICUS_REFRESH_TOKEN=...`.
4.  Update your `.env` file to remove your password and paste the token:
    ```bash
    COPERNICUS_USERNAME=your_email@example.com
    COPERNICUS_REFRESH_TOKEN=eyJhbGciOiJIUz... (long string)
    ```

---

## ⚡ Workflow Guide

### 1. Prepare Input
Place your radar sites in a KML file (e.g., `working_files/input/my_radars.kml`).
*   **Format**: Standard Google Earth KML.
*   **Content**: `Placemark` points. The name of the placemark will be used as the sensor name.

### 2. Calculate Geometric Horizon (Optional)
Generate theoretical range rings (smooth earth) to verify maximum line of sight over open water.
```bash
./rangeplotter horizon
```

### 3. Calculate Terrain Viewshed (Primary)
Compute the actual visibility. This downloads DEM tiles, reprojects them, and performs terrain-aware line-of-sight analysis to targets at any given altitude.
```bash
./rangeplotter viewshed
```
*   **Output**: `working_files/viewshed/viewshed-[SiteName]-tgt_alt_[Alt]m.kml`

### 4. Apply Detection Ranges
Clip the raw viewsheds to specific instrumented ranges (e.g., 100km, 200km) and merge overlapping coverage from multiple sensor locations.
```bash
./rangeplotter detection-range --range 150,300
```
*   **Output**: `working_files/detection_range/`

---

## Configuration

Most behaviours and settings are controlled by `config/config.yaml`. Key settings include:

| Setting | Description | Default |
| :--- | :--- | :--- |
| `input_dir` | Directory to scan for KML inputs. | `working_files/input` |
| `altitudes_msl_m` | List of target altitudes (meters) for viewshed analysis. | `[2, 10, ...]` |
| `target_altitude_reference` | Altitude mode: `msl` (absolute) or `agl` (relative to terrain). | `msl` |
| `sensor_height_m_agl` | Height of the sensor above ground (meters). | `5.0` |
| `atmospheric_k_factor` | Refraction coefficient (1.333 = 4/3 Earth radius). | `1.333` |
| `detection_ranges` | List of max ranges (km) for `detection-range` clipping. | `[50, 100, 200]` |
| `simplify_tolerance_m` | Polygon simplification (higher = smaller files). | `5.0` |

---

## Tech Stack & Methodology

RangePlotter is built on a robust open-source geospatial stack:
*   **Core Engine**: Python 3.12+
*   **Geospatial Processing**: `Rasterio` (GDAL), `Shapely`, `PyProj`.
*   **Terrain Data**: Automatic fetching and caching of **Copernicus GLO-30 DEM** (30m global resolution).
*   **Physics**:
    *   **Adjustable Earth Equivalent Radius Model**: Accounts for atmospheric refraction.
    *   **Azimuthal Equidistant Projection**: Automatically centers calculations on each sensor for high-precision distance measurements.

---

## Bugs & Feature Requests

Please report issues via the [GitHub Issue Tracker](https://github.com/renwell-studio/rangeplotter/issues).
*   **Bugs**: Include the command run, error output, log contents and a sample KML if possible.
*   **Features**: Describe the use case and desired output.

---

## Credit & Support

Developed by **Renwell Studio**.
*   If you find this tool useful or interesting, please consider supporting development.
*   **Donations**: [ko-fi](ko-fi.com/renwell)

---

## License

Distributed under the **MIT License**. See `LICENSE` for more information.

**Note on Third-Party Dependencies:**
This project uses `fastkml` and `simplekml`, which are licensed under the **LGPL**.
- If you modify these libraries and redistribute this application, you must comply with the LGPL terms (e.g., allowing users to replace the modified library).
- As this project is open source, the source code is available for users to rebuild the application with their own versions of these dependencies.

---

## Troubleshooting
- Slow performance: reduce altitudes, adjust multiscale in config or adjust the CPU and RAM usage guards in config.