# Best Practices

## Optimizing for Google Earth
*   **Use `clamped` mode**: Keep `kml_export_altitude_mode: "clamped"` in your config. This "drapes" the visibility map over the 3D terrain in Google Earth, which looks much better and avoids "z-fighting" (flickering) artifacts compared to floating polygons.
*   **Manage Layer Visibility**: RangePlotter generates high-detail polygons. If you load many large viewsheds at once, Google Earth may slow down. Toggle visibility of folders to keep performance smooth.

## Performance Tuning
*   **Concurrency**: RangePlotter defaults to using most of your CPU cores. If your system becomes sluggish, you can reduce `max_workers` or increase `reserve_cpus` in `config.yaml`.
*   **Disk Swap**: For very large areas (e.g., 500km+ radius), the DEM data can exceed RAM. Ensure `resources.use_disk_swap` is `true` (default) to prevent crashes.
*   **Multiscale**: Keep `multiscale.enable: true`. Disabling it will force 30m resolution for the entire calculation, which can be 3-4x slower for very large radii with minimal visual difference.

## Data Management
*   **Cache**: The `data_cache/` directory stores downloaded DEM tiles. Do not delete this unless you want to free up space; re-downloading tiles takes time.
*   **Input Organization**: You can organize your input KMLs into subfolders within `working_files/sensor_locations/`. RangePlotter can process them recursively or you can point it to specific files.
