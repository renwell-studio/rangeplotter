"""
Viewshed Caching Module.

This module provides a physics-level cache for MVA (Minimum Visible Altitude) rasters.
The cache stores expensive LoS geometry calculations for reuse across different target
altitudes and styling options.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import rasterio
from rasterio.crs import CRS

log = logging.getLogger(__name__)

# Cache version - increment when algorithm changes to invalidate stale caches
CACHE_VERSION = "1"


class ViewshedCache:
    """
    Cache for Minimum Visible Altitude (MVA) rasters.
    
    This cache stores the physics-level computation results (MVA surfaces) which are
    independent of target altitude and visual styling. This enables:
    - Instant target altitude queries via thresholding
    - Reuse across different styling options
    - Reuse across different commands (viewshed, detection-range, network)
    
    Each zone in a multiscale viewshed is cached separately with zone parameters
    included in the hash.
    """
    
    def __init__(self, cache_dir: Path):
        """
        Initialize the viewshed cache.
        
        Args:
            cache_dir: Base cache directory. The viewshed cache will be stored
                      in a 'viewsheds' subdirectory.
        """
        self.cache_dir = Path(cache_dir) / "viewsheds"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        log.debug(f"ViewshedCache initialized at {self.cache_dir}")
    
    def compute_hash(
        self,
        lat: float,
        lon: float,
        ground_elev: float,
        sensor_h_agl: float,
        z_min: float,
        z_max: float,
        z_res: float,
        k_factor: float,
        earth_model: str = "WGS84"
    ) -> str:
        """
        Compute a SHA-256 hash that uniquely identifies an MVA raster.
        
        The hash includes all parameters that affect the obstruction geometry:
        - Sensor position and height
        - Zone boundaries and resolution
        - Atmospheric model (k-factor)
        - Earth model
        
        Excluded (because they don't affect physics):
        - Target altitude
        - Visual styling (colors, opacity)
        
        Args:
            lat: Sensor latitude in degrees (rounded to 6 decimals ~0.1m).
            lon: Sensor longitude in degrees (rounded to 6 decimals ~0.1m).
            ground_elev: Sensor ground elevation MSL in meters (rounded to 1 decimal).
            sensor_h_agl: Sensor height AGL in meters (rounded to 2 decimals).
            z_min: Zone minimum radius in meters (integer).
            z_max: Zone maximum radius in meters (integer).
            z_res: Zone resolution in meters (integer).
            k_factor: Atmospheric refraction k-factor (rounded to 4 decimals).
            earth_model: Earth model identifier (e.g., "WGS84").
            
        Returns:
            SHA-256 hex digest string.
        """
        # Format with specified precision for reproducibility
        hash_input = (
            f"version={CACHE_VERSION}|"
            f"lat={lat:.6f}|"
            f"lon={lon:.6f}|"
            f"ground_elev={ground_elev:.1f}|"
            f"sensor_h_agl={sensor_h_agl:.2f}|"
            f"z_min={int(z_min)}|"
            f"z_max={int(z_max)}|"
            f"z_res={int(z_res)}|"
            f"k_factor={k_factor:.4f}|"
            f"earth_model={earth_model}"
        )
        
        return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, hash_key: str) -> Path:
        """Get the file path for a cached MVA raster."""
        return self.cache_dir / f"{hash_key}.tif"
    
    def get(self, hash_key: str) -> Optional[Tuple[np.ndarray, rasterio.Affine, str]]:
        """
        Retrieve a cached MVA raster.
        
        Args:
            hash_key: The SHA-256 hash key from compute_hash().
            
        Returns:
            Tuple of (mva_array, transform, crs_string) if cache hit, None otherwise.
            - mva_array: Float32 numpy array of MVA values
            - transform: Affine transform for the raster
            - crs_string: CRS as a proj4 string
        """
        cache_path = self._get_cache_path(hash_key)
        
        if not cache_path.exists():
            return None
        
        try:
            with rasterio.open(cache_path) as src:
                mva_array = src.read(1)  # Read first band
                transform = src.transform
                crs_string = src.crs.to_proj4() if src.crs else ""
                
            log.debug(f"Cache HIT: {hash_key[:12]}... ({cache_path.stat().st_size / 1024 / 1024:.1f} MB)")
            return mva_array, transform, crs_string
            
        except Exception as e:
            log.warning(f"Failed to read cached MVA {hash_key[:12]}...: {e}")
            # Remove corrupted cache file
            try:
                cache_path.unlink()
            except OSError:
                pass
            return None
    
    def put(
        self,
        hash_key: str,
        mva_array: np.ndarray,
        transform: rasterio.Affine,
        crs: str
    ) -> bool:
        """
        Store an MVA raster in the cache.
        
        Uses atomic write (temp file + rename) to prevent corruption from
        concurrent access or interrupted writes.
        
        Args:
            hash_key: The SHA-256 hash key from compute_hash().
            mva_array: Float32 numpy array of MVA values.
            transform: Affine transform for the raster.
            crs: CRS as a proj4 string.
            
        Returns:
            True if successfully cached, False otherwise.
        """
        cache_path = self._get_cache_path(hash_key)
        
        # Use atomic write: write to temp file, then rename
        temp_path = self.cache_dir / f"{hash_key}.tmp.{uuid.uuid4().hex[:8]}"
        
        try:
            # Ensure array is Float32
            if mva_array.dtype != np.float32:
                mva_array = mva_array.astype(np.float32)
            
            # Replace inf values with a large nodata value for GeoTIFF compatibility
            # GeoTIFF doesn't handle inf well
            nodata_value = 1e38
            mva_array = np.where(np.isinf(mva_array), nodata_value, mva_array)
            
            height, width = mva_array.shape
            
            profile = {
                'driver': 'GTiff',
                'dtype': 'float32',
                'width': width,
                'height': height,
                'count': 1,
                'crs': CRS.from_proj4(crs) if crs else None,
                'transform': transform,
                'compress': 'lzw',
                'predictor': 2,  # Horizontal differencing for better compression
                'nodata': nodata_value,
                'tiled': True,
                'blockxsize': 256,
                'blockysize': 256
            }
            
            with rasterio.open(temp_path, 'w', **profile) as dst:
                dst.write(mva_array, 1)
            
            # Atomic rename
            os.rename(temp_path, cache_path)
            
            size_mb = cache_path.stat().st_size / 1024 / 1024
            log.debug(f"Cache PUT: {hash_key[:12]}... ({size_mb:.1f} MB)")
            return True
            
        except Exception as e:
            log.warning(f"Failed to cache MVA {hash_key[:12]}...: {e}")
            # Cleanup temp file if it exists
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            return False
    
    def exists(self, hash_key: str) -> bool:
        """Check if a cached MVA raster exists."""
        return self._get_cache_path(hash_key).exists()
    
    def delete(self, hash_key: str) -> bool:
        """Delete a cached MVA raster."""
        cache_path = self._get_cache_path(hash_key)
        try:
            if cache_path.exists():
                cache_path.unlink()
                return True
        except OSError as e:
            log.warning(f"Failed to delete cache {hash_key[:12]}...: {e}")
        return False
    
    def clear(self) -> int:
        """
        Clear all cached MVA rasters.
        
        Returns:
            Number of files deleted.
        """
        count = 0
        for path in self.cache_dir.glob("*.tif"):
            try:
                path.unlink()
                count += 1
            except OSError:
                pass
        log.info(f"Cleared {count} cached viewshed files")
        return count
    
    def get_cache_stats(self) -> dict:
        """
        Get statistics about the cache.
        
        Returns:
            Dictionary with cache statistics.
        """
        files = list(self.cache_dir.glob("*.tif"))
        total_size = 0
        valid_count = 0
        for f in files:
            try:
                total_size += f.stat().st_size
                valid_count += 1
            except OSError:
                # File was deleted between glob and stat (race condition)
                pass
        
        return {
            'count': valid_count,
            'total_size_bytes': total_size,
            'total_size_mb': total_size / 1024 / 1024,
            'cache_dir': str(self.cache_dir)
        }
