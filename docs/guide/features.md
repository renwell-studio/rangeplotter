# Key Features

## Sensor Altitude Override
By default, RangePlotter uses the `sensor_height_m_agl` setting in `config.yaml` (default 5m) for all sensors.

You can override this for specific sensors directly in your input KML file:
1.  In Google Earth, open the **Properties** of the Placemark.
2.  Go to the **Altitude** tab.
3.  Change "Altitude" to **Relative to ground**.
4.  Enter the desired sensor height (e.g., `20` meters).

RangePlotter will detect this setting and use 20m as the sensor height for that specific site, while using the default for others.

## Offline Capability
RangePlotter is designed to be bandwidth-efficient. It checks your local cache for Digital Elevation Model (DEM) tiles before attempting to download them.

*   **Smart Caching**: If you have run a viewshed for a specific area before, the DEM tiles are likely already on your disk.
*   **Lazy Authentication**: The tool only connects to the Copernicus API if it *needs* to download missing tiles. If all required data is cached, it will not ask for credentials or require an internet connection.
*   **Offline Field Use**: You can "pre-load" an area by running a viewshed (or using `--download-only`) while online. You can then take your laptop into the field and run new analyses in that same area completely offline.

## Smart Resume & Session Management
RangePlotter includes a robust system to save time and recover from interruptions.

### Smart Resume (Embedded State)
Instead of relying on external files, RangePlotter embeds a cryptographic hash of the simulation parameters directly into the output KML files (in the `<ExtendedData>` section).

**What is tracked?**
The hash ensures validity by tracking:
*   Sensor location (Lat/Lon)
*   Sensor effective height (Ground Elevation + Tower Height)
*   Target altitude
*   Atmospheric refraction factor (k-factor)
*   Earth radius model
*   Maximum horizon range

**Benefits:**
*   **Robustness**: You can move, rename, or share your output files, and RangePlotter will still know exactly how they were generated.
*   **Change Detection**: If you change a critical parameter (e.g., `atmospheric_k_factor` or sensor height) and re-run the analysis, RangePlotter detects the mismatch and automatically recalculates only the affected files.
*   **Skipping**: If the parameters match the existing file, the calculation is skipped instantly.

### Session Management
The `network run` command automatically tracks your active session.
*   **Crash Recovery**: If a long batch run is interrupted (e.g., power failure or Ctrl+C), simply running `network run` again will detect the incomplete session.
*   **One-Click Resume**: The system will prompt you to resume the previous session, restoring your input/output paths and configuration automatically.

## Integrated Network Workflow
The `network run` command streamlines the entire process for multi-site networks.
1.  **Viewshed**: Calculates visibility for all sites.
2.  **Horizon**: Computes theoretical max ranges.
3.  **Detection Range**: Clips viewsheds to instrument limits and creates composite coverage maps.

This command also supports an **Interactive Wizard** mode to guide you through the setup if you don't provide command-line arguments. The wizard allows you to review and revise your configuration settings (altitudes, ranges, etc.) before starting the analysis.

## Target Altitude Modes (AGL vs MSL)
*   **AGL (Above Ground Level)**: The target maintains a constant height above the terrain surface. This is ideal for:
    *   Low-level aircraft / drone detection.
    *   Ground-based comms coverage.
    *   *Result*: The viewshed follows the contours of valleys and hills.
*   **MSL (Mean Sea Level)**: The target is at a fixed barometric altitude. This is ideal for:
    *   High-altitude aircraft.
    *   *Result*: The target may crash into terrain if the ground elevation exceeds the target altitude.

## Enhanced Metadata & KML Styling
RangePlotter generates KML files optimized for professional use in Google Earth.
*   **Clean Navigation**: The "Places" side pane in Google Earth is kept clean. Metadata text is suppressed in the list view to prevent clutter when working with many sensors.
*   **Rich Information**: Clicking on any sensor or viewshed polygon opens a detailed popup containing:
    *   **Sensor Details**: Name, Location, Ground Elevation (MSL), Height (AGL).
    *   **Run Parameters**: Date, Command, Target Altitude, Max Range.
    *   **Physics Models**: Earth Radius Model, Refraction Factor.
*   **Machine Readable**: All metadata is also stored in KML `<ExtendedData>` tags, allowing for programmatic parsing by other tools.

## Multiscale Processing
RangePlotter employs a "multiscale" approach to balance speed and accuracy.
*   **Near Field (< 20km)**: Uses full 30m resolution DEM data. Critical for accurate local horizon masking.
*   **Far Field (> 20km)**: Uses downsampled (90m) data. At these distances, small terrain features have less impact on line-of-sight, and the speedup is significant.

## Sequential Filenaming
Output files are automatically prefixed with numbers (e.g., `01_`, `02_`) based on the target altitude. This ensures that when you load a folder of results into Google Earth, they appear in a logical order (lowest altitude to highest).


