# v0.1.7 Implementation Plan

This document contains detailed implementation instructions for v0.1.7 items.

---

## Changes

### C2: Enable tab completion in install.sh

**Status:** Ready to implement

**Change:**
Find all `read -p` prompts for directory/file paths and change to `read -e -p` for readline support.

**Files to Modify:**
- `install.sh`

**Effort:** Trivial

---

### C3: Ctrl-C Signal Handling

**Status:** Ready to implement

**Behavior:**
1. **First Ctrl-C**: Print message and set graceful shutdown flag
   - Message: `"\n[yellow]Interrupt received. Finishing current operation... Press Ctrl-C again to force quit.[/yellow]"`
   - Complete current zone/operation, then exit cleanly
   - Clean up any partial cache files (`.tmp.*` files in viewshed cache)
2. **Second Ctrl-C**: Immediate termination
   - Exit immediately with cleanup of temp files

**Implementation:**

1. **Add signal handler in `main.py`:**
   ```python
   import signal
   
   _shutdown_requested = False
   _force_quit = False
   
   def _signal_handler(signum, frame):
       global _shutdown_requested, _force_quit
       if _shutdown_requested:
           _force_quit = True
           print("\n[red]Force quit. Cleaning up...[/red]")
           _cleanup_temp_cache_files()
           raise SystemExit(1)
       else:
           _shutdown_requested = True
           print("\n[yellow]Interrupt received. Finishing current operation... Press Ctrl-C again to force quit.[/yellow]")
   
   def _cleanup_temp_cache_files():
       """Remove any .tmp.* files from viewshed cache directory."""
       # Read cache_dir from settings, use hardcoded subfolders
       try:
           settings = load_settings()
           cache_dir = Path(settings.cache_dir) / "viewsheds"
       except Exception:
           cache_dir = Path("data_cache/viewsheds")
       
       if cache_dir.exists():
           for tmp_file in cache_dir.glob("*.tmp.*"):
               try:
                   tmp_file.unlink()
               except OSError:
                   pass
   ```

2. **Register handler at start of long-running commands:**
   ```python
   signal.signal(signal.SIGINT, _signal_handler)
   ```

3. **Check flag in processing loops:**
   - In `viewshed.py` zone loop: check `_shutdown_requested` after each zone
   - In `main.py` sensor/altitude loops: check before starting next item
   - If flag is set, clean up and exit gracefully

4. **Cleanup on exit:**
   - Call `_cleanup_temp_cache_files()` before exiting
   - Ensure atomic writes (already using `.tmp.*` + rename pattern)

**Files to Modify:**
- `src/rangeplotter/cli/main.py` - signal handler, cleanup function, flag checks
- `src/rangeplotter/los/viewshed.py` - check shutdown flag between zones

**Effort:** Medium

---

### C5: `--altitude` flag (with `--altitudes` as hidden alias)

**Status:** Ready to implement (user has specified behavior)

**Changes:**
1. Rename `--altitudes` to `--altitude` as the primary flag
2. Keep `--altitudes` as a hidden alias for backward compatibility
3. Support accumulation: `-a 100 -a 500` should work

**Files to Modify:**
- `src/rangeplotter/cli/main.py` - viewshed command options

**Effort:** Trivial

---

## Fixes

### F1: `horizon` outputs single file with `--no-union` in `network run`

**Status:** Investigation needed

**Investigation:**
1. Check if `horizon` command supports `--no-union` flag
2. Check if `network run` passes `--no-union` to horizon subprocess

**Expected Behavior:**
With `--no-union`, each sensor gets its own horizon KML file following the standard naming convention (see F2).

**Files to Modify:**
- `src/rangeplotter/cli/network.py` - pass `--no-union` to horizon subprocess
- `src/rangeplotter/cli/main.py` (horizon command) - implement `--no-union` if missing

**Effort:** Low-Medium

---

### F2: Consistent Output Naming Convention

**Status:** Ready to implement

**Current State (Audit):**

| Command | Current Naming | Issues |
|---------|---------------|--------|
| `viewshed` | `{prefix}rangeplotter-{name}{sh_suffix}-tgt_alt_{alt}m_{ref}.kml` | ✅ Good pattern |
| `horizon` | `horizons.kml` (single file) | ❌ No per-sensor files, no prefix |
| `detection-range` | `{prefix}rangeplotter-{name}-tgt_alt_{alt}m_{ref}-det_rng_{rng}km{var}.kml` in **subfolders per sensor** | ❌ Uses subfolders instead of flat |

**Standard Naming Convention (all commands):**

All output files go in a **single flat folder** (the command's default output directory or user-specified directory). No subfolders per sensor.

**Filename Pattern:**
```
{prefix}rangeplotter-{sensor_name}{sensor_height_suffix}-{command_params}.kml
```

**Components:**
| Component | Format | Example |
|-----------|--------|---------|
| `prefix` | `{NN}_` where NN is zero-padded sort index | `01_`, `02_` |
| `sensor_name` | Sanitized name (spaces → underscores) | `Brevoort_Island_LRR` |
| `sensor_height_suffix` | `_sh_{height}m` (only if non-default) | `_sh_25m` |
| `command_params` | Command-specific (see below) | |

**Command-Specific Parameters:**

| Command | Parameters | Example |
|---------|------------|---------|
| `viewshed` | `tgt_alt_{alt}m_{AGL\|MSL}` | `tgt_alt_500m_AGL` |
| `horizon` | `horizon` | `horizon` |
| `detection-range` | `tgt_alt_{alt}m_{AGL\|MSL}-det_rng_{range}km` | `tgt_alt_500m_AGL-det_rng_200km` |

**Full Examples:**
```
# viewshed (current - no changes needed)
01_rangeplotter-Brevoort_Island_LRR-tgt_alt_100m_AGL.kml
02_rangeplotter-Brevoort_Island_LRR-tgt_alt_500m_AGL.kml
01_rangeplotter-Brevoort_Island_LRR_sh_25m-tgt_alt_100m_AGL.kml

# horizon (CHANGE REQUIRED - per-sensor files with --no-union)
01_rangeplotter-Brevoort_Island_LRR-horizon.kml
02_rangeplotter-Another_Site-horizon.kml
rangeplotter-union-horizon.kml  # when using --union (default)

# detection-range (CHANGE REQUIRED - flat folder, no subfolders)
01_rangeplotter-Brevoort_Island_LRR-tgt_alt_100m_AGL-det_rng_200km.kml
02_rangeplotter-Brevoort_Island_LRR-tgt_alt_500m_AGL-det_rng_200km.kml
rangeplotter-union-tgt_alt_500m_AGL-det_rng_200km.kml  # when using --union
```

**Changes Required:**

1. **`horizon` command:**
   - Add `--union/--no-union` flag (default: `--union`)
   - With `--union`: output single file `rangeplotter-union-horizon.kml`
   - With `--no-union`: output per-sensor files `{prefix}rangeplotter-{name}-horizon.kml`

2. **`detection-range` command:**
   - Remove subfolder creation (`specific_out_dir = output_dir / base_name`)
   - Output all files directly to `output_dir`
   - Ensure filename includes sensor name for disambiguation

**Files to Modify:**
- `src/rangeplotter/cli/main.py` - horizon and detection-range commands

**Effort:** Low

---

### F3: Output Path Interpretation

**Status:** Ready to implement

**Behavior:**

| User Input | Interpretation |
|------------|----------------|
| `-o myfile.kml` | `{default_output_dir}/myfile.kml` |
| `-o myfolder` | `{default_output_dir}/myfolder/` (if no extension) |
| `-o ./myfile.kml` | `./myfile.kml` (current directory) |
| `-o ./myfolder` | `./myfolder/` (current directory) |
| `-o /absolute/path/file.kml` | `/absolute/path/file.kml` |
| `-o ../relative/path` | `../relative/path` |

**Detection Logic:**
```python
def resolve_output_path(user_path: Path, default_dir: Path) -> Path:
    """
    Resolve user-provided output path.
    
    - Pure filename/foldername → place in default_dir
    - Paths starting with './' or '../' or '/' → use as-is
    """
    user_path = Path(user_path)
    
    # Absolute path: use as-is
    if user_path.is_absolute():
        return user_path
    
    # Relative path with explicit directory: use as-is
    path_str = str(user_path)
    if path_str.startswith('./') or path_str.startswith('../') or '/' in path_str:
        return user_path
    
    # Pure name: place in default directory
    return default_dir / user_path
```

**Default Directories (from config.yaml):**
- `viewshed`: `output_viewshed_dir` (default: `working_files/viewshed`)
- `horizon`: `output_horizon_dir` (default: `working_files/horizon`)
- `detection-range`: `output_detection_dir` (default: `working_files/detection_range`)

**Files to Modify:**
- `src/rangeplotter/cli/main.py` - add `resolve_output_path()` helper, apply to all commands

**Effort:** Low

---

### F4: Sensor Altitude from DEM Ground Elevation

**Status:** Ready to implement

**Problem:**
Google Earth and Copernicus GLO-30 DEM have different ground elevation values. When a user specifies a sensor at "5m AGL" in Google Earth, the absolute altitude from Google Earth may place the sensor below ground level in the Copernicus DEM.

**Solution:**
Handle KML altitude modes correctly by always using Copernicus DEM as the ground reference:

| KML `altitudeMode` | Interpretation |
|--------------------|----------------|
| `relativeToGround` | Use KML's AGL value + DEM ground elevation |
| `clampToGround` | Sensor at DEM ground level (AGL = 0, use config default) |
| `absolute` | Use as-is (current behavior) |

**Implementation:**

1. **Modify KML parsing (`kml.py`):**
   - Parse `altitudeMode` from KML
   - Store in `RadarSite`: `altitude_mode: str` (one of: `"absolute"`, `"relativeToGround"`, `"clampToGround"`)
   - For `relativeToGround`: store the AGL value in `sensor_height_m_agl`
   - For `clampToGround`: set `sensor_height_m_agl` to config default

2. **In `main.py` viewshed command (where ground elevation is sampled):**
   ```python
   # Sample ground elevation from DEM
   ground_elev = dem_client.sample_elevation(sensor.latitude, sensor.longitude)
   
   if sensor.altitude_mode == "relativeToGround":
       # KML specified AGL height - use DEM ground + KML AGL value
       sensor.ground_elevation_m_msl = ground_elev
       sensor.radar_height_m_msl = ground_elev + sensor.sensor_height_m_agl
       log.debug(f"{sensor.name}: Using KML AGL height ({sensor.sensor_height_m_agl}m) + DEM ground ({ground_elev:.1f}m) = {sensor.radar_height_m_msl:.1f}m MSL")
   
   elif sensor.altitude_mode == "clampToGround":
       # KML specified clamp to ground - use DEM ground + config default AGL
       sensor.ground_elevation_m_msl = ground_elev
       sensor.sensor_height_m_agl = settings.sensor_height_m_agl  # from config
       sensor.radar_height_m_msl = ground_elev + sensor.sensor_height_m_agl
       log.debug(f"{sensor.name}: Clamped to DEM ground ({ground_elev:.1f}m) + config AGL ({sensor.sensor_height_m_agl}m) = {sensor.radar_height_m_msl:.1f}m MSL")
   
   else:  # "absolute" or unspecified
       # Current behavior - use KML absolute altitude
       sensor.ground_elevation_m_msl = ground_elev
       # sensor.radar_height_m_msl already set from KML absolute value
       log.debug(f"{sensor.name}: Using KML absolute altitude ({sensor.radar_height_m_msl:.1f}m MSL)")
   ```

3. **Fallback:**
   - If DEM sampling fails (e.g., no tiles available), fall back to KML values
   - Log a warning when falling back

**Files to Modify:**
- `src/rangeplotter/io/kml.py` - parse `altitudeMode`, handle different modes
- `src/rangeplotter/models/radar_site.py` - add `altitude_mode` field
- `src/rangeplotter/cli/main.py` - implement the recalculation logic with debug logging

**Effort:** Medium

---

## Implementation Order

| Priority | ID | Item | Effort |
|----------|-----|------|--------|
| 1 | F4 | Sensor altitude from DEM | Medium |
| 2 | C3 | Ctrl-C signal handling | Medium |
| 3 | F2 | Consistent output naming | Low |
| 4 | F3 | Output path interpretation | Low |
| 5 | F1 | Horizon `--no-union` | Low-Med |
| 6 | C5 | `--altitude` flag rename | Trivial |
| 7 | C2 | Tab completion in install.sh | Trivial |

---

## Deferred to Later Release

- **C1: KML Icons** - Needs design decision on icon style/source
