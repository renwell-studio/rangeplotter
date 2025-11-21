"""
Terrain-aware Line-of-Sight (LOS) calculation module.

This module implements the core visibility algorithm using a radial sweep approach
on a Digital Elevation Model (DEM). It accounts for Earth curvature and atmospheric
refraction using the effective earth radius model.
"""
from __future__ import annotations

import math
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Callable, Any, cast

import numpy as np
import rasterio
# from rasterio.merge import merge # No longer used
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.io import MemoryFile
from shapely.geometry import Polygon, Point, MultiPolygon
from shapely.ops import transform
import pyproj

from rangeplotter.models.radar_site import RadarSite
from rangeplotter.io.dem import DemClient, approximate_bounding_box
from rangeplotter.geo.earth import mutual_horizon_distance, effective_earth_radius

log = logging.getLogger(__name__)

import tempfile
import os
import psutil
import time

def _build_vrt(dem_paths: List[Path]) -> str:
    """
    Builds a VRT (Virtual Dataset) XML for the given DEM paths.
    Returns the path to the temporary VRT file.
    """
    t0 = time.perf_counter()
    # 1. Scan files to determine global bounds and resolution
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    
    res_x, res_y = None, None
    nodata = None
    crs_wkt = None
    
    sources = []
    
    # We need to open files to get their metadata.
    # This is fast as we only read the header.
    for p in dem_paths:
        with rasterio.open(p) as src:
            t = src.transform
            w, h = src.width, src.height
            
            # Update bounds
            # bounds property is (left, bottom, right, top)
            b = src.bounds
            min_x = min(min_x, b.left)
            min_y = min(min_y, b.bottom)
            max_x = max(max_x, b.right)
            max_y = max(max_y, b.top)
            
            # Pick the highest resolution (smallest pixel size)
            if res_x is None or abs(t.a) < abs(res_x):
                res_x = t.a
                res_y = t.e # Usually negative
                nodata = src.nodata
                crs_wkt = src.crs.wkt
            
            sources.append({
                'path': str(p.absolute()),
                'width': w,
                'height': h,
                'transform': t
            })
            
    # 2. Calculate VRT dimensions
    # VRT GeoTransform: (min_x, res_x, 0, max_y, 0, res_y)
    if res_x is None or res_y is None:
        raise ValueError("Could not determine resolution from DEM files.")

    # Ensure res_y is negative for standard north-up images
    if res_y > 0:
        # If positive, it means y increases upwards (Cartesian). 
        # But usually rasterio/GDAL uses top-left origin with negative y-res.
        # We'll assume standard top-left for VRT construction.
        pass 
    
    vrt_width = int(round((max_x - min_x) / res_x))
    # height = (top - bottom) / pixel_height
    # If res_y is negative, pixel_height is -res_y
    vrt_height = int(round((max_y - min_y) / abs(res_y)))
    
    # 3. Generate XML
    fd, vrt_path = tempfile.mkstemp(suffix=".vrt")
    os.close(fd)
    
    with open(vrt_path, 'w') as f:
        f.write(f'<VRTDataset rasterXSize="{vrt_width}" rasterYSize="{vrt_height}">\n')
        f.write(f'  <SRS>{crs_wkt}</SRS>\n')
        f.write(f'  <GeoTransform>{min_x}, {res_x}, 0.0, {max_y}, 0.0, {res_y}</GeoTransform>\n')
        f.write(f'  <VRTRasterBand dataType="Float32" band="1">\n')
        if nodata is not None:
            f.write(f'    <NoDataValue>{nodata}</NoDataValue>\n')
            
        for s in sources:
            # Calculate DstRect
            # x_off = (src_left - vrt_left) / res_x
            # y_off = (vrt_top - src_top) / -res_y (since y grows down in pixel coords)
            
            src_left = s['transform'].c
            src_top = s['transform'].f
            
            dst_x_off = int(round((src_left - min_x) / res_x))
            dst_y_off = int(round((max_y - src_top) / abs(res_y)))
            
            # Calculate DstRect size based on resolution ratio
            src_res_x = s['transform'].a
            src_res_y = s['transform'].e
            
            dst_w = int(round(s['width'] * (src_res_x / res_x)))
            dst_h = int(round(s['height'] * (abs(src_res_y) / abs(res_y))))
            
            f.write('    <SimpleSource>\n')
            f.write(f'      <SourceFilename relativeToVRT="0">{s["path"]}</SourceFilename>\n')
            f.write('      <SourceBand>1</SourceBand>\n')
            f.write(f'      <SrcRect xOff="0" yOff="0" xSize="{s["width"]}" ySize="{s["height"]}" />\n')
            f.write(f'      <DstRect xOff="{dst_x_off}" yOff="{dst_y_off}" xSize="{dst_w}" ySize="{dst_h}" />\n')
            f.write('    </SimpleSource>\n')
            
        f.write('  </VRTRasterBand>\n')
        f.write('</VRTDataset>\n')
    
    t1 = time.perf_counter()
    log.debug(f"VRT creation took {t1-t0:.4f}s")
    return vrt_path

def _reproject_dem_to_aeqd(
    dem_paths: List[Path],
    center_lon: float,
    center_lat: float,
    max_radius_m: float,
    target_resolution: float = 30.0,
    use_disk_swap: bool = True,
    max_ram_percent: float = 80.0
) -> Tuple[np.ndarray, rasterio.Affine]:
    """
    Reproject DEM tiles to Azimuthal Equidistant (AEQD) centered on the radar.
    Uses a VRT (Virtual Raster) to treat multiple tiles as a single source without loading them all.
    Returns the reprojected data (numpy array) and its affine transform.
    """
    # Filter out non-existent paths
    valid_paths = [p for p in dem_paths if p.exists()]
    if not valid_paths:
        raise FileNotFoundError("No valid DEM tiles found.")

    # 1. Define target CRS (AEQD)
    # proj string for AEQD centered on radar
    dst_crs = f"+proj=aeqd +lat_0={center_lat} +lon_0={center_lon} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"

    # 2. Define target grid
    # We want a fixed grid centered on (0,0) covering max_radius_m
    # Use target_resolution (default 30m)
    target_res = target_resolution
    extent = max_radius_m * 1.05 # 5% buffer
    
    # Ensure dimensions are integer
    dim = int(2 * extent / target_res)
    width = dim
    height = dim
    
    # Transform: Top-Left (-extent, extent)
    # x = col * res - extent
    # y = extent - row * res
    dst_transform = rasterio.Affine(target_res, 0.0, -extent, 0.0, -target_res, extent)

    # 3. Allocate destination array
    # Check size: width * height * 4 bytes
    size_bytes = width * height * 4
    size_mb = size_bytes / 1024 / 1024
    
    # Dynamic memory check
    mem = psutil.virtual_memory()
    total_mem = mem.total
    available_mem = mem.available
    
    # Calculate budget based on max_ram_percent
    # Target usage limit
    target_limit = total_mem * (max_ram_percent / 100.0)
    # Current usage
    current_used = total_mem - available_mem
    # Available budget for this array
    # We leave a 1GB buffer for OS/other overhead just in case
    available_budget = max(0, target_limit - current_used - (1024 * 1024 * 1024))
    
    should_swap = False
    if use_disk_swap:
        if size_bytes > available_budget:
            should_swap = True
            log.warning(f"Target DEM array ({size_mb:.1f} MB) exceeds available RAM budget ({available_budget/1024/1024:.1f} MB). Using disk swap.")
            
    if should_swap:
        log.info(f"Target DEM array is large ({size_mb:.1f} MB). Using disk-backed memmap.")
        # Create a temp file
        fd, temp_path = tempfile.mkstemp(suffix=".dat")
        os.close(fd)
        # Create memmap
        dst_array = np.memmap(temp_path, dtype=np.float32, mode='w+', shape=(1, height, width))
        dst_array[:] = np.nan # Initialize with NaN
    else:
        dst_array = np.full((1, height, width), np.nan, dtype=np.float32)

    # 4. Reproject using VRT
    # Build a VRT for the source files
    vrt_path = _build_vrt(valid_paths)
    log.debug(f"Created temporary VRT at {vrt_path}")
    
    t_warp_start = time.perf_counter()
    try:
        with rasterio.open(vrt_path) as src:
            # Reproject from the VRT to the destination array
            # This allows GDAL to handle the mosaicing and reading efficiently
            reproject(
                source=rasterio.band(src, 1),
                destination=dst_array,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                dst_nodata=np.nan,
                num_threads=-1 # Use all available cores
            )
    finally:
        # Cleanup VRT file
        if os.path.exists(vrt_path):
            os.remove(vrt_path)
    
    t_warp_end = time.perf_counter()
    log.info(f"DEM Warp/Reproject took {t_warp_end - t_warp_start:.2f}s")

    return dst_array[0], dst_transform

def _radial_sweep_visibility(
    dem_array: np.ndarray,
    transform: rasterio.Affine,
    radar_h_msl: float,
    target_h_msl: float,
    max_radius_m: float,
    center_lat_deg: float,
    k_factor: float = 1.333,
    max_ram_percent: float = 80.0,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Polygon | MultiPolygon:
    """
    Perform radial sweep to determine visibility polygon.
    
    dem_array: Elevation data in AEQD (meters).
    transform: Affine transform of the DEM (AEQD).
    radar_h_msl: Radar height (MSL).
    target_h_msl: Target height (MSL).
    max_radius_m: Maximum analysis radius.
    center_lat_deg: Latitude of radar (for earth radius).
    k_factor: Effective earth radius factor.
    max_ram_percent: Maximum percentage of system RAM to use.
    progress_callback: Optional callback(step: str, percentage: float) for progress updates.
    """
    
    # Constants
    # Calculate effective earth radius at this latitude
    R_eff = effective_earth_radius(center_lat_deg, k_factor)
    
    log.debug(f"Radial Sweep Inputs: Radar H={radar_h_msl:.2f}m, Target H={target_h_msl:.2f}m, Max Radius={max_radius_m:.2f}m, R_eff={R_eff:.2f}m")

    height, width = dem_array.shape
    
    # Check elevation at radar location
    # Use the inverse transform properly
    it = ~transform
    # Center (0,0) in AEQD maps to (col, row)
    center_col_float, center_row_float = it * (0, 0)
    center_c = int(center_col_float)
    center_r = int(center_row_float)
    
    if 0 <= center_c < width and 0 <= center_r < height:
        center_elev = dem_array[center_r, center_c]
        msg = f"Elevation at Radar Location (Grid Center): {center_elev:.2f}m. Radar H: {radar_h_msl:.2f}m. Delta: {radar_h_msl - center_elev:.2f}m"
        if radar_h_msl < center_elev:
            log.warning(msg)
        else:
            log.info(msg)
    else:
        log.warning(f"Radar location is outside DEM grid! Center: ({center_c}, {center_r}), Shape: ({width}, {height})")

    # 1. Setup Polar Grid
    # We use a dense set of radials to ensure coverage
    # Pixel size (approx)
    pixel_size = transform[0]
    
    # Number of radial steps
    n_r = int(np.ceil(max_radius_m / pixel_size))
    r_values = np.linspace(0, max_radius_m, n_r)
    
    # Number of azimuth steps
    # We want arc length at max range to be comparable to pixel size to avoid gaps
    circumference = 2 * np.pi * max_radius_m
    # Ensure we have at least 1 pixel resolution at the edge
    n_az = int(np.ceil(circumference / pixel_size))
    # Clamp to a reasonable maximum to prevent OOM on huge ranges, but 3600 is too low for 100km+
    # 120km radius -> 750km circ -> 30m pixel -> 25000 steps.
    n_az = min(n_az, 14400) 
    # Ensure even number for symmetry
    if n_az % 2 != 0:
        n_az += 1
        
    log.debug(f"Polar Grid: {n_az} azimuths x {n_r} ranges. Est. memory per array: {n_az * n_r * 4 / 1024 / 1024:.1f} MB")
        
    az_values = np.linspace(0, 2*np.pi, n_az, endpoint=False)
    
    # Create output visibility mask (Polar)
    # We use bool to save memory (1 byte per pixel vs 4 bytes for float)
    visible_polar = np.zeros((n_az, n_r), dtype=bool)
    
    # Chunk processing for Azimuths to save memory
    # Target ~512MB per chunk for intermediate arrays
    # Each azimuth column has n_r elements.
    # We have approx 10 intermediate arrays (r_grid, x, y, cols, rows, elev, theta, M, etc.)
    # Bytes per azimuth = n_r * 4 bytes * 10 arrays = n_r * 40 bytes
    
    # Dynamic chunk sizing
    mem = psutil.virtual_memory()
    total_mem = mem.total
    available_mem = mem.available
    
    # Calculate budget based on max_ram_percent
    # We want to use up to max_ram_percent of TOTAL memory for the process
    # But we need to account for what's already used (including dem_array if it's in RAM)
    
    # Target usage limit
    target_limit = total_mem * (max_ram_percent / 100.0)
    
    current_used = total_mem - available_mem
    
    # Available budget for chunks
    # We leave a 1GB buffer
    available_budget = max(0, target_limit - current_used - (1024 * 1024 * 1024))
    
    # Use up to 80% of the AVAILABLE budget for the active chunk
    target_chunk_bytes = available_budget * 0.8
    
    # Bytes per azimuth = n_r * 40
    bytes_per_az = n_r * 40
    az_chunk_size = max(1, int(target_chunk_bytes / bytes_per_az))
    
    log.debug(f"Available Budget: {available_budget/1024/1024:.1f} MB. Target chunk size: {target_chunk_bytes/1024/1024:.1f} MB.")
    log.debug(f"Processing radial sweep in chunks of {az_chunk_size} azimuths...")
    
    # Pre-calculate r_values grid (1D) as it is constant for all chunks
    # But we need 2D for broadcasting, so we'll make it (1, n_r) and broadcast
    r_values_2d = r_values.reshape(1, n_r)
    
    # Inverse transform
    it = ~transform

    for az_start in range(0, n_az, az_chunk_size):
        az_end = min(az_start + az_chunk_size, n_az)
        
        # 1. Setup Grid for this chunk
        az_chunk = az_values[az_start:az_end]
        az_grid_chunk = az_chunk.reshape(-1, 1) # (chunk, 1)
        
        # Broadcast to (chunk, n_r)
        # x = r * sin(az)
        x_grid = r_values_2d * np.sin(az_grid_chunk)
        y_grid = r_values_2d * np.cos(az_grid_chunk)
        
        # Map to pixel coordinates
        cols = (it.a * x_grid + it.b * y_grid + it.c).astype(int)
        rows = (it.d * x_grid + it.e * y_grid + it.f).astype(int)
        
        # Clip to bounds
        np.clip(cols, 0, width - 1, out=cols)
        np.clip(rows, 0, height - 1, out=rows)
        
        # Sample elevations
        elevations = dem_array[rows, cols]
        
        # Handle missing data
        elevations_filled = np.nan_to_num(elevations, nan=0.0)
        
        # 2. Compute Visibility
        r_safe = r_values_2d.copy()
        r_safe[r_safe == 0] = 0.1
        
        # Term 1
        term1 = (elevations_filled - radar_h_msl) / r_safe
        # Term 2
        term2 = r_safe / (2 * R_eff)
        
        theta_terrain = term1 - term2
        theta_terrain[:, 0] = -9999.0
        
        # Running max
        M = np.maximum.accumulate(theta_terrain, axis=1)
        
        # Target angle
        target_term1 = (target_h_msl - radar_h_msl) / r_safe
        theta_target = target_term1 - term2
        
        # Visibility check
        vis_chunk = theta_target >= M
        
        # Mask underground
        vis_chunk[target_h_msl < elevations_filled] = False
        
        # Store result
        visible_polar[az_start:az_end, :] = vis_chunk
        
        # Explicitly delete large intermediates
        del x_grid, y_grid, cols, rows, elevations, elevations_filled, theta_terrain, M, theta_target, vis_chunk

        if progress_callback:
            progress_callback("Computing LOS", (az_end / n_az) * 100)
    
    # Check if we found ANY visible pixels
    visible_count = np.count_nonzero(visible_polar)
    total_pixels = visible_polar.size
    log.debug(f"Polar Visibility Stats: {visible_count} / {total_pixels} pixels visible ({visible_count/total_pixels*100:.2f}%)")

    # 3. Convert to Cartesian Mask (Chunked)
    # We want to create a boolean mask in the DEM grid space.
    # We iterate over blocks to save memory.
    
    # Create output mask
    mask = np.zeros((height, width), dtype=np.uint8)
    
    block_size = 2048
    total_blocks = ((height + block_size - 1) // block_size) * ((width + block_size - 1) // block_size)
    processed_blocks = 0
    
    for r_start in range(0, height, block_size):
        for c_start in range(0, width, block_size):
            r_end = min(r_start + block_size, height)
            c_end = min(c_start + block_size, width)
            
            # Create grid for this block
            # Indices relative to the block
            # But we need global indices to compute x, y
            # np.indices returns (2, rows, cols)
            # We can use broadcasting
            
            # Global row/col indices for this block
            # shape: (block_h, block_w)
            rows_block, cols_block = np.indices((r_end - r_start, c_end - c_start))
            rows_block += r_start
            cols_block += c_start
            
            # Convert pixel to x, y (AEQD)
            # x = a * col + b * row + c
            # y = d * col + e * row + f
            x_map = transform.a * cols_block + transform.b * rows_block + transform.c
            y_map = transform.d * cols_block + transform.e * rows_block + transform.f
            
            # Convert to Polar
            r_map = np.sqrt(x_map**2 + y_map**2)
            az_map = np.arctan2(x_map, y_map) # result in [-pi, pi]
            az_map[az_map < 0] += 2 * np.pi # [0, 2pi]
            
            # Map to indices in our Polar grid
            r_idx = (r_map / (max_radius_m / (n_r - 1))).astype(int)
            az_idx = (az_map / (2 * np.pi / n_az)).astype(int)
            
            # Clip indices
            np.clip(r_idx, 0, n_r - 1, out=r_idx)
            np.clip(az_idx, 0, n_az - 1, out=az_idx)
            
            # Lookup visibility
            valid_mask = r_map <= max_radius_m
            
            # Extract visibility for this block
            block_mask = np.zeros_like(valid_mask, dtype=np.uint8)
            block_mask[valid_mask] = visible_polar[az_idx[valid_mask], r_idx[valid_mask]]
            
            # Write to global mask
            mask[r_start:r_end, c_start:c_end] = block_mask
            
            processed_blocks += 1
            if progress_callback:
                progress_callback("Generating Mask", (processed_blocks / total_blocks) * 100)
    
    # 4. Polygonize
    if progress_callback:
        progress_callback("Vectorizing", 0)
    import rasterio.features
    from shapely.geometry import shape
    
    # shapes returns generator of (geojson_geometry, value)
    # We want value=1
    shapes = rasterio.features.shapes(mask, transform=transform)
    
    polygons = []
    for geom, val in shapes:
        if val == 1:
            polygons.append(shape(geom))
            
    if not polygons:
        return Polygon()
        
    # Union all polygons
    from shapely.ops import unary_union
    merged = unary_union(polygons)
    
    # Simplify
    simplified = merged.simplify(tolerance=pixel_size, preserve_topology=True)
    
    if isinstance(simplified, (Polygon, MultiPolygon)):
        return simplified
    return Polygon()

def compute_viewshed(
    radar: RadarSite,
    target_alt_msl: float,
    dem_client: DemClient,
    config: dict,
    progress_callback: Optional[Callable[[str, float], None]] = None,
    rich_progress: Optional[Any] = None
) -> Polygon | MultiPolygon:
    
    # 1. Calculate max geometric range
    # We use the geometric horizon as a hard limit to fetch data.
    # d_max = mutual_horizon_distance(radar_h, target_h)
    radar_h = radar.radar_height_m_msl
    if radar_h is None:
        # Should have been set by prepare-dem or similar.
        # If not, we can't proceed accurately.
        # For now, assume 0 if None? Or raise error.
        radar_h = 0.0 # Fallback
        
    d_max = mutual_horizon_distance(radar_h, target_alt_msl, radar.latitude, k=config.get("atmospheric_k_factor", 1.333))
    
    # Add a buffer?
    d_max *= 1.05
    
    log.debug(f"Computing viewshed for {radar.name} @ {target_alt_msl}m. Max range: {d_max/1000:.1f} km")
    
    # 2. Get DEM
    if progress_callback:
        progress_callback("Downloading DEM", 0)
    bbox = approximate_bounding_box(radar.longitude, radar.latitude, d_max)
    dem_paths = dem_client.ensure_tiles(bbox, progress=rich_progress)
    
    # 3. Reproject
    log.debug("Reprojecting DEM to AEQD...")
    if progress_callback:
        progress_callback("Reprojecting DEM", 0)
    
    # Extract resource config
    res_cfg = config.get("resources", {})
    use_disk_swap = res_cfg.get("use_disk_swap", True)
    max_ram_percent = res_cfg.get("max_ram_percent", 80.0)
    
    # Determine resolution using Multiscale config
    ms_config = config.get('multiscale', {})
    
    polygons_aeqd = []
    
    if not ms_config.get('enable', True):
        # Legacy single-pass mode (force high res or use simple logic)
        # For now, just treat as one big zone with near_res
        zones = [(0.0, d_max, ms_config.get('res_near_m', 30.0))]
    else:
        # Define zones: (min_r, max_r, res)
        # We ensure we cover up to d_max
        near_m = ms_config.get('near_m', 50000)
        mid_m = ms_config.get('mid_m', 200000)
        far_m = ms_config.get('far_m', 800000)
        
        res_near = ms_config.get('res_near_m', 30.0)
        res_mid = ms_config.get('res_mid_m', 120.0)
        res_far = ms_config.get('res_far_m', 1000.0)
        
        zones = []
        # Zone 1: 0 -> near
        zones.append((0.0, near_m, res_near))
        # Zone 2: near -> mid
        zones.append((near_m, mid_m, res_mid))
        # Zone 3: mid -> far (or d_max)
        zones.append((mid_m, max(far_m, d_max), res_far))

    # Process each zone
    for i, (z_min, z_max, z_res) in enumerate(zones):
        if d_max <= z_min:
            continue
            
        # Effective max radius for this pass
        pass_max_r = min(d_max, z_max)
        
        log.info(f"Processing Zone {i+1}: {z_min/1000:.1f}-{pass_max_r/1000:.1f} km @ {z_res}m resolution")
        
        if progress_callback:
            progress_callback(f"Zone {i+1} ({z_res}m)", 0)

        t0 = time.perf_counter()
        dem_array, transform = _reproject_dem_to_aeqd(
            dem_paths, 
            radar.longitude, 
            radar.latitude, 
            pass_max_r,
            target_resolution=z_res,
            use_disk_swap=use_disk_swap,
            max_ram_percent=max_ram_percent
        )
        t1 = time.perf_counter()
        log.debug(f"Zone {i+1} Reprojection took {t1-t0:.2f}s. Grid: {dem_array.shape}")
        log.debug(f"DEM Stats: Min={np.nanmin(dem_array):.2f}, Max={np.nanmax(dem_array):.2f}, Mean={np.nanmean(dem_array):.2f}")
        
        # Run Radial Sweep
        t_sweep_start = time.perf_counter()
        poly = _radial_sweep_visibility(
            dem_array, 
            transform, 
            radar_h, 
            target_alt_msl, 
            pass_max_r, 
            radar.latitude,
            config.get("atmospheric_k_factor", 1.333),
            max_ram_percent=max_ram_percent,
            progress_callback=None # Don't spam progress for sub-steps
        )
        t_sweep_end = time.perf_counter()
        log.debug(f"Zone {i+1} Sweep took {t_sweep_end - t_sweep_start:.2f}s")
        
        if poly.is_empty:
            log.warning(f"Zone {i+1} produced an empty viewshed polygon.")
        else:
            log.debug(f"Zone {i+1} produced a valid polygon (Area: {poly.area:.1f})")

        # Clip to annulus
        # Create annulus in AEQD
        center = Point(0, 0)
        outer_circle = center.buffer(pass_max_r)
        if z_min > 0:
            inner_circle = center.buffer(z_min)
            annulus = outer_circle.difference(inner_circle)
        else:
            annulus = outer_circle
            
        # Intersect viewshed with annulus
        clipped_poly = poly.intersection(annulus)
        
        if not clipped_poly.is_empty:
            log.debug(f"Zone {i+1} clipped polygon is valid (Area: {clipped_poly.area:.1f})")
            polygons_aeqd.append(clipped_poly)
        else:
            log.warning(f"Zone {i+1} clipped polygon is empty.")
            
        # Cleanup
        del dem_array, poly, clipped_poly
        
    # Union all zones
    from shapely.ops import unary_union
    log.info(f"Unioning {len(polygons_aeqd)} zone polygons...")
    if not polygons_aeqd:
        poly_aeqd = Polygon()
    else:
        poly_aeqd = unary_union(polygons_aeqd)
    
    if poly_aeqd.is_empty:
        log.warning("Final AEQD polygon is empty.")
    else:
        log.info(f"Final AEQD polygon area: {poly_aeqd.area:.1f}")
    
    # 5. Reproject back to WGS84
    
    # 5. Reproject back to WGS84
    if progress_callback:
        progress_callback("Transforming to WGS84", 0)
    # Define CRSs
    aeqd_proj = f"+proj=aeqd +lat_0={radar.latitude} +lon_0={radar.longitude} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    crs_aeqd = pyproj.CRS(aeqd_proj)
    crs_wgs84 = pyproj.CRS("EPSG:4326")
    
    project = pyproj.Transformer.from_crs(crs_aeqd, crs_wgs84, always_xy=True).transform
    
    from shapely.ops import transform as shapely_transform
    t_vec_start = time.perf_counter()
    poly_wgs84 = shapely_transform(project, poly_aeqd)
    t_vec_end = time.perf_counter()
    log.info(f"Vector Reprojection took {t_vec_end - t_vec_start:.2f}s")
    
    return cast(Polygon | MultiPolygon, poly_wgs84)

