# Radar Line-of-Sight (LOS) Terrain Visibility Utility

## 1. Objectives
- Compute theoretical radar geometric range rings for specified target altitudes using Earth curvature + atmospheric refraction adjustments.
- Refine each ring via terrain-aware line-of-sight (viewshed) using Copernicus GLO-30 DEM to produce polygons of actual visibility per altitude per radar.
- Produce union LOS polygons across all radars for each altitude.
- Output KML/KMZ files organized in a logical directory structure for Google Earth Pro (Linux desktop).
- Provide a modular, extensible Python codebase allowing later integration of radar performance (frequency, power, RCS) and advanced propagation effects.

Notes confirmed by user:
- Target altitudes are specified in metres above mean sea level (MSL).
- Input KML can contain up to 100+ radars; per-site sequential processing is acceptable.
- High-altitude targets may require radii of 500+ km.
- KML output is sufficient; style initially: orange outline, weight 2, no fill, configurable.
- Union polygons must preserve holes (terrain shadows) precisely.
- Strict bitwise reproducibility NOT required (approximate stable outputs acceptable).

## 2. High-Level Architecture
```
visibility/
  docs/
  src/
    config/           # Config loading & validation
    io/               # KML parsing, DEM download, raster tiling, KML/KMZ export
    geo/              # Coordinate transforms, projections, Earth model utilities
    los/              # Range ring generation, terrain LOS, union operations
    models/           # Domain models (RadarSite, LOSResult, Config)
    cli/              # Command-line interface entry points
    utils/            # Logging, caching helpers, concurrency helpers
  tests/
    data/             # Sample KML, small DEM tiles, expected outputs
  data_cache/         # Local DEM tile cache (gitignored)
  output/             # Generated KML/KMZ & intermediate rasters
  pyproject.toml / requirements.txt
  README.md
```

### Module Responsibilities
- `config`: Parse YAML/TOML config; validate numeric ranges; compute derived constants (effective Earth radius).
- `io.kml`: Read radar points from KML; support Placemark Points; extract name/id.
- `io.dem`: Determine bounding boxes per radar + max range; fetch/mosaic GLO-30 tiles; reproject to working CRS.
- `geo.proj`: Choose optimal local projected CRS (UTM zone or equal-area) for each radar for accurate distance buffers; provide transformations.
- `los.rings`: Generate geometric range rings per altitude using horizon distance formulas.
- `los.viewshed`: Compute terrain LOS using adapted viewshed (GDAL API) with curvature & refraction; incorporate target altitude logic.
- `los.union`: Union per-altitude polygons across radars; dissolve contiguous areas; simplify geometry.
- `io.export`: Export rings and LOS polygons as KML/KMZ folders (per altitude, per radar, plus union).
- `cli`: Provide commands: `prepare-dem`, `horizon`, `viewshed`, `export`, `all`.

Projection strategy for large radii (UTM boundary safe):
- Use local Azimuthal Equidistant (AEQD) centered on each radar for buffering/raster ops at ranges up to ~1000 km with controlled distortion. Fall back to UTM for small radii only if AEQD unavailable. Auto-select based on max range.

## 3. Technology Stack & Libraries
- Language: Python 3.11+
- Geospatial: `GDAL`, `rasterio`, `shapely`, `pyproj`
- DEM Access: Copernicus Data Space Ecosystem API (OData/REST + token auth)
- KML: `fastkml` for parsing; `simplekml` for export (or manual XML if performance needed)
- Config: `pydantic` or `dynaconf` (prefer `pydantic` for strict validation)
- CLI: `typer` or `click` (prefer `typer`)
- Caching: Local filesystem; optional `sqlite` index for tile metadata.
- Parallelism: `concurrent.futures` or `ray` (initially simple thread/process pool).
- Testing: `pytest`
 - Progress/UI: `rich` (progress bars) or `tqdm`.
 - Math/perf: `numpy`, optional `numba` for custom LOS kernel, `psutil` for CPU affinity and throttling.
 - Geodesy/vertical: `geographiclib` for ellipsoidal computations and geoid where needed.

## 4. Data Acquisition (Copernicus GLO-30)
1. Authentication: Obtain access token via CDSE public client (`cdse-public`) using password grant (`grant_type=password`) initially, then prefer refresh token (`grant_type=refresh_token`). No client secret is used.
2. Tile Identification:
   - Determine maximum required radius from highest altitude horizon distance.
   - Build bounding box around radar site (buffer with margin ~5%).
   - Query GLO-30 (COP-DEM) products via OData with minimal filters: `Collection/Name eq 'COP-DEM'` AND geographic intersects of bounding box polygon.
   - Narrow further using optional `datasetIdentifier` attribute filter (e.g. `COP-DEM_GLO-30`) to exclude other COP-DEM variants.
3. Download & Cache:
   - Prefer Cloud Optimized GeoTIFF (COG) streaming if assets expose direct GeoTIFF; otherwise download `$value` product once.
   - Initially store referenced product metadata only (Id, Name, Footprint) to avoid premature bulk downloads.
   - Implement lazy / on-demand fetch when elevation sampling first required (reduces number of requests if only ring computation done).
4. Mosaic:
   - Use `rasterio.merge` or `gdalbuildvrt` to build a virtual mosaic per radar region.
5. Reprojection:
   - Project mosaic to working projected CRS (e.g., appropriate UTM zone) for accurate distance buffering & raster ops.
6. Resolution Considerations:
   - 30m resolution impacts LOS pixel precision; document expected horizontal accuracy.
7. Refresh Strategy:
   - Config parameter for forced re-download; expiration policy optional.
 8. Vertical datum awareness:
    - Confirm Copernicus DEM vertical reference (typically EGM96 geoid). Treat target altitudes as MSL; ensure consistency. Provide option to apply geoid separation corrections if needed.

### Request Minimization Strategy
- Use a single OData query per radar with bounding box polygon and `top` limit tuned to expected number of overlapping tiles (configurable).
- Apply `datasetIdentifier` attribute filter when known to reduce result set.
- Defer asset download until elevation sampling or LOS rasterization phase (lazy loading).
- Future enhancement: dynamic subsetting via COG HTTP range requests (no full-file download) leveraging rasterio's vsicurl once authenticated headers are supported.
- Consider splitting very large radius into near/mid/far concentric zones and only requesting GLO-30 for near/mid while using coarser DEM (GLO-90) for far zone (optional multiscale optimization).

## 5. Configuration Schema (YAML/TOML)
Example (YAML) (updated auth model):
```yaml
radars_kml: "input/radars.kml"
output_dir: "output"
cache_dir: "data_cache"
altitudes_msl_m: [500, 1000, 3000, 6000, 10000]  # Target altitudes above mean sea level (clarify!)
radome_height_m_agl: 15
atmospheric_k_factor: 1.333  # Effective Earth radius factor (k)
earth_radius_m: 6371008.8
working_crs_strategy: "auto_utm"  # auto_utm | manual:EPSG:XXXX
max_threads: 4
simplify_tolerance_m: 5.0
export_format: "KML"  # KML | KMZ | GeoJSON (optional)
precision: 9
copernicus_api:
   base_url: "https://catalogue.dataspace.copernicus.eu/odata/v1"  # OData root
   token_url: "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
   client_id: "cdse-public"        # implicit if omitted
   # Do NOT store real credentials in committed config. Prefer supplying via env/.env.
   # username: null
   # password: null
   # refresh_token: null              # populate after first successful password grant & remove password
los:
  line_sampling_interval_m: 30  # Step along rays
  viewshed_algorithm: "gdal"    # gdal | custom
  target_height_mode: "msl"     # msl | agl
validation:
  min_visibility_area_m2: 1000
logging:
  level: "INFO"
```
Derived values at load:
- `effective_earth_radius_m = earth_radius_m * atmospheric_k_factor`
- Precompute max geometric horizon distances per altitude & radome.

Expanded schema (additions):
```yaml
style:
   line_color: "#FFA500"   # orange
   line_width: 2
   fill_color: null         # no fill
   fill_opacity: 0.0

concurrency:
   mode: "process"         # process | thread
   max_workers: 8           # or auto (<= logical_cpus - reserve)
   reserve_cpus: 4          # keep system responsive
   process_priority: "low"  # best-effort niceness

progress:
   enabled: true
   refresh_hz: 10

earth_model:
   type: "ellipsoidal"      # ellipsoidal always; spherical removed
   ellipsoid: "WGS84"        # configurable but defaults WGS84

vertical:
   target_altitude_reference: "msl"
   dem_vertical_reference: "EGM2008"  # Copernicus GLO-30 vertical datum (EPSG:3855)

multiscale:
   enable: true
   near_m: 50000
   mid_m: 200000
   far_m: 800000
   res_near_m: 30
   res_mid_m: 120
   res_far_m: 1000
```

## 6. Core Algorithms
### 6.1 Horizon Distance (Geometric)
For observer height `h_r` (radar elevation + radome) and target altitude `h_t`:
- Single horizon distance (target at ground): `d_h ≈ sqrt(2 * h_r * R_eff)`.
- Mutual LOS distance when both elevated: `d_max ≈ sqrt(2 * R_eff * h_r) + sqrt(2 * R_eff * h_t)`.
Where `R_eff = k * R_earth`.

Ellipsoidal radius (always used):
- Replace constant `R_earth` with local effective radius derived from WGS84: use mean of meridian (M) and prime vertical (N) curvatures or a more precise azimuthally averaged radius. Apply `k` to this local radius for `R_eff`.

### 6.2 Curvature Drop
At distance `d`: `drop(d) = d^2 / (2 * R_eff)`.

### 6.3 LOS Ray Sampling (Custom for MSL Target Altitudes)
For each candidate pixel center along radial direction:
1. Compute ground elevation `h_g(x)` from DEM.
2. Effective ground with curvature: `h_eff(x) = h_g(x) + drop(x)`.
3. Line-of-sight height toward target altitude plane `h_t` at distance fraction `f = x / d_target`: `h_line(x) = h_r + (h_t - h_r) * f`.
4. Visible if `h_eff(x) <= h_line(x)` for all intermediate samples.

Performance adaptations:
- Adaptive step size that increases with distance; ensure Nyquist on terrain frequencies after resampling.
- Multiscale DEM pyramid: 30 m near-field, 120 m mid-field, 1 km far-field as configured.
- Maintain the running maximum elevation angle method to avoid O(n^2) checks: a sample is visible if its angle to observer is greater than the max of previous samples; extend to altitude plane by comparing angle to `h_t` at each distance.

### 6.4 GDAL Viewshed Integration
GDAL's `ViewshedGenerate` supports curvature & refraction parameters:
- Observer height: `h_r`
 - Target height: GDAL supports constant `targetHeight` above ground, which does not directly model MSL target altitudes varying by cell. Use GDAL viewshed for the special case `h_t == DEM(x)` (i.e., ground targets), or for AGL analyses. For MSL targets, use the custom sampler (6.3).
- Use negative curvature coefficient to mimic increased Earth radius (refraction). Provide `CURVATURE_CORRECTION` and `REFRACTION_COEFFICIENT`.
- Post-process raster to remove cells beyond `d_max`.

### 6.5 Polygon Construction
1. Convert visibility raster mask (`visible=1`) to polygons (raster-vector via `rasterio.features.shapes`).
2. Clip polygons to geometric ring (circle) to enforce radius limit.
3. Simplify geometry (`shapely.simplify`) with tolerance from config.
4. Ensure validity (`buffer(0)` if necessary).

### 6.6 Union per Altitude
- Collect per-radar LOS polygons for altitude `h_t`.
- Dissolve with `shapely.union_all`.
- Optionally hole removal if area < threshold.

### 6.7 Export
- Each altitude: folder structure `output/altitude_<value>/radar_<id>/los.kml` and a `union.kml`.
- Range rings: `output/range_rings/radar_<id>.kml` including placemark styling.

KML altitude semantics (input robustness):
- Support `<altitudeMode>` values: `clampToGround`, `relativeToGround`, `absolute`.
- If `clampToGround` or no altitude: derive radar elevation from DEM + `radome_height_m_agl`.
- If `relativeToGround`: treat coordinate z as AGL; radar MSL = DEM + z; then add `radome_height_m_agl`.
- If `absolute`: treat coordinate z as MSL; then add `radome_height_m_agl`.
- Allow config flags to override or ignore embedded altitudes.

## 7. Implementation Phases
1. Foundations
   - Project scaffolding, config loader, logging setup.
   - Basic KML radar site parsing.
2. Geometry & Earth Model
   - Implement horizon distance & derived metrics (spherical + optional ellipsoidal radii).
3. DEM Acquisition
   - API client; tile query; caching & mosaic.
4. CRS Handling
   - AEQD centered on radar for large radii; UTM fallback; transform utilities.
5. Range Ring Generation
   - Buffer operations in projected CRS; export circles.
6. Terrain LOS (MVP)
   - Custom MSL-target LOS sampler with curvature/refraction; multiscale pyramid.
   - Optional GDAL viewshed path for ground-target analyses.
7. Raster Post-Processing & Vectorization
   - Clip to ring, polygonize, simplify.
8. Union & Aggregation
   - Merge per altitude; output union polygons.
9. Export Layer Structuring
   - KML export with folder hierarchy & user-configurable styling (orange, 2 px, no fill default).
 10. Performance & Parallelism
    - Parallel per-radar with limited worker count and CPU reservation; chunk altitudes sequentially per radar to bound memory.
    - Progress bars per radar and overall.
11. Validation & Testing
    - Unit tests for formulas, integration tests on small sample area.
12. Documentation & Examples
    - README, usage examples, sample config + sample KML.

## 8. Testing Strategy
- Unit: horizon distance, curvature drop, config validation.
- Integration: Single radar small DEM (mock or clipped real tile) verifying LOS ring size plausible.
- Regression: Compare visibility area changes with config adjustments.
- Performance: Time per altitude per radar; memory usage.
- Determinism: Same inputs produce identical polygon WKT hashes.


## 9. Performance Considerations
- Limit maximum radius to required `d_max` to reduce DEM extent.
- Use VRT instead of physical mosaics where possible.
- Raster resolution trade-off: Option to resample DEM to coarser grid for speed (configurable).
- Parallelization: Process (not thread) for CPU-bound operations due to GIL, except I/O-bound downloads.
- Cache union results if altitude set identical between runs.
 - Resource control: Reserve CPUs to keep machine responsive; set low process priority; optionally slow down with sleep quotas between tiles.
 - Memory mapping for DEM windows to avoid large arrays in RAM.
 - GPU note: GDAL viewshed is CPU-bound; Intel Arc (iGPU) acceleration is not readily available without custom kernels. Future oneAPI/numba-dppy acceleration for custom sampler possible.

## 10. Extensibility Roadmap
- Radar Detection Modeling: Add module for propagation & detection probability surfaces.
- Atmospheric Variability: Dynamic `k` factor by standard atmosphere or local weather input.
- Clutter & Landcover: Integrate ancillary datasets for classification.
- UI Layer: Web front-end or QGIS plugin.
- Cloud Execution: Batch processing on remote server with tile streaming.
 - GPU Acceleration: Prototype oneAPI or OpenCL path for LOS kernel when available.

## 11. Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| API rate limits / auth failures | Implement exponential backoff; local caching; refresh token reuse; fall back to password grant if refresh fails. |
| Large DEM memory usage | Use windowed reading; VRT + streaming. |
| CRS distortion over wide areas | Limit to local UTM; if large, move to geodesic buffering (geographiclib). |
| Ambiguous altitude definition (MSL vs AGL) | Clarify with config flag; document clearly. |
| GDAL version differences | Pin GDAL version; test features availability. |
| Polygon artifacts (slivers/holes) | Post-process with area threshold filters. |
 | LOS at very large radii | Use AEQD projection and multiscale DEM to bound distortion and compute load. |

## 12. Logging & Observability
- Structured logs (JSON optional) for each major phase.
- Timing decorators per altitude computation.
- Summary report: area sizes per altitude, union area, average visibility percentage.
 - Progress bars: overall and per-radar using `rich`.

## 13. Security & Compliance
- Securely store API credentials (env vars or separate secrets file not committed).
- Provide checksum verification for DEM tiles.

## 14. CLI Commands (Draft)
- `visibility prepare-dem --config config.yaml`
- `visibility horizon --config config.yaml`
- `visibility viewshed --config config.yaml --altitude 3000`
- `visibility export --config config.yaml`
- `visibility all --config config.yaml`

## 15. Acceptance Criteria
- Given sample config + radar KML, tool produces KML rings & LOS polygons without error.
- Union polygons exist for every altitude.
- Areas are plausible (no negative or zero area). 
- Runtime for single radar, 5 altitudes over 50km radius < configurable target (e.g., <5 min on baseline hardware).
 - Running on Intel Core Ultra 7 155H with 32GB RAM keeps OS responsive (CPU reserved, RAM bounded) during long runs.

## 16. Clarifying Questions (Resolved/Updated)
1. Altitudes: Are provided target altitudes above mean sea level (MSL) or above local ground (AGL)? Need explicit definition.
2. Typical altitude range & count? (Affects performance strategy.)
3. Number of radar sites expected concurrently? (Memory planning.)
4. Maximum anticipated horizon radius? (To size DEM requests.)
5. Acceptable processing time per altitude per radar? (Performance target.)
6. Do you require KMZ compression or is plain KML adequate?
7. Styling preferences for polygons & rings (colors, opacity)?
8. Should union polygon include internal holes (terrain shadow) or represent outer envelope only?
9. Any need for partial LOS (e.g., percentage visibility per sector) rather than binary? Future extension? — Defaulting to binary; can add percent-visible per azimuth bin later if desired.
10. Will coordinates always be WGS84 (EPSG:4326) in KML input? Any altitudes embedded there? — Assume WGS84, robustly parse altitude modes.
11. Determinism implications: exact bitwise outputs may vary with floating-point and parallelism. If strict reproducibility is required, we will enable single-threaded ordered processing and fixed simplification tolerance.
12. UTM boundary handling: for large radii and high latitudes, we will prefer AEQD centered per radar to avoid cross-zone distortion.
13. GeoJSON for intermediates: default is yes for debugging (gitignored); improves testability and repeatability.
14. Dependencies: open-source only.

## 17. Recommendations & Potential Adjustments
- Use GDAL viewshed first; fall back to custom ray sampling only if altitude handling proves insufficient.
- Maintain altitude semantics with a dedicated `AltitudeMode` enum to avoid confusion.
- Implement a geometry cache for repeated union operations across altitudes.
- Keep DEM tiles untouched; use VRT to avoid unnecessary disk writes.
- Postpone advanced propagation until LOS base stable; design interfaces now (e.g., `VisibilityModel` strategy pattern).

Notes:
"Geometry cache" refers to storing and reusing union/intermediate vector results keyed by input hashes (sites, altitude list, k factor). This speeds re-runs where inputs are unchanged.

## 18. Next Steps After Plan Approval (Updated)
1. Integrate CDSE auth (password + refresh) – DONE.
2. Implement COP-DEM OData product listing for radar bbox (in progress).
3. Persist product metadata & add prepare-dem CLI.
4. Add DEM tile download + unzip + mosaic (VRT) for sample area.
5. Elevation sampling for radar ground height (replace placeholder 0.0).
6. Implement custom LOS sampler for MSL target altitudes.
7. Vectorization, union, export.
8. Performance tuning & documentation.

## 19. Progress & Resource Controls
- Expose CLI flags to cap workers and reserve CPUs.
- Lower process priority (nice) and optionally I/O priority for downloads.
- Periodic progress reporting with ETA per radar and overall; write checkpoint files to allow resume.

---
Please review clarifying questions and recommendations. Confirm or adjust before implementation begins.
