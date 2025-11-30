# Getting Started

## Installation

RangePlotter is available as a standalone binary for Linux or as a Python package for cross-platform use.

### Option 1: Standalone Binary (Linux)
Recommended for most Linux users. No Python environment is required.

1.  **Download** the latest `rangeplotter_vX.Y.Z_linux.zip` from the [Releases page](https://github.com/renwell-studio/rangeplotter/releases).
2.  **Unzip** the archive.
3.  **Run the installer**:
    ```bash
    ./install.sh
    ```
    This script will:
    *   Install the application to `~/rangeplotter` (default).
    *   Auto-configure performance settings for your hardware.
    *   Preserve your existing configuration and data if upgrading.
    *   **Note**: It is always recommended to backup your important files before upgrading (e.g. copy `config.yaml` to `config.yaml.backup`). Key resources are:
        *   `config.yaml`
        *   `.env`
        *   `working_files/`
        *   `data_cache/`

### Option 2: Python Wheel (Cross-Platform)
For users with Python installed (Windows, macOS, Linux).

1.  **Download** the `.whl` file from the Releases page.
2.  **Install** via pip:
    ```bash
    pip install rangeplotter-X.Y.Z-py3-none-any.whl
    ```

## Authentication (Copernicus DEM)

RangePlotter uses high-resolution global terrain data (GLO-30) from the Copernicus Data Space Ecosystem. You need a free account to access this data.

1.  **Register** at [dataspace.copernicus.eu](https://dataspace.copernicus.eu/).
2.  **Configure Credentials**:
    Create a `.env` file in your installation directory (or where you run the tool):
    ```bash
    COPERNICUS_USERNAME=your_email@example.com
    COPERNICUS_PASSWORD=your_password
    ```
    *Note: The application handles token generation and refreshing automatically.*

## First Run

1.  **Prepare Input**: Place a KML file containing your sensor location(s) in `working_files/sensor_locations/`. You can export this from Google Earth (Right-click placemark or folder of placemarks -> Save Place As -> KML).
2.  **Run Viewshed**:
    ```bash
    rangeplotter network run --input working_files/sensor_locations/my_sensor.kml
    ```
3.  **View Output**: The results will be saved in `working_files/network/`. Open the generated `.kml` file(s) in Google Earth (File -> Import...).
