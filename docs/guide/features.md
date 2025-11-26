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

## Smart Resume
RangePlotter tracks the state of your simulations to avoid redundant work.
*   **How it works**: Before calculating a viewshed, the system computes a unique "hash" based on the sensor location, target altitude, and physics parameters.
*   **Benefit**: If you re-run a large network analysis (e.g., after adding a new site or fixing a config error), RangePlotter will instantly skip any viewsheds that have already been successfully calculated with the same parameters.
*   **Override**: Use the `--force` flag to bypass this check and force a recalculation.

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

## Multiscale Processing
RangePlotter employs a "multiscale" approach to balance speed and accuracy.
*   **Near Field (< 20km)**: Uses full 30m resolution DEM data. Critical for accurate local horizon masking.
*   **Far Field (> 20km)**: Uses downsampled (90m) data. At these distances, small terrain features have less impact on line-of-sight, and the speedup is significant.

## Sequential Filenaming
Output files are automatically prefixed with numbers (e.g., `01_`, `02_`) based on the target altitude. This ensures that when you load a folder of results into Google Earth, they appear in a logical order (lowest altitude to highest).

## Smart Resume
RangePlotter tracks the state of your simulations to avoid redundant work.
*   **How it works**: Before calculating a viewshed, the system computes a unique "hash" based on the sensor location, target altitude, and physics parameters.
*   **Benefit**: If you re-run a large network analysis (e.g., after adding a new site or fixing a config error), RangePlotter will instantly skip any viewsheds that have already been successfully calculated with the same parameters.
*   **Override**: Use the `--force` flag to bypass this check and force a recalculation.

## Integrated Network Workflow
The `network run` command streamlines the entire process for multi-site networks.
1.  **Viewshed**: Calculates visibility for all sites.
2.  **Horizon**: Computes theoretical max ranges.
3.  **Detection Range**: Clips viewsheds to instrument limits and creates composite coverage maps.

This command also supports an **Interactive Wizard** mode to guide you through the setup if you don't provide command-line arguments.
