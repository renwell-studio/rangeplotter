# v0.2.0 Implementation Plan: Unified Extensible Viewshed Cache

This document contains the problem statement, solution design, and detailed implementation instructions for fixing the viewshed cache to be target-altitude-independent and incrementally extensible.

**Key sections:**
- [Problem Statement](#problem-statement) — Why the current cache creates too many files
- [High-Level Solution](#high-level-solution) — Three-phase approach overview
- [Architectural Improvements](#architectural-improvements) — Package restructure, separation of concerns
- [Storage Format & Compression](#storage-format--compression) — UInt16 quantization, 0.5m precision, NPZ format
- [Phase 0: Architecture](#phase-0-architecture) — Cache package, MVA module separation
- [Phase 1: Unified Cache](#phase-1-unified-cache) — Altitude-independent cache key
- [Phase 2: Incremental Extension](#phase-2-incremental-extension) — Extend cache instead of recompute, lazy DEM loading
- [Implementation Order](#implementation-order) — Step-by-step task list
- [Migration & Compatibility](#migration--compatibility) — Version bump and backward compat
- [Success Criteria](#success-criteria) — Acceptance tests

---

## Problem Statement

### Observed Behavior

Running `network run` over 4 sensor sites at target altitudes `[10, 50, 100, 500, 1000]` created **20 cache files** instead of the expected **4** (one per sensor).

A subsequent run at 750m target altitude created **4 additional cache files** instead of reusing the existing cached viewsheds.

### Root Cause

The current cache implementation includes **zone boundaries** in the cache hash. Specifically, the outermost zone's maximum radius (`z_max`) is derived from:

```python
max_r = min(cfg.get("max_range_km", 200) * 1000, horizon_m)
```

Where `horizon_m = mutual_horizon_distance(radar_height, target_alt, ...)`.

Since `target_alt` affects `horizon_m`, which affects `z_max`, which is part of the cache hash:
- **Different target altitudes → different Zone 3 boundaries → different cache hashes → cache misses**

### Current Cache Key (Problematic)

```python
key_str = (
    f"{lat:.6f}|{lon:.6f}|"
    f"{sensor_height:.1f}|{k_factor:.4f}|"
    f"{z_min:.1f}|{z_max:.1f}|{z_res:.1f}"  # <-- Problem: z_max varies with target_alt
)
```

### Desired Behavior

1. **Single cache file per sensor location**: One MVA surface per unique (lat, lon, sensor_height, k_factor) combination
2. **Altitude-independent caching**: The cached MVA should be reusable across all target altitudes
3. **Incremental extension**: If a new request requires a larger radius than cached, extend the existing cache rather than recompute from scratch
4. **Minimum computation**: Only compute what's necessary to answer the query
5. **Minimal DEM downloads**: Only fetch DEM tiles for regions not already computed

---

## High-Level Solution

### Three-Phase Implementation

**Phase 0: Architecture (enables clean implementation)**
- Create dedicated `cache/` package for all caching concerns
- Separate MVA computation from cache/orchestration logic
- Establish clean interfaces for Phase 1 and 2

**Phase 1: Unified Cache (fixes immediate issue)**
- Single cache file per sensor location
- Cache key excludes zone/radius information
- Metadata tracks the maximum radius computed so far
- If requested radius > cached radius: recompute entirely to larger radius, replace cache
- If requested radius ≤ cached radius: use cached data, clip to actual horizon at threshold time

**Phase 2: Incremental Extension (optimization)**
- Store horizon state at outer boundary in metadata
- Implement annulus-only computation for extensions
- **Lazy DEM loading**: Only fetch tiles for the extension annulus
- Merge new data with existing MVA surface
- Never recompute already-cached regions

### Cache Structure

```
data_cache/viewshed_cache/
├── {sensor_hash}.npz           # MVA raster data (NumPy compressed)
├── {sensor_hash}.meta.json     # Metadata including max_radius, boundary state
```

Where `sensor_hash` = hash of:
- Latitude (6 decimal places)
- Longitude (6 decimal places)  
- Sensor height AGL (1 decimal place)
- K-factor (4 decimal places)
- Cache version

**NOT included in hash:**
- Target altitude
- Zone boundaries
- Maximum radius

### New Cache Key

```python
key_str = (
    f"v{CACHE_VERSION}|"
    f"{lat:.6f}|{lon:.6f}|"
    f"{sensor_height:.1f}|{k_factor:.4f}"
)
```

---

## Storage Format & Compression

### Problem: Current Cache Files Are Too Large

The current implementation stores MVA rasters as GeoTIFF with Float32 precision and LZW compression. For a typical 200km radius viewshed, this produces files of **100-140 MB per sensor**. With multiple sensors and incremental extension, cache storage becomes unmanageable.

### Solution: Quantized Compressed NPZ

Replace GeoTIFF Float32 with **UInt16 quantized values** stored in **NumPy compressed archives (.npz)**. This achieves:

- **~90% size reduction**: 100-140 MB → 5-15 MB per cache file
- **0.5m altitude precision**: Sufficient for both close-range detection and high-altitude targets
- **Fast I/O**: NumPy's native binary format with built-in compression

### Altitude Encoding Specification

| Property | Value | Rationale |
|----------|-------|-----------|
| **Data type** | UInt16 | 65,536 discrete values |
| **Scale factor** | 0.5 | 0.5m precision per LSB |
| **Offset** | 0 | Zero-based (no negative altitudes needed) |
| **Range** | 0 – 32,767.5 m | Covers 0 to ~32.8 km altitude |
| **NODATA value** | 65535 | Indicates "never visible at any altitude" |

**Encoding formula:**
```python
# Encode: float meters → UInt16
def encode_mva(mva_float: np.ndarray) -> np.ndarray:
    """Quantize MVA values to UInt16 with 0.5m precision."""
    quantized = np.round(mva_float / 0.5).astype(np.uint16)
    quantized[mva_float == np.inf] = 65535  # NODATA
    quantized[quantized > 65534] = 65534    # Clamp to valid range
    return quantized

# Decode: UInt16 → float meters
def decode_mva(mva_uint16: np.ndarray) -> np.ndarray:
    """Restore MVA values from UInt16 encoding."""
    result = mva_uint16.astype(np.float32) * 0.5
    result[mva_uint16 == 65535] = np.inf  # Restore NODATA
    return result
```

### Precision Analysis & Design Rationale

**Why 0.5m precision?**

The MVA (Minimum Visible Altitude) represents the lowest altitude at which a target becomes visible from the sensor. Precision requirements depend on the use case:

1. **Close-range human detection** (security, border surveillance):
   - Person height: ~1.7–2.0m
   - Need to distinguish a crouching person (1.0m) from standing (1.8m)
   - 0.5m precision: ✓ Can represent 1.0m, 1.5m, 2.0m distinctly
   - 2.0m precision: ✗ Would round 1.0m and 1.8m to same value

2. **Low-altitude aircraft** (drones, helicopters):
   - Typical altitudes: 50–500m
   - 0.5m precision: 0.1–1% error (negligible)
   - 2.0m precision: 0.4–4% error (acceptable but less precise)

3. **High-altitude aircraft** (commercial aviation):
   - Typical altitudes: 10,000–15,000m
   - Both 0.5m and 2.0m precision are negligible (<0.02% error)

4. **Space-observation radar** (future use case):
   - Target altitudes: 200–2000+ km
   - These exceed the 32.8km UInt16 range
   - **Resolution:** Space targets are always above terrain obstructions; visibility is determined by geometric horizon only, not MVA lookup. The MVA cache remains useful for low-altitude portions of the coverage area.

**Precision comparison:**

| Scale | Max Altitude | Precision | Close-Range | High-Alt | Space |
|-------|--------------|-----------|-------------|----------|-------|
| 0.5m  | 32.8 km      | ±0.25m    | ✓ Excellent | ✓ Excellent | ✓ N/A |
| 1.0m  | 65.5 km      | ±0.5m     | ○ Marginal  | ✓ Good   | ✓ N/A |
| 2.0m  | 131 km       | ±1.0m     | ✗ Inadequate| ✓ Good   | ✓ N/A |

**Decision: 0.5m precision** — Provides excellent fidelity for the primary use case (detecting small targets at close range) while maintaining more than adequate range for all realistic terrain-constrained scenarios.

### Compression Details

**NPZ format internals:**
- Uses `np.savez_compressed()` which applies ZIP deflate compression
- UInt16 quantization + ZIP typically achieves 15:1 to 20:1 compression vs raw Float32
- Lossless after quantization (no additional precision loss from compression)

**Estimated file sizes:**

| Radius | Raster Size | Float32 Raw | Float32 LZW | UInt16 NPZ |
|--------|-------------|-------------|-------------|------------|
| 50 km  | ~3300×3300  | 44 MB       | 15-25 MB    | 2-4 MB     |
| 100 km | ~6600×6600  | 175 MB      | 50-80 MB    | 5-10 MB    |
| 200 km | ~13200×13200| 700 MB      | 100-150 MB  | 10-20 MB   |

### NPZ File Structure

Each cache file contains:

```python
# Cache file: {sensor_hash}.npz
{
    'mva': np.ndarray,           # (H, W) UInt16 - quantized MVA surface
    'boundary_angles': np.ndarray, # (14400,) Float32 - horizon state (Phase 2)
    'boundary_radius': np.ndarray, # (1,) Float32 - max radius in meters
    'transform': np.ndarray,     # (6,) Float64 - affine transform coefficients
    'crs_wkt': str,              # Coordinate reference system as WKT
}
```

Separate JSON metadata for human-readable info:
```json
{
    "version": "2",
    "sensor_lat": 64.123456,
    "sensor_lon": -21.654321,
    "sensor_height_m": 50.0,
    "k_factor": 1.333,
    "max_radius_m": 150000,
    "quantization_scale": 0.5,
    "nodata_value": 65535,
    "created": "2024-12-03T10:30:00Z",
    "last_extended": "2024-12-03T14:45:00Z"
}
```

### Implementation Steps (Phase 1, Steps 1.0.x)

These steps should be implemented **before** the cache key changes, as they affect the storage layer:

| Step | Description | Details |
|------|-------------|---------|
| 1.0.1 | Add encoding/decoding functions | `encode_mva()`, `decode_mva()` in `viewshed_cache.py` |
| 1.0.2 | Update `put_with_metadata()` | Encode to UInt16 before saving, store transform/CRS |
| 1.0.3 | Update `get_with_metadata()` | Decode from UInt16 after loading, restore transform/CRS |
| 1.0.4 | Remove rasterio/GeoTIFF dependency | Replace with pure NumPy I/O |
| 1.0.5 | Add migration warning | Log warning when loading v1 cache (will be recomputed) |
| 1.0.6 | Update tests | Verify encode/decode round-trip, file size reduction |

**Code implementation:**

```python
# Constants
MVA_SCALE = 0.5  # meters per LSB
MVA_NODATA = 65535  # UInt16 NODATA sentinel

def encode_mva(mva: np.ndarray) -> np.ndarray:
    """Quantize MVA surface to UInt16 with 0.5m precision.
    
    Args:
        mva: Float32 array of minimum visible altitudes in meters.
             Values of np.inf indicate "never visible".
    
    Returns:
        UInt16 array where value * 0.5 = altitude in meters.
        65535 indicates NODATA (never visible).
    """
    # Handle infinities first
    is_nodata = ~np.isfinite(mva)
    
    # Quantize: divide by scale, round to nearest integer
    quantized = np.round(mva / MVA_SCALE).astype(np.float32)
    
    # Clamp to valid range [0, 65534]
    quantized = np.clip(quantized, 0, 65534)
    
    # Convert to UInt16 and apply NODATA
    result = quantized.astype(np.uint16)
    result[is_nodata] = MVA_NODATA
    
    return result


def decode_mva(encoded: np.ndarray) -> np.ndarray:
    """Restore MVA surface from UInt16 encoding.
    
    Args:
        encoded: UInt16 array from cache file.
    
    Returns:
        Float32 array of minimum visible altitudes in meters.
        NODATA values restored to np.inf.
    """
    # Convert to float and scale
    result = encoded.astype(np.float32) * MVA_SCALE
    
    # Restore NODATA as infinity
    result[encoded == MVA_NODATA] = np.inf
    
    return result
```

---

## Architectural Improvements

This rework is an opportunity to improve the codebase structure. The following changes enable cleaner implementation of the cache features and better long-term maintainability.

### A. Cache Package Restructure

**Current state:**
- `src/rangeplotter/io/viewshed_cache.py` — cache lives in `io/` directory
- Cache is tightly coupled to viewshed module
- DEM caching scattered in `DemClient`

**Problem:**
- The `io/` directory is for input/output operations (KML, DEM file parsing)
- Caching is a cross-cutting concern, not I/O
- No unified cache management interface

**Solution:** Create dedicated `cache/` package:
```
src/rangeplotter/cache/
├── __init__.py          # Public exports
├── base.py              # Abstract cache interface (future)
└── viewshed.py          # Viewshed MVA cache (moved from io/)
```

**Benefits:**
- Clear separation of concerns
- Room for future cache types (horizon cache, network results)
- Consistent cache configuration and management
- Easier to add cache statistics, pruning, etc.

### B. Separate MVA Computation from Cache Logic

**Current state:**
- `compute_viewshed()` in `los/viewshed.py` mixes:
  - Cache lookup/store
  - MVA computation (radial sweep)
  - Thresholding for target altitudes
  - Coordinate transforms

**Problem:**
- Hard to test MVA computation in isolation
- Cache logic interleaved with physics
- Extension implementation will add more complexity

**Solution:** Separate into distinct modules:
```
src/rangeplotter/los/
├── mva.py              # Pure MVA computation, no caching
│   ├── compute_mva()           # Full computation
│   ├── compute_mva_extension() # Annulus extension (Phase 2)
│   └── sweep_radial()          # Low-level sweep
├── viewshed.py         # Orchestration with caching
│   └── compute_viewshed()      # High-level API
```

**Benefits:**
- Easier to test MVA computation in isolation
- Cache logic separated from physics
- Cleaner extension implementation
- Better code organization

### C. Lazy DEM Loading for Extensions

**Current state:**
- DEM tiles are fetched for the entire computation region upfront
- When extending a viewshed, tiles for the already-cached region are re-fetched unnecessarily

**Problem:**
- DEM tile download is the slowest operation in the pipeline
- Extending from 100km to 200km re-downloads tiles for 0-100km (wasted)
- Network latency and bandwidth are significant bottlenecks

**Solution:** Bounding-box aware DEM fetching:
```python
def compute_mva_extension(
    existing_mva: np.ndarray,
    boundary_state: np.ndarray,
    inner_radius: float,
    outer_radius: float,
    radar: RadarSite,
    dem_client: DemClient,
    ...
) -> Tuple[np.ndarray, np.ndarray]:
    # Only fetch DEM tiles that intersect the annulus
    annulus_bbox = compute_annulus_bbox(radar.location, inner_radius, outer_radius)
    dem_tiles = dem_client.get_tiles_for_bbox(annulus_bbox)  # NEW: bbox-aware
    
    # Compute only the extension region
    ...
```

**Implementation approach:**
1. Add `get_tiles_for_bbox(bbox)` method to `DemClient`
2. `compute_mva_extension()` computes the annulus bounding box
3. Only tiles intersecting the annulus are fetched
4. Already-cached tiles are still used (DEM cache unchanged)

**Tile intersection logic:**
```python
def compute_annulus_bbox(center: LatLon, inner_r: float, outer_r: float) -> BBox:
    """Compute bounding box of annulus region.
    
    The annulus is the ring between inner_r and outer_r centered on `center`.
    We only need tiles that intersect this ring, not the full circle.
    """
    # Outer boundary determines the max extent
    outer_bbox = buffer_point(center, outer_r)
    
    # Inner circle is excluded, but tiles may still partially intersect
    # For simplicity, fetch tiles in outer_bbox that are NOT entirely within inner_r
    # (A tile entirely within the inner circle contains no annulus points)
    return outer_bbox  # First pass: use outer bbox, optimize later if needed

def tiles_for_annulus(center: LatLon, inner_r: float, outer_r: float, 
                      tile_index: TileIndex) -> List[TileId]:
    """Return tiles that intersect the annulus."""
    outer_bbox = buffer_point(center, outer_r)
    candidates = tile_index.tiles_in_bbox(outer_bbox)
    
    # Filter out tiles entirely within inner circle
    result = []
    for tile in candidates:
        tile_center = tile.center()
        # If any corner of tile is outside inner_r, include it
        if not tile_entirely_within_radius(tile, center, inner_r):
            result.append(tile)
    
    return result
```

**Expected savings:**
- Extending 100km → 200km: ~75% fewer tiles (area ratio)
- Extending 150km → 200km: ~44% fewer tiles
- Critical for Arctic regions with expensive SRTM downloads

---

## Phase 0: Architecture

### Goal

Establish clean code structure before implementing cache features. This phase has no functional changes—only refactoring.

### Changes Required

#### 0.1 Create `cache/` Package

```bash
mkdir -p src/rangeplotter/cache
touch src/rangeplotter/cache/__init__.py
```

#### 0.2 Move Cache Module

```bash
git mv src/rangeplotter/io/viewshed_cache.py src/rangeplotter/cache/viewshed.py
```

#### 0.3 Update Imports

All files importing from `rangeplotter.io.viewshed_cache` must be updated:

```python
# Before
from rangeplotter.io.viewshed_cache import ViewshedCache

# After
from rangeplotter.cache.viewshed import ViewshedCache
```

Files to update:
- `src/rangeplotter/los/viewshed.py`
- `tests/test_viewshed_cache.py`
- `tests/test_viewshed_integration.py`
- Any CLI modules using cache

#### 0.4 Create `cache/__init__.py`

```python
"""Cache management for RangePlotter."""

from .viewshed import ViewshedCache

__all__ = ["ViewshedCache"]
```

#### 0.5 Create `los/mva.py`

Extract pure MVA computation functions:

```python
"""Minimum Visible Altitude (MVA) computation.

This module contains the core algorithms for computing MVA surfaces.
No caching logic—pure computation only.
"""

import numpy as np
from typing import Tuple, Optional

from ..dem import DemClient
from ..models import RadarSite


def compute_mva(
    radar: RadarSite,
    dem: DemClient,
    max_radius: float,
    zones: list,
    k_factor: float = 1.333,
) -> Tuple[np.ndarray, np.ndarray, dict]:
    """Compute full MVA surface from sensor to max_radius.
    
    Args:
        radar: Sensor configuration
        dem: DEM data source
        max_radius: Maximum radius in meters
        zones: Zone configuration for multiscale computation
        k_factor: Atmospheric refraction factor
        
    Returns:
        mva: (H, W) Float32 array of minimum visible altitudes
        boundary_angles: (n_az,) Float32 array of horizon angles at max_radius
        geo_info: Dict with 'transform' and 'crs' for georeferencing
    """
    # Implementation moved from viewshed.py
    ...


def compute_mva_extension(
    existing_mva: np.ndarray,
    boundary_angles: np.ndarray,
    inner_radius: float,
    outer_radius: float,
    radar: RadarSite,
    dem: DemClient,
    zones: list,
    k_factor: float = 1.333,
) -> Tuple[np.ndarray, np.ndarray, dict]:
    """Extend existing MVA surface from inner_radius to outer_radius.
    
    Only computes the annulus region and merges with existing data.
    Only fetches DEM tiles for the annulus (not the inner cached region).
    
    Args:
        existing_mva: Cached MVA surface
        boundary_angles: Horizon state at inner_radius (from cache)
        inner_radius: Start of extension (= cached max_radius)
        outer_radius: End of extension (= new required radius)
        radar: Sensor configuration
        dem: DEM data source (will only fetch tiles for annulus)
        zones: Zone configuration
        k_factor: Atmospheric refraction factor
        
    Returns:
        extended_mva: Merged MVA surface covering 0 to outer_radius
        new_boundary_angles: Horizon state at outer_radius
        geo_info: Updated georeferencing for extended surface
    """
    # Implementation in Phase 2
    ...
```

#### 0.6 Refactor `viewshed.py` to Use `mva.py`

```python
# los/viewshed.py - becomes orchestration layer

from .mva import compute_mva, compute_mva_extension
from ..cache.viewshed import ViewshedCache

def compute_viewshed(
    radar: RadarSite,
    target_alts: list,
    dem: DemClient,
    cache: Optional[ViewshedCache] = None,
    ...
) -> List[VisibilityResult]:
    """Compute viewshed with caching support.
    
    This is the high-level API that:
    1. Checks cache for existing MVA
    2. Computes or extends MVA as needed (delegating to mva.py)
    3. Thresholds MVA for each target altitude
    4. Returns visibility results
    """
    ...
```

#### 0.7 Update Tests

Ensure all tests pass after refactoring:
- Update import paths
- Add basic tests for new module structure
- Verify no functional changes

---

## Phase 1: Unified Cache

### Goal

Fix the cache so that:
1. Only one cache file exists per sensor location
2. Cache is reused regardless of target altitude
3. Cache grows to accommodate larger radius requests

### Changes Required

#### 1. Modify `ViewshedCache` class (`src/rangeplotter/cache/viewshed.py`)

**1.1 Update `compute_hash()` to exclude zone parameters:**

```python
@staticmethod
def compute_hash(
    lat: float,
    lon: float, 
    sensor_height: float,
    k_factor: float = 1.333,
) -> str:
    """Compute cache key for a sensor location.
    
    The hash is independent of target altitude and zone boundaries,
    allowing the same cache to be reused across different queries.
    """
    key_str = (
        f"v{ViewshedCache.CACHE_VERSION}|"
        f"{lat:.6f}|{lon:.6f}|"
        f"{sensor_height:.1f}|{k_factor:.4f}"
    )
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]
```

**1.2 Update metadata structure:**

```python
metadata = {
    "version": CACHE_VERSION,
    "sensor_lat": lat,
    "sensor_lon": lon,
    "sensor_height_m": sensor_height,
    "k_factor": k_factor,
    "max_radius_m": max_radius,  # Maximum radius computed so far
    "created": timestamp,
    "last_updated": timestamp,
}
```

**1.3 Add `get_with_metadata()` method:**

```python
def get_with_metadata(self, cache_key: str) -> Tuple[Optional[np.ndarray], Optional[dict]]:
    """Retrieve cached MVA and its metadata."""
    # Returns (mva_array, metadata) or (None, None) if not found
```

**1.4 Add `put_with_metadata()` method:**

```python
def put_with_metadata(self, cache_key: str, mva: np.ndarray, metadata: dict) -> None:
    """Store MVA with associated metadata."""
```

#### 2. Modify `compute_viewshed()` (`src/rangeplotter/los/viewshed.py`)

**2.1 Change cache lookup logic:**

```python
def compute_viewshed(...):
    # Compute required radius based on maximum target altitude in request
    max_target_alt = max(target_alts) if isinstance(target_alts, list) else target_alts
    required_radius = mutual_horizon_distance(radar_height, max_target_alt, lat, k_factor)
    required_radius = min(required_radius, cfg.get("max_range_km", 200) * 1000)
    
    # Compute cache key (altitude-independent)
    cache_key = ViewshedCache.compute_hash(lat, lon, sensor_height, k_factor)
    
    # Check cache
    cached_mva, cached_meta = cache.get_with_metadata(cache_key)
    
    if cached_mva is not None:
        cached_radius = cached_meta.get("max_radius_m", 0)
        if cached_radius >= required_radius:
            # Cache HIT - use as-is
            log.debug(f"Cache hit: cached_radius={cached_radius}m >= required={required_radius}m")
            mva = cached_mva
        else:
            # Cache exists but insufficient radius - recompute to larger radius (Phase 1)
            # Phase 2 will extend instead of recompute
            log.info(f"Cache radius insufficient: {cached_radius}m < {required_radius}m. Recomputing...")
            mva = _compute_mva_full(radar, dem, required_radius, ...)
            cache.put_with_metadata(cache_key, mva, {
                "max_radius_m": required_radius,
                ...
            })
    else:
        # No cache - compute fresh
        mva = _compute_mva_full(radar, dem, required_radius, ...)
        cache.put_with_metadata(cache_key, mva, {...})
    
    # Threshold and clip for each target altitude
    results = []
    for target_alt in target_alts:
        horizon_r = mutual_horizon_distance(radar_height, target_alt, lat, k_factor)
        visible = (mva <= target_alt)  # Threshold
        visible = _clip_to_radius(visible, horizon_r)  # Clip to actual horizon
        results.append(visible)
    
    return results
```

**2.2 Refactor zone computation into `_compute_mva_full()`:**

Extract the existing multiscale zone logic into a dedicated function that:
- Takes `max_radius` as parameter (not derived from target altitude internally)
- Returns the full MVA surface

#### 3. Update `_signal_handler` cleanup

Ensure temporary files follow new naming convention.

#### 4. Update Tests

**4.1 New test: `tests/test_viewshed_cache_unified.py`**

```python
def test_cache_reused_across_altitudes():
    """Cache should be reused regardless of target altitude."""
    # First request at 100m altitude
    result1 = compute_viewshed(sensor, target_alt=100, cache=cache)
    assert cache.stats()["entries"] == 1
    
    # Second request at 500m altitude (same sensor)
    result2 = compute_viewshed(sensor, target_alt=500, cache=cache)
    assert cache.stats()["entries"] == 1  # Still just 1 entry
    
def test_cache_extends_for_larger_radius():
    """Cache should be replaced when larger radius needed."""
    # First request at 100m (small radius)
    compute_viewshed(sensor, target_alt=100, cache=cache)
    meta1 = cache.get_metadata(cache_key)
    
    # Second request at 10000m (larger radius needed)
    compute_viewshed(sensor, target_alt=10000, cache=cache)
    meta2 = cache.get_metadata(cache_key)
    
    assert meta2["max_radius_m"] > meta1["max_radius_m"]
    assert cache.stats()["entries"] == 1  # Still just 1 entry

def test_cache_not_extended_for_smaller_radius():
    """Cache should not change when smaller radius sufficient."""
    # First request at 10000m (large radius)
    compute_viewshed(sensor, target_alt=10000, cache=cache)
    meta1 = cache.get_metadata(cache_key)
    
    # Second request at 100m (smaller radius sufficient)
    compute_viewshed(sensor, target_alt=100, cache=cache)
    meta2 = cache.get_metadata(cache_key)
    
    assert meta2["max_radius_m"] == meta1["max_radius_m"]  # Unchanged
```

**4.2 Update existing cache tests to reflect new hash signature**

#### 5. Documentation Updates

**5.1 Update `docs/guide/features.md` - Data Caching section:**

```markdown
### Viewshed MVA Cache

RangePlotter caches the Minimum Visible Altitude (MVA) surface for each sensor 
location. This cache is **independent of target altitude**, meaning:

- A viewshed computed at 100m target altitude can be reused for 500m, 1000m, etc.
- The cache automatically extends when a larger radius is needed
- Only one cache file exists per sensor location

**Cache Key Components:**
- Sensor latitude/longitude (6 decimal places)
- Sensor height AGL
- Atmospheric refraction factor (k)

**NOT included in cache key:**
- Target altitude (thresholding happens at query time)
- Zone boundaries (determined by cached radius)
```

**5.2 Update CHANGELOG.md**

---

## Phase 2: Incremental Extension

### Goal

When a larger radius is needed, **extend** the existing cache rather than recompute from scratch. This requires:

1. Storing the "horizon state" at the outer boundary of the cached region
2. Computing only the annulus (ring) between cached radius and required radius
3. Merging the extension with the existing MVA

### Background: Radial Sweep Algorithm

The viewshed algorithm performs a radial sweep from the sensor outward:

```
For each azimuth angle (0° to 360°):
    max_elevation_angle = -∞
    For each distance step (0 to max_radius):
        terrain_elevation = DEM[point]
        elevation_angle = atan2(terrain_elevation - sensor_elevation, distance)
        
        if elevation_angle > max_elevation_angle:
            max_elevation_angle = elevation_angle
            MVA[point] = target_altitude_at_this_angle
        else:
            MVA[point] = ∞  # Not visible at any altitude
```

**Key insight:** To extend the sweep beyond `cached_radius`, we need to know `max_elevation_angle` at `cached_radius` for each azimuth. This is the "horizon state".

### Storage Format: NPZ with Boundary State

Store everything in a single `.npz` file (NumPy compressed archive):

```python
# Save cache
np.savez_compressed(
    cache_path,
    mva=mva_surface,                      # (H, W) float32 - the MVA raster
    boundary_angles=max_elevation_angles, # (14400,) float32 - fixed resolution
    boundary_radius=np.array([max_radius], dtype=np.float32),
)

# Load cache
data = np.load(cache_path)
mva = data['mva']
boundary_angles = data['boundary_angles']
boundary_radius = float(data['boundary_radius'][0])
```

**Why NPZ?**
- Binary format, compact (~5-20 KB for boundary state after compression)
- Already using NPZ for MVA storage
- Fast load/save with NumPy
- Single file per sensor (no separate metadata file needed for Phase 2)

**Separate JSON metadata** is kept for human-readable info:
```json
{
    "version": "2",
    "sensor_lat": 64.123456,
    "sensor_lon": -21.654321,
    "sensor_height_m": 50.0,
    "k_factor": 1.333,
    "max_radius_m": 150000,
    "created": "2024-12-03T10:30:00Z",
    "last_extended": "2024-12-03T14:45:00Z"
}
```

### Fixed Azimuth Resolution for Boundary State

The boundary state is **always stored at 14,400 azimuths** (0.025° resolution), regardless of the azimuth count used during computation. This provides:

1. **Consistency**: Same storage format for all cache entries
2. **Future-proofing**: Can extend to any radius without resolution mismatch
3. **Minimal overhead**: 14,400 × 4 bytes = 57.6 KB uncompressed, ~15-20 KB compressed

**Resolution handling during extension:**
- If MVA was computed with fewer azimuths (e.g., 10,000), interpolate boundary angles up to 14,400 before storing
- When extending, interpolate boundary angles down to match the extension computation's azimuth count
- This ensures the boundary state is always compatible with any future extension

```python
BOUNDARY_STATE_AZIMUTHS = 14400  # Fixed resolution for boundary storage

def _normalize_boundary_angles(angles: np.ndarray) -> np.ndarray:
    """Interpolate boundary angles to fixed 14,400 resolution."""
    if len(angles) == BOUNDARY_STATE_AZIMUTHS:
        return angles
    # Linear interpolation to fixed resolution
    x_old = np.linspace(0, 2*np.pi, len(angles), endpoint=False)
    x_new = np.linspace(0, 2*np.pi, BOUNDARY_STATE_AZIMUTHS, endpoint=False)
    return np.interp(x_new, x_old, angles, period=2*np.pi)
```

The `max_elevation_angles` array stores the running maximum elevation angle at the outer boundary for each azimuth direction. This allows the sweep to continue outward from any cached radius.

### Changes Required

#### 1. Update NPZ save/load to include boundary state

Building on the Phase 1 storage format, add boundary state arrays:

```python
# In ViewshedCache.put_with_metadata():
np.savez_compressed(
    npz_path,
    mva=encode_mva(mva_surface),  # UInt16 quantized (from Phase 1)
    boundary_angles=_normalize_boundary_angles(boundary_angles),  # (14400,) Float32
    boundary_radius=np.array([max_radius], dtype=np.float32),
    transform=transform_coeffs,   # (6,) Float64 - affine transform
    crs_wkt=crs_wkt,              # str - coordinate reference system
)

# In ViewshedCache.get_with_metadata():
data = np.load(npz_path)
mva = decode_mva(data['mva'])         # Decode UInt16 → Float32
boundary_angles = data['boundary_angles']  # Always 14400 elements
boundary_radius = float(data['boundary_radius'][0])
transform = data['transform']
crs_wkt = str(data['crs_wkt'])
```


#### 2. Implement `_compute_mva_extension()`

```python
BOUNDARY_STATE_AZIMUTHS = 14400

def _compute_mva_extension(
    existing_mva: np.ndarray,
    boundary_angles: np.ndarray,  # Shape: (14400,)
    inner_radius: float,
    outer_radius: float,
    radar: RadarSite,
    dem: DemClient,
    cfg: dict,
) -> Tuple[np.ndarray, np.ndarray]:
    """Compute MVA for annulus and merge with existing.
    
    Args:
        existing_mva: The cached MVA surface (Cartesian)
        boundary_angles: Max elevation angles at inner_radius (14400 azimuths)
        inner_radius: Start of annulus (= cached max_radius)
        outer_radius: End of annulus (= new required radius)
        radar: Sensor configuration
        dem: DEM data source
        cfg: Zone configuration
        
    Returns:
        extended_mva: Merged MVA surface covering 0 to outer_radius
        new_boundary_angles: Horizon state at outer_radius (14400 azimuths)
    """
    # 1. Determine zone configuration for the extension region
    extension_zones = _get_zones_for_range(inner_radius, outer_radius, cfg)
    
    # 2. Determine azimuth count for extension computation
    #    (based on outer_radius, same logic as full computation)
    pixel_size = cfg.get("pixel_size", 30)
    circumference = 2 * np.pi * outer_radius
    n_az = min(int(np.ceil(circumference / pixel_size)), 14400)
    
    # 3. Interpolate boundary angles to match computation resolution
    working_angles = _interpolate_boundary_angles(boundary_angles, n_az)
    
    # 4. Compute MVA for extension region only
    extension_mva, new_working_angles = _sweep_annulus(
        radar, dem, 
        inner_radius, outer_radius,
        working_angles,  # Starting horizon angles
        n_az,
        extension_zones
    )
    
    # 5. Merge extension with existing MVA (both in Cartesian)
    extended_mva = _merge_mva_cartesian(existing_mva, extension_mva, inner_radius, outer_radius)
    
    # 6. Normalize new boundary angles back to 14400 for storage
    new_boundary_angles = _normalize_boundary_angles(new_working_angles)
    
    return extended_mva, new_boundary_angles

def _interpolate_boundary_angles(angles_14400: np.ndarray, target_count: int) -> np.ndarray:
    """Interpolate from fixed 14400 resolution to computation resolution."""
    if target_count == 14400:
        return angles_14400
    x_old = np.linspace(0, 2*np.pi, 14400, endpoint=False)
    x_new = np.linspace(0, 2*np.pi, target_count, endpoint=False)
    return np.interp(x_new, x_old, angles_14400, period=2*np.pi)
```

#### 3. Implement `_sweep_annulus()`

```python
def _sweep_annulus(
    radar: RadarSite,
    dem: DemClient,
    inner_r: float,
    outer_r: float,
    starting_angles: np.ndarray,
    n_az: int,
    zones: List[dict],
) -> Tuple[np.ndarray, np.ndarray]:
    """Perform radial sweep for annulus region only.
    
    This is similar to the existing sweep but:
    - Starts at inner_r instead of 0
    - Uses starting_angles as initial max_elevation_angle per azimuth
    - Only outputs MVA values for points between inner_r and outer_r
    
    Returns:
        extension_mva: MVA values for annulus region (polar coordinates)
        final_angles: Max elevation angles at outer_r
    """
    # Implementation details...
```

#### 4. Update `compute_viewshed()` to use extension

```python
if cached_mva is not None:
    cached_radius = cached_meta.get("max_radius_m", 0)
    if cached_radius >= required_radius:
        # Cache HIT
        mva = cached_mva
        boundary_angles = cached_boundary_angles
    else:
        # EXTEND cache (Phase 2)
        if cached_boundary_angles is None:
            # Legacy cache without boundary state - must recompute
            log.info("Legacy cache without boundary state. Recomputing...")
            mva, boundary_angles = _compute_mva_full(...)
        else:
            # Extend existing cache
            log.info(f"Extending cache from {cached_radius}m to {required_radius}m")
            mva, boundary_angles = _compute_mva_extension(
                cached_mva, 
                cached_boundary_angles,  # np.ndarray shape (14400,)
                inner_radius=cached_radius,
                outer_radius=required_radius,
                ...
            )
        
        # Save with updated boundary state
        cache.put_with_metadata(cache_key, mva, boundary_angles, {
            "max_radius_m": required_radius,
            ...
        })
```

#### 5. Coordinate System Considerations

The current implementation uses polar coordinates for the sweep, then converts to Cartesian for the output. For extension:

**Option A: Store MVA in polar coordinates**
- Easier to extend (just append more radial samples)
- Convert to Cartesian only at final output stage
- Requires changing storage format

**Option B: Store MVA in Cartesian, convert for extension**
- Keep current format
- Extract boundary angles from Cartesian MVA
- Merge extension in Cartesian space
- More complex coordinate transformations

**Recommendation:** Option A is cleaner for extension but requires more refactoring. For Phase 2, we can start with Option B and optimize later.

#### 6. Lazy DEM Loading for Annulus

**Critical optimization:** DEM tile download is the slowest operation. When extending a cache, we must only fetch tiles for the annulus region.

**Implementation:**

```python
# In los/mva.py

def compute_mva_extension(
    existing_mva: np.ndarray,
    boundary_angles: np.ndarray,
    inner_radius: float,
    outer_radius: float,
    radar: RadarSite,
    dem_client: DemClient,
    zones: list,
    k_factor: float = 1.333,
) -> Tuple[np.ndarray, np.ndarray, dict]:
    """Extend MVA surface, fetching only annulus DEM tiles."""
    
    # 1. Compute bounding box for annulus region only
    annulus_bbox = _compute_annulus_bbox(
        radar.location, 
        inner_radius, 
        outer_radius
    )
    
    # 2. Fetch DEM tiles for annulus only (not inner cached region)
    dem_mosaic = dem_client.get_mosaic_for_bbox(
        annulus_bbox,
        exclude_inner_radius=inner_radius,  # NEW: skip tiles entirely within
        center=radar.location
    )
    
    # 3. Perform sweep from inner_radius to outer_radius
    # ... rest of extension logic
```

**DemClient changes:**

```python
# In dem/client.py

def get_mosaic_for_bbox(
    self,
    bbox: BBox,
    exclude_inner_radius: Optional[float] = None,
    center: Optional[LatLon] = None,
) -> np.ndarray:
    """Fetch and mosaic DEM tiles for bounding box.
    
    Args:
        bbox: Bounding box to cover
        exclude_inner_radius: If set, skip tiles entirely within this radius of center
        center: Center point for exclusion radius
        
    Returns:
        Mosaiced DEM array covering bbox
    """
    tiles = self._get_tile_ids_for_bbox(bbox)
    
    if exclude_inner_radius is not None and center is not None:
        # Filter out tiles entirely within inner radius
        tiles = [t for t in tiles 
                 if not self._tile_entirely_within_radius(t, center, exclude_inner_radius)]
    
    return self._fetch_and_mosaic(tiles)


def _tile_entirely_within_radius(
    self, 
    tile_id: str, 
    center: LatLon, 
    radius: float
) -> bool:
    """Check if all corners of tile are within radius of center."""
    tile_bounds = self._get_tile_bounds(tile_id)
    corners = [
        (tile_bounds.north, tile_bounds.west),
        (tile_bounds.north, tile_bounds.east),
        (tile_bounds.south, tile_bounds.west),
        (tile_bounds.south, tile_bounds.east),
    ]
    
    for lat, lon in corners:
        dist = haversine_distance(center.lat, center.lon, lat, lon)
        if dist > radius:
            return False  # At least one corner outside radius
    
    return True  # All corners within radius → skip this tile
```

**Annulus bounding box computation:**

```python
def _compute_annulus_bbox(
    center: LatLon,
    inner_radius: float,
    outer_radius: float,
) -> BBox:
    """Compute bounding box that covers the annulus.
    
    The full bounding box is determined by outer_radius.
    Tile filtering handles the inner exclusion.
    """
    # Use outer radius to determine extent
    # (Tile filtering will exclude tiles entirely within inner_radius)
    return buffer_point_to_bbox(center, outer_radius)
```

**Expected performance gains:**

| Extension | Tiles (Full) | Tiles (Annulus) | Savings |
|-----------|--------------|-----------------|---------|
| 50km → 100km | ~25 | ~19 | 24% |
| 100km → 150km | ~56 | ~31 | 45% |
| 100km → 200km | ~100 | ~75 | 25% |
| 150km → 200km | ~100 | ~44 | 56% |

**Note:** Actual savings depend on sensor location and tile grid alignment. Arctic regions (SRTM coverage edge) benefit most due to expensive tile downloads.

**Tests for lazy DEM loading:**

```python
def test_extension_fetches_fewer_tiles():
    """Extension should fetch fewer DEM tiles than full computation."""
    # Track tile fetches
    tile_tracker = TileFetchTracker(dem_client)
    
    # Compute at 100km radius
    compute_viewshed(sensor, target_alt=1000, cache=cache, dem=tile_tracker)
    full_tiles = tile_tracker.tiles_fetched
    tile_tracker.reset()
    
    # Extend to 150km radius
    compute_viewshed(sensor, target_alt=5000, cache=cache, dem=tile_tracker)
    extension_tiles = tile_tracker.tiles_fetched
    
    # Extension should fetch significantly fewer tiles
    # (Only tiles for 100-150km annulus, not 0-150km full circle)
    assert len(extension_tiles) < len(full_tiles) * 0.6


def test_extension_skips_inner_tiles():
    """Extension should not re-fetch tiles entirely within cached radius."""
    # Compute at 100km
    compute_viewshed(sensor, target_alt=1000, cache=cache)
    
    # Mock DEM client to track fetches
    mock_dem = MockDemClient()
    
    # Extend to 150km
    compute_viewshed(sensor, target_alt=5000, cache=cache, dem=mock_dem)
    
    # Verify no tiles fetched that are entirely within 100km of sensor
    for tile_id in mock_dem.fetched_tiles:
        bounds = mock_dem.get_tile_bounds(tile_id)
        assert not tile_entirely_within_radius(bounds, sensor.location, 100_000)
```

#### 7. Documentation Updates

Update `docs/guide/features.md`:

```markdown
### Incremental Cache Extension

When a viewshed request requires a larger radius than what's cached, RangePlotter 
**extends** the existing cache rather than recomputing from scratch:

1. The cached MVA surface covers radius 0 to R₁
2. New request requires radius 0 to R₂ (where R₂ > R₁)
3. RangePlotter computes only the annulus from R₁ to R₂
4. The extension is merged with the cached data
5. Cache is updated to cover 0 to R₂

This means:
- Running viewsheds at increasing altitudes only computes the incremental difference
- Previously computed regions are never recomputed
- Cache file grows to accommodate the largest radius requested

**Example:**
- First run: 100m target alt → computes ~130km radius
- Second run: 500m target alt → extends from 130km to ~200km (only computes the outer ring)
- Third run: 50m target alt → uses cached data, no computation needed
```

---

## Implementation Order

### Phase 0 (Priority: Critical — Do First)

Architectural changes that enable clean implementation of subsequent phases:

| Step | Description | Files |
|------|-------------|-------|
| 0.1 | Create `src/rangeplotter/cache/` directory | - |
| 0.2 | Create `cache/__init__.py` with public exports | `cache/__init__.py` |
| 0.3 | Move `io/viewshed_cache.py` → `cache/viewshed.py` | `cache/viewshed.py` |
| 0.4 | Update all imports referencing old location | Multiple |
| 0.5 | Create `los/mva.py` with pure computation functions | `los/mva.py` |
| 0.6 | Move `_compute_mva_polar()` and sweep logic to `mva.py` | `los/mva.py`, `los/viewshed.py` |
| 0.7 | Refactor `viewshed.py` to import from `mva.py` | `los/viewshed.py` |
| 0.8 | Run tests — verify no functional changes | - |

### Phase 1 (Priority: Critical)

Storage format changes come first, as they affect all subsequent cache operations:

| Step | Description | Files |
|------|-------------|-------|
| **Storage Format** | | |
| 1.0.1 | Add `encode_mva()` / `decode_mva()` functions | `cache/viewshed.py` |
| 1.0.2 | Add `MVA_SCALE = 0.5` and `MVA_NODATA = 65535` constants | `cache/viewshed.py` |
| 1.0.3 | Implement NPZ save with UInt16 encoding + transform/CRS | `cache/viewshed.py` |
| 1.0.4 | Implement NPZ load with UInt16 decoding | `cache/viewshed.py` |
| 1.0.5 | Remove rasterio/GeoTIFF dependency from cache module | `cache/viewshed.py` |
| 1.0.6 | Add encode/decode unit tests + file size assertions | `tests/test_viewshed_cache.py` |
| **Unified Cache** | | |
| 1.1 | Update `compute_hash()` to exclude zone params | `cache/viewshed.py` |
| 1.2 | Add `get_with_metadata()` / `put_with_metadata()` methods | `cache/viewshed.py` |
| 1.3 | Refactor `compute_viewshed()` to use new cache logic | `los/viewshed.py` |
| 1.4 | Update existing cache tests | `tests/test_viewshed_cache.py` |
| 1.5 | Add new unified cache tests | `tests/test_viewshed_cache_unified.py` |
| 1.6 | Update documentation | `docs/guide/features.md` |
| 1.7 | Update CHANGELOG | `CHANGELOG.md` |
| 1.8 | Run full test suite | - |

### Phase 2 (Priority: High)

| Step | Description | Files |
|------|-------------|-------|
| **Boundary State & Extension** | | |
| 2.1 | Add boundary state arrays to NPZ structure | `cache/viewshed.py` |
| 2.2 | Add `_normalize_boundary_angles()` / `_interpolate_boundary_angles()` | `los/mva.py` |
| 2.3 | Implement `compute_mva_extension()` skeleton | `los/mva.py` |
| 2.4 | Implement `_sweep_annulus()` | `los/mva.py` |
| 2.5 | Implement `_merge_mva_cartesian()` | `los/mva.py` |
| **Lazy DEM Loading** | | |
| 2.6 | Add `_compute_annulus_bbox()` helper | `los/mva.py` |
| 2.7 | Add `get_mosaic_for_bbox(exclude_inner_radius=...)` to DemClient | `dem/client.py` |
| 2.8 | Add `_tile_entirely_within_radius()` helper | `dem/client.py` |
| 2.9 | Integrate lazy DEM loading into `compute_mva_extension()` | `los/mva.py` |
| 2.10 | Add tile-fetch tracking tests | `tests/test_dem_lazy.py` |
| **Integration** | | |
| 2.11 | Update `compute_viewshed()` to use extension when beneficial | `los/viewshed.py` |
| 2.12 | Add extension correctness tests | `tests/test_viewshed_cache_extension.py` |
| 2.13 | Add extension performance benchmarks | `tests/test_viewshed_cache_extension.py` |
| 2.14 | Update documentation | `docs/guide/features.md` |
| 2.15 | Update CHANGELOG | `CHANGELOG.md` |
| 2.16 | Run full test suite + verify performance gains | - |

---

## Migration & Compatibility

### Cache Version Bump

Increment `CACHE_VERSION` from `"1"` to `"2"` to invalidate old caches automatically.

### Backward Compatibility

- Old cache files (v1) will be ignored (version mismatch)
- Users will see a one-time recomputation for cached locations
- No data loss; old caches can be manually deleted to reclaim space

### Clear Cache Command

Add guidance to run `rangeplotter cache clear` after upgrade to remove obsolete v1 cache files.

---

## Success Criteria

### Phase 0

- [ ] `cache/` package exists with `ViewshedCache` exported
- [ ] `los/mva.py` exists with `compute_mva()` function
- [ ] `los/viewshed.py` imports from `mva.py` for computation
- [ ] All existing tests pass (no functional changes)
- [ ] No imports from `rangeplotter.io.viewshed_cache`

### Phase 1

**Storage Format:**
- [ ] `encode_mva()` / `decode_mva()` round-trip preserves values to 0.5m precision
- [ ] NODATA (infinity) values correctly encoded as 65535 and restored
- [ ] Cache files are NPZ format, <20 MB for 200km radius viewshed
- [ ] No rasterio dependency in cache module

**Unified Cache:**
- [ ] Running `network run` over 4 sensors at 5 altitudes creates exactly 4 cache files
- [ ] Subsequent run at different altitude reuses existing cache (no new files)
- [ ] All existing tests pass
- [ ] New unified cache tests pass

### Phase 2

**Extension:**
- [ ] Extending cache is faster than recomputing (at least 2x for typical extensions)
- [ ] Extended MVA matches full recomputation (within 0.5m tolerance)
- [ ] Boundary state stored at fixed 14,400 azimuth resolution
- [ ] Extension tests pass

**Lazy DEM Loading:**
- [ ] `DemClient.get_mosaic_for_bbox()` supports `exclude_inner_radius` parameter
- [ ] Extension from 100km→150km fetches <60% of tiles vs full 150km computation
- [ ] No tiles entirely within cached radius are fetched during extension
- [ ] Lazy DEM loading tests pass

**Documentation:**
- [ ] `docs/guide/features.md` updated with cache extension documentation
- [ ] CHANGELOG updated
