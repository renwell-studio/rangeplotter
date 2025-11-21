# RangePlotter

**Advanced Sensor Line-of-Sight & Terrain Visibility Analysis**

RangePlotter is a command line, python-based geospatial utility designed to calculate high-fidelity sensor coverage maps for visualisation in an appropriate viewer (such as Google Earth). Unlike simple geometric tools, RangePlotter integrates high-resolution global terrain data (Copernicus GLO-30) to determine exactly where a sensor can see, accounting for Earth curvature, atmospheric refraction, and terrain masking (viewsheds).

## Use Cases

*   **Radar Network Visualisation**: Optimize site selection by visualizing coverage gaps and terrain shadowing.
*   **Telecommunications**: Analyze line-of-sight for microwave links or radio towers.
*   **Gap Analysis**: Identify blind spots in existing sensor networks.

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

## Installation

### Option 1: Standalone Binary (Recommended for Linux Users)
No Python environment required.
1.  **Download** the latest release from the [GitHub Releases page](https://github.com/renwell-studio/rangeplotter/releases).
2.  **Make executable**:
    ```bash
    chmod +x rangeplotter
    ```
3.  **Run**:
    ```bash
    ./rangeplotter --help
    ```

### Option 2: Python Source (For Developers)
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

## ⚡ Quick Start Guide

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

The behavior is controlled by `config/config.yaml`. Key settings include:

| Setting | Description | Default |
| :--- | :--- | :--- |
| `altitudes_msl_m` | List of target altitudes to analyze during viewshed calculation (e.g., `[50, 1000]`). | `[50]` |
| `radome_height_m_agl` | Height of the sensor above ground. | `5.0` |
| `atmospheric_k_factor` | Refraction coefficient (4/3 Earth is common for radar applications). | `1.333` |
| `simplify_tolerance_m` | Polygon simplification (higher = smaller files). | `5.0` |
| `input_dir` | Directory to scan for KML inputs. | `working_files/input` |

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