# Configuration Guide

RangePlotter is highly configurable via the `config/config.yaml` file. This file controls default behaviors, output paths, and calculation parameters.

## Key Settings

### Input / Output Directories
Define where the tool looks for files and saves results.
```yaml
input_dir: "working_files/sensor_locations"
output_viewshed_dir: "working_files/viewshed"
output_horizon_dir: "working_files/horizon"
output_detection_dir: "working_files/detection_range"
```

### Target Altitudes
Define the altitudes at which you want to calculate visibility.
```yaml
# List of target altitudes in meters
altitudes_msl_m: [10, 50, 100, 1000]

# Reference: 'msl' (Mean Sea Level) or 'agl' (Above Ground Level)
target_altitude_reference: "agl"
```
*   **AGL (Recommended)**: Calculates visibility for targets flying *at* these heights above the terrain. Essential for low-flying aircraft or ground-to-ground analysis.
*   **MSL**: Calculates visibility for targets at fixed altitudes above sea level.

### Sensor Height
Default height of the sensor above the ground.
```yaml
sensor_height_m_agl: 5.0
```
*Note: This can be overridden per-sensor using KML input (see [Features](features.md)).*

### KML Export Mode
Controls how the output polygons are drawn in Google Earth.
```yaml
kml_export_altitude_mode: "clamped"
```
*   **clamped (Default)**: Drapes the visibility polygon over the terrain. This is usually the best looking and most performant option for visualization.
*   **absolute**: Draws the polygon floating at the actual calculated altitude. Useful for 3D analysis but can look cluttered.

### Multiscale Processing
Optimizes performance by using lower resolution terrain data for distant areas.
```yaml
multiscale:
  enable: true
  near_m: 20000    # Use full resolution (30m) up to 20km
  mid_m: 100000    # Use 90m resolution up to 100km
  far_m: 800000    # Use 90m resolution beyond 100km
```
*This provides a significant speedup (2-3x) with minimal impact on accuracy for long-range viewsheds.*

### Styling
Customize the appearance of the output KMLs.
```yaml
style:
  line_color: "#FFA500"  # Orange
  line_width: 2
  fill_color: "#FFA500"
  fill_opacity: 0.5
```
