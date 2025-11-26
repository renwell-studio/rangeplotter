# Command Reference

RangePlotter has three main commands. Run `rangeplotter --help` or `rangeplotter [command] --help` for quick reference.

## 1. `viewshed`
Calculates the actual terrain-aware visibility.

**Usage:**
```bash
rangeplotter viewshed [OPTIONS]
```

**Key Options:**
*   `--input / -i`: Path to input KML file or directory. Defaults to `working_files/sensor_locations`.
*   `--output / -o`: Output directory.
*   `--altitudes / -a`: Comma-separated list of target altitudes to calculate (overrides config).
    *   *Example*: `-a 50,100,500`
*   `--reference / --ref`: Set target altitude reference (`agl` or `msl`).
*   `--download-only`: Download required DEM tiles but skip calculation.
*   `--check`: Check if tiles are available locally without downloading.

**Output:**
Generates one KML file per sensor per target altitude (e.g., `01_rangeplotter-SiteA-tgt_alt_100m_AGL.kml`).

---

## 2. `horizon`
Calculates the theoretical maximum geometric horizon (range rings) based on Earth curvature and sensor height, ignoring terrain.

**Usage:**
```bash
rangeplotter horizon [OPTIONS]
```

**Output:**
Generates a `horizons.kml` file containing range rings for all sensors at the configured target altitudes. Useful for comparing "theoretical max" vs "actual terrain-limited" performance.

---

## 3. `detection-range`
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
