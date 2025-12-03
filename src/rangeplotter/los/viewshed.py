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
from rangeplotter.io.viewshed_cache import ViewshedCache
from rangeplotter.geo.earth import mutual_horizon_distance, effective_earth_radius
from rangeplotter.utils.shutdown import is_shutdown_requested

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


def _compute_mva_polar(
    dem_array: np.ndarray,
    transform: rasterio.Affine,
    radar_h_msl: float,
    max_radius_m: float,
    center_lat_deg: float,
    k_factor: float = 1.333,
    max_ram_percent: float = 80.0,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute Minimum Visible Altitude (MVA) surface in polar coordinates.
    
    Returns a Float32 array where each cell contains the minimum altitude (AGL)
    a target must be at to be visible from the sensor.
    
    Physics:
        The MVA represents the lowest altitude a target must be at to clear all
        terrain obstructions along the line-of-sight ray from the sensor.
        
        For each point at distance r along a radial ray:
        1. Track the maximum elevation angle encountered so far:
           θ_terrain = (h_terrain - h_sensor) / r - r / (2 * R_eff)
           M = max(θ_terrain) along the ray
        
        2. Compute the MSL altitude required to clear angle M:
           h_req = h_sensor + r * (M + r / (2 * R_eff))
        
        3. Convert to AGL:
           MVA = max(0, h_req - h_terrain)
        
        Where R_eff = R_earth * k_factor accounts for atmospheric refraction.
        
        MVA Interpretation:
        - MVA = 0: Ground is visible (no obstruction)
        - MVA = 500: Target must be at least 500m AGL to be seen
        - MVA = inf: Location is beyond horizon or completely obscured
    
    Args:
        dem_array: Elevation data in AEQD (meters).
        transform: Affine transform of the DEM (AEQD).
        radar_h_msl: Radar height (MSL).
        max_radius_m: Maximum analysis radius.
        center_lat_deg: Latitude of radar (for earth radius).
        k_factor: Effective earth radius factor.
        max_ram_percent: Maximum percentage of system RAM to use.
        progress_callback: Optional callback(step: str, percentage: float) for progress updates.
        
    Returns:
        Tuple of (mva_polar, r_values, az_values):
            - mva_polar: Float32 array (n_az, n_r) of minimum visible altitude AGL
            - r_values: 1D array of range values in meters
            - az_values: 1D array of azimuth values in radians
    """
    # Constants
    R_eff = effective_earth_radius(center_lat_deg, k_factor)
    
    log.debug(f"MVA Polar Sweep: Radar H={radar_h_msl:.2f}m, Max Radius={max_radius_m:.2f}m, R_eff={R_eff:.2f}m")

    height, width = dem_array.shape
    
    # Check elevation at radar location
    it = ~transform
    center_col_float, center_row_float = it * (0, 0)
    center_c = int(center_col_float)
    center_r = int(center_row_float)
    
    if 0 <= center_c < width and 0 <= center_r < height:
        center_elev = dem_array[center_r, center_c]
        msg = f"Elevation at Radar Location (Grid Center): {center_elev:.2f}m. Radar H: {radar_h_msl:.2f}m. Delta: {radar_h_msl - center_elev:.2f}m"
        if radar_h_msl < center_elev:
            log.warning(msg)
        else:
            log.debug(msg)
    else:
        log.warning(f"Radar location is outside DEM grid! Center: ({center_c}, {center_r}), Shape: ({width}, {height})")

    # 1. Setup Polar Grid
    pixel_size = transform[0]
    
    n_r = int(np.ceil(max_radius_m / pixel_size))
    r_values = np.linspace(0, max_radius_m, n_r)
    
    circumference = 2 * np.pi * max_radius_m
    n_az = int(np.ceil(circumference / pixel_size))
    n_az = min(n_az, 14400)
    if n_az % 2 != 0:
        n_az += 1
        
    log.debug(f"Polar Grid: {n_az} azimuths x {n_r} ranges. Est. memory per array: {n_az * n_r * 4 / 1024 / 1024:.1f} MB")
        
    az_values = np.linspace(0, 2*np.pi, n_az, endpoint=False)
    
    # Create output MVA array (Polar) - Float32 for altitude values
    # Initialize with inf (meaning completely obscured)
    mva_polar = np.full((n_az, n_r), np.inf, dtype=np.float32)
    
    # Dynamic chunk sizing
    mem = psutil.virtual_memory()
    total_mem = mem.total
    available_mem = mem.available
    target_limit = total_mem * (max_ram_percent / 100.0)
    current_used = total_mem - available_mem
    available_budget = max(0, target_limit - current_used - (1024 * 1024 * 1024))
    target_chunk_bytes = available_budget * 0.8
    
    # Bytes per azimuth: n_r * 44 bytes (accounting for Float32 MVA output)
    bytes_per_az = n_r * 44
    az_chunk_size = max(1, int(target_chunk_bytes / bytes_per_az))
    
    log.debug(f"Available Budget: {available_budget/1024/1024:.1f} MB. Target chunk size: {target_chunk_bytes/1024/1024:.1f} MB.")
    log.debug(f"Processing MVA sweep in chunks of {az_chunk_size} azimuths...")
    
    r_values_2d = r_values.reshape(1, n_r)
    it = ~transform

    for az_start in range(0, n_az, az_chunk_size):
        az_end = min(az_start + az_chunk_size, n_az)
        
        az_chunk = az_values[az_start:az_end]
        az_grid_chunk = az_chunk.reshape(-1, 1)
        
        x_grid = r_values_2d * np.sin(az_grid_chunk)
        y_grid = r_values_2d * np.cos(az_grid_chunk)
        
        cols = (it.a * x_grid + it.b * y_grid + it.c).astype(int)
        rows = (it.d * x_grid + it.e * y_grid + it.f).astype(int)
        
        np.clip(cols, 0, width - 1, out=cols)
        np.clip(rows, 0, height - 1, out=rows)
        
        elevations = dem_array[rows, cols]
        elevations_filled = np.nan_to_num(elevations, nan=0.0)
        
        r_safe = r_values_2d.copy()
        r_safe[r_safe == 0] = 0.1
        
        # Compute terrain angle from radar
        term1 = (elevations_filled - radar_h_msl) / r_safe
        term2 = r_safe / (2 * R_eff)
        
        theta_terrain = term1 - term2
        theta_terrain[:, 0] = -9999.0
        
        # Running max angle along each ray
        M = np.maximum.accumulate(theta_terrain, axis=1)
        
        # Compute the required MSL altitude to clear the max angle M
        # Using: theta = (h - h_radar) / r - r / (2 * R_eff)
        # Solve for h: h_req = h_radar + r * (M + r / (2 * R_eff))
        h_req_msl = radar_h_msl + r_safe * (M + term2)
        
        # MVA is the height Above Ground Level
        mva_chunk = h_req_msl - elevations_filled
        
        # Clamp to 0 if ground is visible (h_req <= terrain means MVA = 0)
        mva_chunk = np.maximum(mva_chunk, 0.0).astype(np.float32)
        
        # Store result
        mva_polar[az_start:az_end, :] = mva_chunk
        
        del x_grid, y_grid, cols, rows, elevations, elevations_filled
        del theta_terrain, M, h_req_msl, mva_chunk

        if progress_callback:
            progress_callback("Computing MVA", (az_end / n_az) * 100)
    
    # Stats for logging
    finite_mva = mva_polar[np.isfinite(mva_polar)]
    if finite_mva.size > 0:
        log.debug(f"MVA Polar Stats: Min={finite_mva.min():.2f}m, Max={finite_mva.max():.2f}m, Mean={finite_mva.mean():.2f}m")
    
    return mva_polar, r_values, az_values


def _polar_to_cartesian_mva(
    mva_polar: np.ndarray,
    r_values: np.ndarray,
    az_values: np.ndarray,
    dem_shape: Tuple[int, int],
    transform: rasterio.Affine,
    max_radius_m: float,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> np.ndarray:
    """
    Convert MVA from polar to Cartesian coordinates.
    
    Args:
        mva_polar: Float32 array (n_az, n_r) of MVA values.
        r_values: 1D array of range values in meters.
        az_values: 1D array of azimuth values in radians.
        dem_shape: Shape of the output cartesian grid (height, width).
        transform: Affine transform for the cartesian grid.
        max_radius_m: Maximum radius for valid data.
        progress_callback: Optional callback for progress updates.
        
    Returns:
        Float32 array (height, width) of MVA values in Cartesian coordinates.
        Values outside max_radius_m are set to inf.
    """
    height, width = dem_shape
    n_az = len(az_values)
    n_r = len(r_values)
    
    # Create output - initialize with inf (outside range = not visible)
    mva_cart = np.full((height, width), np.inf, dtype=np.float32)
    
    block_size = 2048
    total_blocks = ((height + block_size - 1) // block_size) * ((width + block_size - 1) // block_size)
    processed_blocks = 0
    
    for r_start in range(0, height, block_size):
        for c_start in range(0, width, block_size):
            r_end = min(r_start + block_size, height)
            c_end = min(c_start + block_size, width)
            
            rows_block, cols_block = np.indices((r_end - r_start, c_end - c_start))
            rows_block += r_start
            cols_block += c_start
            
            x_map = transform.a * cols_block + transform.b * rows_block + transform.c
            y_map = transform.d * cols_block + transform.e * rows_block + transform.f
            
            r_map = np.sqrt(x_map**2 + y_map**2)
            az_map = np.arctan2(x_map, y_map)
            az_map[az_map < 0] += 2 * np.pi
            
            r_idx = (r_map / (max_radius_m / (n_r - 1))).astype(int)
            az_idx = (az_map / (2 * np.pi / n_az)).astype(int)
            
            np.clip(r_idx, 0, n_r - 1, out=r_idx)
            np.clip(az_idx, 0, n_az - 1, out=az_idx)
            
            valid_mask = r_map <= max_radius_m
            
            # Extract MVA values for this block
            block_mva = np.full_like(r_map, np.inf, dtype=np.float32)
            block_mva[valid_mask] = mva_polar[az_idx[valid_mask], r_idx[valid_mask]]
            
            mva_cart[r_start:r_end, c_start:c_end] = block_mva
            
            processed_blocks += 1
            if progress_callback:
                progress_callback("Converting to Cartesian", (processed_blocks / total_blocks) * 100)
    
    return mva_cart


def _threshold_mva_to_mask(mva: np.ndarray, target_alt_agl: float) -> np.ndarray:
    """
    Threshold an MVA surface to produce a binary visibility mask.
    
    Args:
        mva: Float32 MVA array (Cartesian or Polar).
        target_alt_agl: Target altitude Above Ground Level.
        
    Returns:
        uint8 binary mask where 1 = visible (MVA <= target_alt).
    """
    return (mva <= target_alt_agl).astype(np.uint8)


def _radial_sweep_visibility(
    dem_array: np.ndarray,
    transform: rasterio.Affine,
    radar_h_msl: float,
    target_h: float,
    max_radius_m: float,
    center_lat_deg: float,
    k_factor: float = 1.333,
    max_ram_percent: float = 80.0,
    progress_callback: Optional[Callable[[str, float], None]] = None,
    altitude_mode: str = "msl"
) -> Polygon | MultiPolygon:
    """
    Perform radial sweep to determine visibility polygon.
    
    This is a compatibility wrapper that uses the new MVA-based approach
    internally but maintains the original function signature.
    
    dem_array: Elevation data in AEQD (meters).
    transform: Affine transform of the DEM (AEQD).
    radar_h_msl: Radar height (MSL).
    target_h: Target height (MSL or AGL depending on mode).
    max_radius_m: Maximum analysis radius.
    center_lat_deg: Latitude of radar (for earth radius).
    k_factor: Effective earth radius factor.
    max_ram_percent: Maximum percentage of system RAM to use.
    progress_callback: Optional callback(step: str, percentage: float) for progress updates.
    altitude_mode: "msl" or "agl".
    """
    log.debug(f"Radial Sweep: Radar H={radar_h_msl:.2f}m, Target H={target_h:.2f}m ({altitude_mode}), Max Radius={max_radius_m:.2f}m")
    
    # 1. Compute MVA in polar coordinates
    mva_polar, r_values, az_values = _compute_mva_polar(
        dem_array=dem_array,
        transform=transform,
        radar_h_msl=radar_h_msl,
        max_radius_m=max_radius_m,
        center_lat_deg=center_lat_deg,
        k_factor=k_factor,
        max_ram_percent=max_ram_percent,
        progress_callback=progress_callback
    )
    
    # 2. Convert to Cartesian coordinates
    mva_cart = _polar_to_cartesian_mva(
        mva_polar=mva_polar,
        r_values=r_values,
        az_values=az_values,
        dem_shape=dem_array.shape,
        transform=transform,
        max_radius_m=max_radius_m,
        progress_callback=progress_callback
    )
    
    # Free polar memory
    del mva_polar
    
    # 3. Handle altitude mode conversion
    # MVA is computed as AGL - the minimum altitude above ground for visibility
    if altitude_mode == "agl":
        # target_h is already AGL, use directly
        target_alt_agl = target_h
    else:
        # MSL mode: target_h is absolute MSL
        # We need to compare against terrain + MVA
        # For MSL mode, a point is visible if target_h >= terrain_elev + MVA
        # Which means: MVA <= target_h - terrain_elev
        # But we don't have terrain_elev in the Cartesian grid easily...
        # 
        # Alternative approach: For MSL mode, we need to sample terrain and adjust
        # For now, we'll handle MSL by using the inverse:
        # If target is at fixed MSL, visibility depends on terrain height too.
        # This is complex - for backwards compatibility, let's handle it specially.
        #
        # Actually, for MSL mode, we need the terrain elevation at each point.
        # The simplest approach: sample DEM at each point.
        # But this is expensive. Better approach: 
        # - For MSL, target_alt_agl = target_h - terrain_elev at each point
        # This means we can't use a simple threshold; we need a per-pixel comparison.
        #
        # Let's do it properly with the DEM:
        height, width = dem_array.shape
        it = ~transform
        
        # Create meshgrid for terrain sampling
        rows_idx, cols_idx = np.indices((height, width))
        x_coords = transform.a * cols_idx + transform.b * rows_idx + transform.c
        y_coords = transform.d * cols_idx + transform.e * rows_idx + transform.f
        
        # We already have dem_array which gives terrain elevation
        terrain_elev = np.nan_to_num(dem_array, nan=0.0)
        
        # For MSL mode: visible if target_h >= terrain_elev + MVA
        # Which means: target_h - terrain_elev >= MVA
        target_h_above_ground = target_h - terrain_elev
        
        # Create mask: visible where MVA <= target_h_above_ground
        # Also need to exclude underground targets (target_h < terrain)
        mask = np.zeros((height, width), dtype=np.uint8)
        visible = (mva_cart <= target_h_above_ground) & (target_h_above_ground >= 0)
        mask[visible] = 1
        
        # Also exclude points outside range (mva_cart is inf there)
        del mva_cart, terrain_elev, target_h_above_ground, visible
        
        # Skip to polygonization
        return _polygonize_mask(mask, transform)
    
    # 4. Threshold MVA to binary visibility mask (AGL mode)
    mask = _threshold_mva_to_mask(mva_cart, target_alt_agl)
    del mva_cart
    
    # 5. Polygonize
    return _polygonize_mask(mask, transform)


def _polygonize_mask(mask: np.ndarray, transform: rasterio.Affine) -> Polygon | MultiPolygon:
    """
    Convert a binary visibility mask to a polygon.
    
    Args:
        mask: uint8 binary mask where 1 = visible.
        transform: Affine transform for the mask.
        
    Returns:
        Polygon or MultiPolygon representing the visible area.
    """
    pixel_size = transform[0]
    
    import rasterio.features
    from shapely.geometry import shape
    from shapely.ops import unary_union
    
    shapes = rasterio.features.shapes(mask, transform=transform)
    
    polygons = []
    for geom, val in shapes:
        if val == 1:
            polygons.append(shape(geom))
            
    if not polygons:
        return Polygon()
        
    merged = unary_union(polygons)
    simplified = merged.simplify(tolerance=pixel_size, preserve_topology=True)
    
    if isinstance(simplified, (Polygon, MultiPolygon)):
        return simplified
    return Polygon()

def compute_viewshed(
    radar: RadarSite,
    target_alt: float,
    dem_client: DemClient,
    config: dict,
    progress_callback: Optional[Callable[[str, float], None]] = None,
    rich_progress: Optional[Any] = None,
    altitude_mode: str = "msl",
    use_cache: bool = True
) -> Polygon | MultiPolygon:
    """
    Compute a viewshed polygon for a radar site.
    
    This function uses a Minimum Visible Altitude (MVA) approach with per-zone
    caching to enable efficient recomputation for different target altitudes.
    
    Args:
        radar: The radar site to compute the viewshed for.
        target_alt: Target altitude (MSL or AGL depending on altitude_mode).
        dem_client: DEM client for fetching terrain data.
        config: Configuration dictionary.
        progress_callback: Optional callback for progress updates.
        rich_progress: Optional rich progress bar.
        altitude_mode: "msl" or "agl".
        use_cache: Whether to use the MVA cache (default True).
        
    Returns:
        Polygon or MultiPolygon representing the visible area in WGS84.
    """
    
    # 1. Calculate max geometric range
    radar_h = radar.radar_height_m_msl
    if radar_h is None:
        radar_h = 0.0  # Fallback
        
    d_max = mutual_horizon_distance(radar_h, target_alt, radar.latitude, k=config.get("atmospheric_k_factor", 1.333))
    d_max *= 1.05  # 5% buffer
    
    log.debug(f"Computing viewshed for {radar.name} @ {target_alt}m ({altitude_mode.upper()}). Max range: {d_max/1000:.1f} km")
    
    # 2. Get DEM tiles (needed for cache miss path)
    if progress_callback:
        progress_callback("Downloading DEM", 0)
    bbox = approximate_bounding_box(radar.longitude, radar.latitude, d_max)
    dem_paths = dem_client.ensure_tiles(bbox, progress=rich_progress)
    
    # 3. Setup cache
    cache_dir = Path(config.get("cache_dir", "data_cache"))
    cache = ViewshedCache(cache_dir) if use_cache else None
    
    # Extract resource config
    res_cfg = config.get("resources", {})
    use_disk_swap = res_cfg.get("use_disk_swap", True)
    max_ram_percent = res_cfg.get("max_ram_percent", 80.0)
    
    # Determine resolution using Multiscale config
    ms_config = config.get('multiscale', {})
    
    polygons_aeqd = []
    
    if not ms_config.get('enable', True):
        zones = [(0.0, d_max, ms_config.get('res_near_m', 30.0))]
    else:
        near_m = ms_config.get('near_m', 50000)
        mid_m = ms_config.get('mid_m', 200000)
        far_m = ms_config.get('far_m', 800000)
        
        res_near = ms_config.get('res_near_m', 30.0)
        res_mid = ms_config.get('res_mid_m', 120.0)
        res_far = ms_config.get('res_far_m', 1000.0)
        
        zones = [
            (0.0, near_m, res_near),
            (near_m, mid_m, res_mid),
            (mid_m, max(far_m, d_max), res_far)
        ]

    # Get ground elevation for cache key
    ground_elev = radar.ground_elevation_m_msl if radar.ground_elevation_m_msl is not None else 0.0
    sensor_h_agl = radar.sensor_height_m_agl if radar.sensor_height_m_agl is not None else radar_h - ground_elev
    
    # Earth model for cache key
    earth_model_cfg = config.get("earth_model", {})
    earth_model = earth_model_cfg.get("ellipsoid", "WGS84")
    k_factor = config.get("atmospheric_k_factor", 1.333)

    # Process each zone
    for i, (z_min, z_max, z_res) in enumerate(zones):
        # Check for shutdown request between zones
        if is_shutdown_requested():
            log.info(f"Shutdown requested. Stopping after zone {i}.")
            break
            
        if d_max <= z_min:
            continue
            
        pass_max_r = min(d_max, z_max)
        
        log.info(f"Processing Zone {i+1}: {z_min/1000:.1f}-{pass_max_r/1000:.1f} km @ {z_res}m resolution")
        
        if progress_callback:
            progress_callback(f"Zone {i+1} ({z_res}m)", 0)

        # Try cache lookup
        mva_cart = None
        dem_array = None
        transform = None
        cache_hit = False
        
        if cache is not None:
            zone_hash = cache.compute_hash(
                lat=radar.latitude,
                lon=radar.longitude,
                ground_elev=ground_elev,
                sensor_h_agl=sensor_h_agl,
                z_min=z_min,
                z_max=pass_max_r,
                z_res=z_res,
                k_factor=k_factor,
                earth_model=earth_model
            )
            
            cached = cache.get(zone_hash)
            if cached is not None:
                mva_cart, transform, _ = cached
                cache_hit = True
                log.info(f"Zone {i+1}: Cache HIT ({zone_hash[:8]}...)")
        
        if not cache_hit:
            # Cache miss - compute MVA
            log.info(f"Zone {i+1}: Cache MISS. Computing MVA...")
            
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
            
            # Compute MVA in polar coordinates
            t_sweep_start = time.perf_counter()
            mva_polar, r_values, az_values = _compute_mva_polar(
                dem_array=dem_array,
                transform=transform,
                radar_h_msl=radar_h,
                max_radius_m=pass_max_r,
                center_lat_deg=radar.latitude,
                k_factor=k_factor,
                max_ram_percent=max_ram_percent,
                progress_callback=None
            )
            
            # Convert to Cartesian
            mva_cart = _polar_to_cartesian_mva(
                mva_polar=mva_polar,
                r_values=r_values,
                az_values=az_values,
                dem_shape=dem_array.shape,
                transform=transform,
                max_radius_m=pass_max_r,
                progress_callback=None
            )
            t_sweep_end = time.perf_counter()
            log.debug(f"Zone {i+1} MVA computation took {t_sweep_end - t_sweep_start:.2f}s")
            
            del mva_polar, r_values, az_values
            
            # Cache the result
            if cache is not None:
                aeqd_crs = f"+proj=aeqd +lat_0={radar.latitude} +lon_0={radar.longitude} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
                cache.put(zone_hash, mva_cart, transform, aeqd_crs)
        
        # Threshold MVA to get binary visibility mask
        if altitude_mode == "agl":
            # For AGL mode, target_alt is already in AGL - direct threshold
            mask = _threshold_mva_to_mask(mva_cart, target_alt)
        else:
            # For MSL mode, we need terrain elevation to compute target height AGL
            # If we have dem_array from cache miss path, use it
            # Otherwise we need to load it for MSL mode
            if dem_array is None:
                dem_array, _ = _reproject_dem_to_aeqd(
                    dem_paths, 
                    radar.longitude, 
                    radar.latitude, 
                    pass_max_r,
                    target_resolution=z_res,
                    use_disk_swap=use_disk_swap,
                    max_ram_percent=max_ram_percent
                )
            
            terrain_elev = np.nan_to_num(dem_array, nan=0.0)
            target_h_above_ground = target_alt - terrain_elev
            
            # Visible where MVA <= target_h_above_ground and target is above ground
            mask = np.zeros_like(mva_cart, dtype=np.uint8)
            visible = (mva_cart <= target_h_above_ground) & (target_h_above_ground >= 0)
            mask[visible] = 1
            
            del terrain_elev, target_h_above_ground, visible
        
        del mva_cart
        if dem_array is not None:
            del dem_array
        
        # Polygonize
        poly = _polygonize_mask(mask, transform)
        del mask
        
        if poly.is_empty:
            log.warning(f"Zone {i+1} produced an empty viewshed polygon.")
        else:
            log.debug(f"Zone {i+1} produced a valid polygon (Area: {poly.area:.1f})")

        # Clip to annulus
        center = Point(0, 0)
        outer_circle = center.buffer(pass_max_r)
        if z_min > 0:
            inner_circle = center.buffer(z_min)
            annulus = outer_circle.difference(inner_circle)
        else:
            annulus = outer_circle
            
        clipped_poly = poly.intersection(annulus)
        
        if not clipped_poly.is_empty:
            log.debug(f"Zone {i+1} clipped polygon is valid (Area: {clipped_poly.area:.1f})")
            polygons_aeqd.append(clipped_poly)
        else:
            log.warning(f"Zone {i+1} clipped polygon is empty.")
            
        del poly, clipped_poly
        
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
    
    # Reproject back to WGS84
    if progress_callback:
        progress_callback("Transforming to WGS84", 0)
    
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

