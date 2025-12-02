# Central Viewshed Cache & Minimum Visible Altitude (MVA)

## Overview
This document outlines the architectural and physical basis for the "Central Viewshed Cache" feature in RangePlotter v0.1.7. 

The goal is to transition RangePlotter from an **output-dependent** caching model (checking if a specific KML exists) to a **physics-dependent** caching model. This allows expensive Line-of-Sight (LoS) calculations to be reused across different commands, projects, and target altitudes.

## Core Concept: Minimum Visible Altitude (MVA)

Instead of calculating a binary "Visible/Not Visible" mask for a specific target altitude, the core physics engine will be updated to calculate a **Minimum Visible Altitude (MVA)** surface.

### The Physics
For every pixel in the analysis area, the MVA represents the lowest altitude (Above Ground Level) a target must be at to be visible from the sensor.

*   **Pixel Value = 0**: The ground itself is visible.
*   **Pixel Value = 500**: A target must be at least 500m AGL to be seen (it is currently in a shadow cast by terrain).
*   **Pixel Value = Infinity (or NoData)**: The location is completely obscured (e.g., beyond the horizon or behind a vertical obstruction that blocks all angles).

### The Algorithm (Modified Radial Sweep)
The radial sweep algorithm propagates a ray from the sensor outwards.
1.  Track the **maximum elevation angle** ($\theta_{max}$) encountered so far along the ray (caused by terrain peaks).
2.  At distance $d$, calculate the altitude required to clear $\theta_{max}$.
    *   *Flat Earth Simplified*: $h_{req} = h_{sensor} + d \cdot \tan(\theta_{max})$
    *   *Curved Earth*: Apply standard geodesic projection using the Effective Earth Radius ($R_{eff} = R_{earth} \times k$) to project the ray at $\theta_{max}$ to distance $d$.
3.  **MVA** = $h_{req} - h_{terrain}(d)$.
    *   If $h_{req} < h_{terrain}(d)$, then MVA = 0 (Ground is visible).

## Two-Tier Caching Architecture

RangePlotter uses a **two-tier caching system** to maximize performance while maintaining correctness:

| Tier | System | Layer | Purpose |
|------|--------|-------|--------|
| 1 | **ViewshedCache** | Physics | Caches the expensive LoS geometry calculation (MVA raster) |
| 2 | **StateManager** | Output | Caches the final KML file to avoid redundant export |

These systems are **complementary**:
*   `ViewshedCache` allows reuse of physics across different target altitudes and styling options.
*   `StateManager` prevents redundant polygonization and file I/O when the exact same output already exists.

---

### Tier 1: ViewshedCache (Physics-Level)

#### What It Caches
The **Minimum Visible Altitude (MVA) raster** — a Float32 GeoTIFF representing the LoS geometry. This is the expensive computation (radial sweep algorithm).

#### Cache Key (Hash)
SHA-256 hash of parameters that define the **obstruction geometry**:

| Parameter | Precision | Rationale |
|-----------|-----------|----------|
| Sensor Latitude | 6 decimals | ~0.1m precision |
| Sensor Longitude | 6 decimals | ~0.1m precision |
| Sensor Ground Elevation (MSL) | 1 decimal | Affects absolute height |
| Sensor Height (AGL) | 2 decimals | Directly affects shadow geometry |
| Zone Min Radius | Integer (m) | Multiscale zone boundary |
| Zone Max Radius | Integer (m) | Multiscale zone boundary |
| Zone Resolution | Integer (m) | Grid cell size |
| Refraction k-factor | 4 decimals | Atmospheric model |
| Earth Model | String | e.g., "WGS84" |

**EXCLUDED from ViewshedCache hash:**
*   **Target Altitude**: The MVA surface is valid for *all* target altitudes.
*   **Visual Styles**: Color, opacity, line width — these don't affect physics.
*   **Output Filename**: Irrelevant to physics.

#### Storage Format
*   **File Type:** GeoTIFF (`.tif`)
*   **Data Type:** `Float32` (altitude in meters AGL)
*   **Compression:** LZW (Lossless)
*   **Location:** `data_cache/viewsheds/<hash>.tif`

---

### Tier 2: StateManager (Output-Level)

#### What It Caches
The **existence and validity of a specific KML output file**. The hash is embedded in the KML's `<ExtendedData>` metadata.

#### Cache Key (Hash)
MD5 hash of parameters that define a **specific output file**:

| Parameter | Precision | Rationale |
|-----------|-----------|----------|
| Sensor Latitude | 6 decimals | Identifies the site |
| Sensor Longitude | 6 decimals | Identifies the site |
| Sensor Height (MSL) | 2 decimals | Affects output |
| Sensor Height (AGL) | 2 decimals | Affects output |
| **Target Altitude** | 2 decimals | Different altitudes = different outputs |
| Max Range | 1 decimal | Affects coverage extent |
| Refraction k-factor | 3 decimals | Physics model |
| Earth Model | String | e.g., "ellipsoidal" |
| **Fill Color** | String | Visual styling |
| **Line Color** | String | Visual styling |
| **Opacity** | 2 decimals | Visual styling |

**Key Difference**: StateManager hash **includes** target altitude and styling, because these affect the output KML even if the underlying physics is identical.

---

### How They Work Together

```
User runs: rangeplotter viewshed -i radar.kml -a 100 --fill-color #FF0000

┌─────────────────────────────────────────────────────────────────┐
│ Step 1: StateManager Check                                      │
│   Hash = f(sensor, target_alt=100, color=#FF0000, ...)          │
│   Q: Does output KML exist with matching hash?                  │
│   → YES: Skip everything, print "Already exists"                │
│   → NO: Continue to Step 2                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: ViewshedCache Check (per zone)                          │
│   Hash = f(sensor, zone_params, k_factor, ...)                  │
│   Q: Does MVA raster exist for this zone?                       │
│   → YES: Load from cache (skip DEM download & radial sweep)     │
│   → NO: Compute MVA, save to cache                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Generate Output                                         │
│   1. Threshold MVA at target_alt=100 → binary mask              │
│   2. Polygonize mask → vectors                                  │
│   3. Apply styling (color=#FF0000)                              │
│   4. Export KML with StateManager hash in metadata              │
└─────────────────────────────────────────────────────────────────┘
```

---

### Scenario Matrix

| Scenario | ViewshedCache | StateManager | Action |
|----------|---------------|--------------|--------|
| Identical command, same output | HIT | HIT | **Skip everything** (instant) |
| Same sensor, different target altitude | HIT | MISS | Load cached MVA, threshold, export new KML |
| Same sensor, different color | HIT | MISS | Load cached MVA, threshold, export with new style |
| Same sensor, different sensor height | MISS | MISS | Full recalculation |
| Different sensor entirely | MISS | MISS | Full recalculation |

## Workflow

### Step 1: Lookup
When `viewshed` or `network run` is executed:
1.  Compute the **Physics Hash**.
2.  Check `data_cache/viewsheds/<hash>.tif`.

### Step 2: Calculation (Cache Miss)
1.  Download DEM tiles (if needed).
2.  Reproject to AEQD.
3.  Run **MVA Radial Sweep**.
4.  Save result to `data_cache/viewsheds/<hash>.tif` (using atomic write/rename).

### Step 3: Generation (Cache Hit)
1.  Load the MVA GeoTIFF.
2.  **Thresholding**: Apply the user's requested target altitude ($T_{alt}$) to generate a binary mask.
    *   `Mask = (MVA_Raster <= T_{alt})`
3.  **Polygonize**: Convert the binary mask to vectors.
4.  **Export**: Save the final KML.

## Benefits

1.  **Instant Variable Target Altitudes**:
    *   Calculating `detection-range` (which runs viewsheds at 10+ altitudes) becomes **~10x faster**. The sweep runs once to generate the MVA; the 10 binary masks are generated instantly via thresholding.
2.  **Cross-Command Reuse**:
    *   A viewshed calculated during a single-site analysis is automatically found and reused during a batch `network run`.
3.  **Future-Proofing**:
    *   **Obscuration Proximity**: The MVA surface contains the data needed to visualize "how close" a target is to being obscured (Angular Clearance).
    *   **3D Volume Visualization**: The MVA surface effectively defines the "floor" of the visible volume.

## Limitations
*   **Variable Sensor Height**: Changing the sensor height fundamentally alters the shadow geometry. This still requires a full recalculation (new hash).
*   **Disk Usage**: Float32 rasters are larger than binary masks. A cache pruning strategy (LRU) will eventually be required.

## Implementation Plan

---

### Phase 1: Core Physics Refactor
**File:** `src/rangeplotter/los/viewshed.py`

#### 1.1 Refactor `_radial_sweep_visibility` → `_compute_mva_polar`
*   **Change Output**: Return a `Float32` numpy array representing the MVA in **Polar coordinates** `(n_az, n_r)`.
*   **Update Logic**:
    *   The current sweep tracks `M = max_angle_so_far` along each ray.
    *   Instead of `visible = (theta_target >= M)`, compute:
        ```python
        # h_req is the MSL altitude required to clear the max_angle M
        # Using the inverse of theta = (h - h_radar) / r - r / (2 * R_eff)
        # Solve for h: h_req = h_radar + r * (M + r / (2 * R_eff))
        h_req = radar_h_msl + r_values * (M + r_values / (2 * R_eff))
        
        # MVA is the height Above Ground Level
        mva_polar = h_req - terrain_elevations
        mva_polar = np.maximum(mva_polar, 0.0)  # Clamp to 0 if ground is visible
        ```
*   **Memory Impact**:
    *   Current: `visible_polar = np.zeros((n_az, n_r), dtype=bool)` — **1 byte/pixel**.
    *   New: `mva_polar = np.zeros((n_az, n_r), dtype=np.float32)` — **4 bytes/pixel**.
    *   *Mitigation*: The existing chunked azimuth processing must be preserved. Adjust `bytes_per_az` estimate from `n_r * 40` to `n_r * 44` (or similar) to account for the larger output array.

#### 1.2 Refactor `_polar_to_cartesian_mask` → `_polar_to_cartesian_mva`
*   The current code converts the boolean polar grid to a Cartesian `uint8` mask. 
*   Refactor to output a Float32 Cartesian MVA raster.
*   This is the raster we will cache.

#### 1.3 Create Helper `_threshold_mva_to_mask`
*   **Input**: MVA Surface (Float32 numpy array), Target Altitude (float).
*   **Output**: Binary Visibility Mask (`uint8` numpy array).
*   **Logic**: `return (mva <= target_alt).astype(np.uint8)`

---

### Phase 2: Caching Infrastructure
**File:** `src/rangeplotter/io/viewshed_cache.py` (New File)

#### 2.1 Create `ViewshedCache` Class

**Constructor:**
```python
def __init__(self, cache_dir: Path):
    self.cache_dir = cache_dir / "viewsheds"
    self.cache_dir.mkdir(parents=True, exist_ok=True)
```

**`compute_hash(...) -> str`:**
Generate SHA-256 hash from parameters that define the **obstruction geometry for a specific zone**.
*   Sensor Lat/Lon (rounded to 6 decimals).
*   Sensor Ground Elevation MSL (rounded to 1 decimal).
*   Sensor Height AGL (rounded to 2 decimals).
*   Zone Parameters: `zone_min_radius_m`, `zone_max_radius_m`, `zone_resolution_m`.
*   Physics: `k_factor` (rounded to 4 decimals), Earth Model string (e.g., "WGS84").

**Design Decision (Multiscale Handling):**
The current `compute_viewshed` uses a "Multiscale" approach with 3 zones (near, mid, far), each with different resolutions. The cache must store **one MVA raster per zone**, not one raster for the entire viewshed.
*   *Rationale*: A "near zone" raster (0-20km @ 30m res) is a different grid than a "far zone" raster (100-800km @ 90m res). They cannot be merged into one file without resampling and losing the benefit.
*   *Consequence*: The hash **must include zone parameters** (`z_min`, `z_max`, `z_res`).

**`get(hash: str) -> Optional[Tuple[np.ndarray, rasterio.Affine]]`:**
*   Check if `<cache_dir>/<hash>.tif` exists.
*   Load using `rasterio`.
*   Return `(data_array, transform)` or `None`.

**`put(hash: str, data: np.ndarray, transform: rasterio.Affine, crs: str)`:**
*   Save the Float32 array as a GeoTIFF.
*   **Profile**: `dtype=float32`, `count=1`, `compress='lzw'`.
*   **Concurrency**: Write to a temporary file (`<hash>.tmp.<random>`) and use `os.rename()` for atomic commit.

---

### Phase 3: Integration into `compute_viewshed`
**File:** `src/rangeplotter/los/viewshed.py`

#### 3.1 Signature Change
The function signature remains the same. The caching is an internal optimization, transparent to callers.

#### 3.2 Workflow Change (Inside the Zone Loop)

The current zone loop structure:
```python
for i, (z_min, z_max, z_res) in enumerate(zones):
    dem_array, transform = _reproject_dem_to_aeqd(...)
    poly = _radial_sweep_visibility(...)
    # clip, append
```

The **new** zone loop structure:
```python
cache = ViewshedCache(Path(config.get("cache_dir", "data_cache")))

for i, (z_min, z_max, z_res) in enumerate(zones):
    pass_max_r = min(d_max, z_max)
    
    # Compute hash for THIS zone
    zone_hash = cache.compute_hash(
        lat=radar.latitude, lon=radar.longitude,
        ground_elev=radar.ground_elevation_m_msl,
        sensor_h_agl=radar.sensor_height_m_agl,
        z_min=z_min, z_max=pass_max_r, z_res=z_res,
        k_factor=config.get("atmospheric_k_factor"),
        earth_model=config.get("earth_model", {}).get("ellipsoid", "WGS84")
    )
    
    # Attempt Cache Lookup
    cached = cache.get(zone_hash)
    
    if cached is not None:
        mva_cart, transform = cached
        log.info(f"Zone {i+1}: Cache HIT ({zone_hash[:8]}...)")
    else:
        log.info(f"Zone {i+1}: Cache MISS. Computing...")
        
        # --- Existing Logic (DEM Download & Reproject) ---
        dem_array, transform = _reproject_dem_to_aeqd(...)
        
        # --- New: Compute MVA (not binary visibility) ---
        mva_polar = _compute_mva_polar(dem_array, transform, radar_h, pass_max_r, ...)
        mva_cart = _polar_to_cartesian_mva(mva_polar, dem_array.shape, transform, ...)
        
        # --- Save to Cache ---
        aeqd_crs = f"+proj=aeqd +lat_0={radar.latitude} +lon_0={radar.longitude} ..."
        cache.put(zone_hash, mva_cart, transform, aeqd_crs)
        
        del dem_array, mva_polar  # Cleanup
    
    # --- Threshold to get binary mask for THIS target_alt ---
    mask = _threshold_mva_to_mask(mva_cart, target_alt)
    
    # --- Polygonize (existing logic) ---
    poly = _polygonize_mask(mask, transform)
    
    # --- Clip to annulus (existing logic) ---
    ...
    polygons_aeqd.append(clipped_poly)
```

#### 3.3 DEM Download Optimization (Cache Hit Path)
**Critical Insight**: If we have a cache hit, we **skip DEM download entirely** for that zone. This is a major performance win, as DEM download/reprojection is often the slowest step.
*   The `dem_client.ensure_tiles(bbox)` call should be moved *inside* the cache-miss block.

---

### Phase 4: CLI & StateManager Updates
**Files:** `src/rangeplotter/cli/main.py`, `src/rangeplotter/utils/state.py`

#### 4.1 `StateManager` Hash Extension
Extend `StateManager.compute_hash()` to include **styling parameters** so that style changes trigger KML regeneration.

**Current signature:**
```python
def compute_hash(self, site, target_alt, refraction_k, earth_radius_model, max_range, sensor_height_m_agl) -> str
```

**New signature:**
```python
def compute_hash(
    self, site, target_alt, refraction_k, earth_radius_model, max_range, sensor_height_m_agl,
    fill_color: str = None,
    line_color: str = None, 
    fill_opacity: float = None
) -> str
```

**Updated hash string:**
```python
data = f"{site.name}|{site.latitude:.6f}|{site.longitude:.6f}|"
data += f"{h_val}|{sensor_height_m_agl:.2f}|"
data += f"{target_alt:.2f}|{refraction_k:.3f}|"
data += f"{earth_radius_model}|{max_range:.1f}|"
# NEW: Append styling
data += f"{fill_color or 'default'}|{line_color or 'default'}|{fill_opacity or 'default'}"
```

#### 4.2 CLI Updates
**File:** `src/rangeplotter/cli/main.py`

Pass styling parameters when calling `StateManager.compute_hash()`:
```python
current_hash = state_manager.compute_hash(
    sensor, alt, settings.atmospheric_k_factor,
    earth_radius_model=settings.earth_model.type,
    max_range=horizon_m,
    sensor_height_m_agl=sensor_h,
    # NEW
    fill_color=final_style.get('fill_color'),
    line_color=final_style.get('line_color'),
    fill_opacity=final_style.get('fill_opacity')
)
```

#### 4.3 `network run` Command
*   `network run` calls `viewshed` via `subprocess.run()`.
*   It does **not** directly call `compute_viewshed`.
*   Therefore, both cache integrations are automatically inherited.
*   **No changes required to `network.py`.**

#### 4.4 Hash Design Summary
| System | Includes Target Alt? | Includes Styling? | Purpose |
|--------|---------------------|-------------------|--------|
| `ViewshedCache` | ❌ No | ❌ No | Physics reuse across altitudes/styles |
| `StateManager` | ✅ Yes | ✅ Yes | Exact output deduplication |

---

### Phase 5: Configuration
**File:** `config/config.yaml`, `src/rangeplotter/config/settings.py`

#### 5.1 Cache Directory
The cache directory is already configurable via `cache_dir` in `config.yaml` (currently defaults to `data_cache`). The `ViewshedCache` will create a `viewsheds/` subdirectory within it.
*   **No changes required to `config.yaml`.**

#### 5.2 (Optional) Cache Control Flag
Consider adding a `--no-cache` flag to the `viewshed` CLI command for debugging or forcing fresh calculations.
*   **Scope**: Deferred to a follow-up task. For v0.1.7, the cache is always enabled.

---

### Phase 6: Testing

#### 6.1 Unit Tests
**File:** `tests/test_viewshed_cache.py` (New File)
*   Test `ViewshedCache.compute_hash()` for determinism (same inputs = same hash).
*   Test `ViewshedCache.put()` and `get()` round-trip.
*   Test atomic write (simulate concurrent access).

#### 6.2 Integration Tests
**File:** `tests/test_viewshed_integration.py` (Modify)
*   **Test Cache Hit**: Run `compute_viewshed` twice with the same sensor parameters but different `target_alt`. Assert the second call is significantly faster (< 1 second).
*   **Test Cache Miss on Param Change**: Run `compute_viewshed`, then change `sensor_height_m_agl` and run again. Assert a new cache file is created.

#### 6.3 Manual Verification
1.  Run `rangeplotter viewshed -i site.kml -a 100`. Verify `data_cache/viewsheds/<hash>.tif` exists.
2.  Run `rangeplotter viewshed -i site.kml -a 500`. Verify it completes almost instantly (cache hit). Verify **no new** `.tif` file is created.
3.  Run `rangeplotter network run`. Verify multiple workers share the cache without corruption.
4.  Run `rangeplotter detection-range`. Verify significant speedup compared to pre-cache behavior.

---

### Summary of Files Changed

| File | Change Type | Description |
|---|---|---|
| `src/rangeplotter/los/viewshed.py` | **Major Refactor** | Split `_radial_sweep_visibility` into MVA computation, Polar-to-Cartesian conversion, and thresholding. Integrate `ViewshedCache` into zone loop. |
| `src/rangeplotter/io/viewshed_cache.py` | **New File** | `ViewshedCache` class with `compute_hash`, `get`, `put`. |
| `tests/test_viewshed_cache.py` | **New File** | Unit tests for cache. |
| `tests/test_viewshed_integration.py` | **Modify** | Add integration tests for cache behavior. |
| `src/rangeplotter/cli/main.py` | **Minor Update** | Pass styling params to `StateManager.compute_hash()`. |
| `src/rangeplotter/cli/network.py` | **No Change** | Inherits cache via subprocess call to `viewshed`. |
| `src/rangeplotter/utils/state.py` | **Minor Update** | Extend `compute_hash()` to include styling parameters. |
| `config/config.yaml` | **No Change** | Uses existing `cache_dir`. |
