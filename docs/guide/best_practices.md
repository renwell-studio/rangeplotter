# Best Practices

## Optimizing for Google Earth
*   **Use `clamped` mode**: Keep `kml_export_altitude_mode: "clamped"` in your config. This "drapes" the visibility map over the 3D terrain in Google Earth, which looks much better and avoids "z-fighting" (flickering) artifacts compared to floating polygons.
*   **Manage Layer Visibility**: RangePlotter generates high-detail polygons. If you load many large viewsheds at once, Google Earth may slow down. Toggle visibility of folders to keep performance smooth.
*   **Metadata Access**: To view run parameters (Date, Sensor Height, Refraction, etc.), simply click on the sensor icon or the viewshed polygon in the 3D map view. The "Places" pane is intentionally kept clean to reduce visual clutter.

## Performance Tuning
*   **Concurrency**: RangePlotter defaults to using most of your CPU cores. If your system becomes sluggish, you can reduce `max_workers` or increase `reserve_cpus` in `config.yaml`.
*   **Disk Swap**: For very large areas (e.g., 500km+ radius), the DEM data can exceed RAM. Ensure `resources.use_disk_swap` is `true` (default) to prevent crashes.
*   **Multiscale**: Keep `multiscale.enable: true`. Disabling it will force 30m resolution for the entire calculation, which can be 3-4x slower for very large radii with minimal visual difference.

## Data Management
*   **Cache**: RangePlotter maintains two caches under `data_cache/`: DEM tiles and viewshed MVA surfaces. See [Data Caching](features.md#data-caching) for detailed information on cache locations, sizes, and management.
*   **Input Organization**: You can organize your input KMLs into subfolders within `working_files/sensor_locations/`. RangePlotter can process them recursively or you can point it to specific files.
*   **Disk Space**: For large-scale analyses, monitor your cache directories. DEM tiles (10-50 GB for national coverage) and viewshed caches (1-3 GB for 50 sensors) can accumulate over time.
