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
Calculating viewsheds is computationally expensive. RangePlotter embeds a cryptographic hash of the simulation parameters directly into the output KML files (in the `<ExtendedData>` section). This allows the tool to verify if an existing output file matches your current configuration.

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
*   **Crash Recovery**: If a long multi-sensor calculation run fails (or you stop it mid-run), RangePlotter can restart from the last completed viewshed and avoid recalculating redundant viewsheds.

### Session Management
The `network run` command automatically tracks your active session.
*   **Crash Recovery**: If a long batch run is interrupted (e.g., power failure or Ctrl+C), simply running `network run` again will detect the incomplete session.
*   **One-Click Resume**: The system will prompt you to resume the previous session, restoring your input/output paths and configuration automatically.
The `viewshed` command will inspect every file in the `working_files/viewshed/` folder (but not any subfolders you may have created) for completed viewshed outputs matching the requested calculation and skips calculation where found (unless you use `--force`).

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

## Data Caching

RangePlotter uses a two-tier caching system to minimize redundant downloads and computations. Understanding how caching works helps you manage disk space and troubleshoot issues.

### DEM Tile Cache

**Location:** `data_cache/dem/`

RangePlotter downloads Copernicus GLO-30 Digital Elevation Model (DEM) tiles on-demand and caches them locally.

**Behavior:**
- Tiles are 1°×1° geographic cells (~100 MB each, compressed).
- Once downloaded, tiles are reused for any analysis in that region.
- The cache persists across sessions and RangePlotter versions.
- Tiles are never automatically deleted; manual cleanup is required if disk space is needed.

**Typical Sizes:**
| Coverage | Approximate Size |
|----------|------------------|
| Single sensor (500km radius) | ~500 MB - 2 GB |
| Regional network (10 sensors) | ~2 - 10 GB |
| National-scale analysis | ~10 - 50 GB |

**Management:**
```bash
# Check DEM cache size
du -sh data_cache/dem/

# Clear DEM cache (will re-download on next run)
rm -rf data_cache/dem/
```

### Viewshed Cache (MVA Surfaces)

**Location:** `data_cache/viewsheds/`

RangePlotter caches the expensive Line-of-Sight geometry calculations as **Minimum Visible Altitude (MVA)** surfaces. This is a physics-level cache that enables instant recomputation for different target altitudes.

**How It Works:**

Instead of computing "visible/not visible" for a specific altitude, RangePlotter computes the *minimum altitude a target must be at* to be visible from each point. This MVA surface can then be thresholded instantly for any target altitude.

**What Triggers a Cache Hit:**
- Changing the target altitude (e.g., from 500m to 1000m)
- Changing visual styling (fill color, line color, opacity)
- Re-running the same sensor with different output options

**What Triggers a Cache Miss (Full Recalculation):**
- Changing sensor position (latitude/longitude)
- Changing sensor height (AGL)
- Changing the atmospheric refraction k-factor
- Changing the Earth model

**Storage Format:**
- Compressed GeoTIFF files (Float32, LZW compression)
- One file per multiscale zone (near, mid, far)
- Typical size: 5-20 MB per zone

**Typical Sizes:**
| Scenario | Approximate Size |
|----------|------------------|
| Single sensor, 3 zones | ~30 - 60 MB |
| 10 sensors | ~300 - 600 MB |
| 50 sensors | ~1.5 - 3 GB |

**Management:**
```bash
# Check viewshed cache size
du -sh data_cache/viewsheds/

# Clear viewshed cache (will recompute on next run)
rm -rf data_cache/viewsheds/

# Bypass cache for a single run (force fresh calculation)
rangeplotter viewshed -i input.kml --no-cache
```

**Cache Versioning:**
The viewshed cache includes a version identifier. When RangePlotter's calculation algorithm is updated, old cache files are automatically ignored and fresh calculations are performed. You do not need to manually clear the cache after upgrading.

### Two-Tier Cache Architecture

RangePlotter uses a **two-tier caching system** to maximize performance:

| Tier | System | What It Caches | Hash Includes |
|------|--------|----------------|---------------|
| 1 | **Viewshed Cache** | MVA raster (physics) | Sensor position, height, k-factor, Earth model |
| 2 | **Output State** | KML file validity | All of Tier 1 + target altitude + styling |

**How They Work Together:**

```
User runs: rangeplotter viewshed -i radar.kml -a 100

┌─────────────────────────────────────────────────────────┐
│ Step 1: Output State Check                              │
│   Does output KML exist with matching parameters?       │
│   → YES: Skip everything (instant)                      │
│   → NO: Continue to Step 2                              │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│ Step 2: Viewshed Cache Check                            │
│   Does MVA raster exist for this sensor/zone?           │
│   → YES: Load from cache (skip DEM & radial sweep)      │
│   → NO: Compute MVA, save to cache                      │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│ Step 3: Generate Output                                 │
│   Threshold MVA at target altitude → binary mask        │
│   Polygonize → vectors → Apply styling → Export KML     │
└─────────────────────────────────────────────────────────┘
```

**Example Scenarios:**

| Scenario | Viewshed Cache | Output State | Result |
|----------|----------------|--------------|--------|
| Identical command | HIT | HIT | Skip everything (instant) |
| Same sensor, different altitude | HIT | MISS | Load cached MVA, threshold, export |
| Same sensor, different color | HIT | MISS | Load cached MVA, re-export with new style |
| Different sensor height | MISS | MISS | Full recalculation |

This architecture means that running `detection-range` (which tests 10+ altitudes) is ~10x faster after the first run, since only the thresholding and export steps need to repeat.

### Cache Directory Configuration

The cache directory location is configurable in `config.yaml`:

```yaml
cache_dir: "data_cache"  # Default location
```

All caches (DEM tiles, viewshed MVA surfaces) are stored under this directory.


