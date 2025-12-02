# Command Reference

RangePlotter has four main commands. Run `rangeplotter --help` or `rangeplotter [command] --help` for quick reference.

## 1. `network run` (Recommended)
Orchestrates the complete analysis pipeline (`viewshed` -> `horizon` -> `detection-range`) in a single step.

The interactive wizard now includes a **Site Selection** step. If your input file contains multiple sites, you can choose to process all of them or select a specific subset interactively.

**Usage:**
```bash
# Interactive Wizard Mode
rangeplotter network run

# Non-Interactive Mode
rangeplotter network run --input examples/radars.csv --yes
```

**Key Options:**
*   `--input / -i`: Path to input KML/CSV file or directory.
*   `--output / -o`: Project output directory. Defaults to `working_files/network/{name}_{timestamp}`.
*   `--filter`: Regex pattern to process only specific sensors (e.g., `--filter "Site A"`).
*   `--force`: Force recalculation of viewsheds even if they already exist (bypasses Smart Resume).
*   `--yes / -y`: Skip interactive confirmation.

---

## 2. `viewshed`
Calculates the actual terrain-aware visibility.

**Usage:**
```bash
rangeplotter viewshed [OPTIONS]
```

**Key Options:**
*   `--input / -i`: Path to input KML/CSV file or directory. Defaults to `working_files/sensor_locations`.
*   `--output / -o`: Output directory.
*   `--altitudes / -a`: Comma-separated list of target altitudes to calculate (overrides config).
    *   *Example*: `-a 50,100,500`
*   `--sensor-heights / -sh`: Comma-separated list of sensor heights (AGL) to calculate (overrides config).
    *   *Example*: `-sh 10,20,30`
*   `--reference / --ref`: Set target altitude reference (`agl` or `msl`).
*   `--filter`: Regex pattern to filter sensors.
*   `--force`: Force recalculation.
*   `--download-only`: Download required DEM tiles but skip calculation.
*   `--check`: Check if tiles are available locally without downloading.

**Output:**
Generates one KML file per sensor per target altitude (e.g., `01_rangeplotter-SiteA-tgt_alt_100m_AGL.kml`).
*   Files include embedded metadata (Sensor Height, Ground Elevation, etc.) accessible via popups.
*   Side-pane text is suppressed for cleaner navigation.

---

## 3. `horizon`
Calculates the theoretical maximum geometric horizon (range rings) based on Earth curvature and sensor height, ignoring terrain.

**Usage:**
```bash
rangeplotter horizon [OPTIONS]
```

**Key Options:**
*   `--union/--no-union`: Control output format (default: `--union`).
    *   `--union`: Output a single `rangeplotter-union-horizon.kml` with all sensors.
    *   `--no-union`: Output individual `{prefix}rangeplotter-{name}-horizon.kml` files per sensor.
*   `--output / -o`: Output directory. Pure names go to `working_files/horizons/`, paths with `./`, `../`, or `/` are used as-is.

**Output:**
Generates a KML file containing range rings for all sensors at the configured target altitudes. Useful for comparing "theoretical max" vs "actual terrain-limited" performance.

---

## 4. `detection-range`
Post-processes viewsheds to clip them to specific maximum ranges (e.g., representing radar instrument limits).

**Usage:**
```bash
rangeplotter detection-range [OPTIONS]
```

**Key Options:**
*   `--ranges / -r`: Comma-separated list of ranges in km.
    *   *Example*: `-r 50,100,250`
*   `--input / -i`: Input directory containing *previously calculated viewsheds*. Defaults to `working_files/viewshed`.

**Output:**
Generates clipped viewsheds and "Union" files (combining coverage from multiple sensors) in `working_files/detection_range`.
