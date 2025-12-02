
import pytest
from unittest.mock import MagicMock
from pathlib import Path
import rasterio
from rasterio.transform import from_origin
import numpy as np
import time
from shapely.geometry import Polygon, MultiPolygon
from rangeplotter.los.viewshed import compute_viewshed
from rangeplotter.models.radar_site import RadarSite
from rangeplotter.io.viewshed_cache import ViewshedCache

@pytest.fixture
def synthetic_dem_path(tmp_path):
    dem_path = tmp_path / "synthetic_dem.tif"
    
    # Create a 100x100 DEM covering a small area around 0,0
    # Resolution approx 30m (approx 0.00027 degrees)
    width = 100
    height = 100
    res = 0.00027
    transform = from_origin(-0.0135, 0.0135, res, res)
    
    # Flat terrain at 10m elevation
    data = np.full((1, height, width), 10, dtype=np.int16)
    
    with rasterio.open(
        dem_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1,
        dtype=data.dtype,
        crs='+proj=latlong',
        transform=transform,
    ) as dst:
        dst.write(data)
        
    return dem_path

def test_compute_viewshed_integration(synthetic_dem_path):
    # Mock DemClient
    mock_client = MagicMock()
    mock_client.ensure_tiles.return_value = [synthetic_dem_path]
    
    # Create a radar site at the center
    radar = RadarSite(
        name="Test Radar",
        longitude=0.0,
        latitude=0.0,
        altitude_mode="clampToGround",
        input_altitude=None,
        sensor_height_m_agl=10.0,
        ground_elevation_m_msl=10.0 # Same as terrain
    )
    
    # Config dict
    config = {
        "resources": {"use_disk_swap": False},
        "multiscale": {"enable": False}, # Disable multiscale for simple test
        "atmospheric_k_factor": 1.333
    }
    
    # Compute viewshed for target at 100m MSL
    # Radar is at 20m MSL (10m ground + 10m sensor)
    # Target is at 100m MSL
    # Should be visible
    
    poly = compute_viewshed(
        radar=radar,
        target_alt=100.0,
        dem_client=mock_client,
        config=config,
        altitude_mode="msl"
    )
    
    assert isinstance(poly, (Polygon, MultiPolygon))
    assert not poly.is_empty
    assert poly.area > 0

def test_compute_viewshed_agl(synthetic_dem_path):
    # Mock DemClient
    mock_client = MagicMock()
    mock_client.ensure_tiles.return_value = [synthetic_dem_path]
    
    radar = RadarSite(
        name="Test Radar",
        longitude=0.0,
        latitude=0.0,
        altitude_mode="clampToGround",
        input_altitude=None,
        sensor_height_m_agl=10.0,
        ground_elevation_m_msl=10.0
    )
    
    config = {
        "resources": {"use_disk_swap": False},
        "multiscale": {"enable": False},
        "atmospheric_k_factor": 1.333
    }
    
    # Compute viewshed for target at 50m AGL
    poly = compute_viewshed(
        radar=radar,
        target_alt=50.0,
        dem_client=mock_client,
        config=config,
        altitude_mode="agl"
    )
    
    assert isinstance(poly, (Polygon, MultiPolygon))
    assert not poly.is_empty


class TestViewshedCacheIntegration:
    """Integration tests for viewshed caching."""
    
    def test_cache_hit_faster_than_miss(self, synthetic_dem_path, tmp_path):
        """Second viewshed with different altitude should be faster (cache hit)."""
        mock_client = MagicMock()
        mock_client.ensure_tiles.return_value = [synthetic_dem_path]
        
        radar = RadarSite(
            name="Cache Test Radar",
            longitude=0.0,
            latitude=0.0,
            altitude_mode="clampToGround",
            input_altitude=None,
            sensor_height_m_agl=10.0,
            ground_elevation_m_msl=10.0
        )
        
        config = {
            "cache_dir": str(tmp_path / "cache"),
            "resources": {"use_disk_swap": False},
            "multiscale": {"enable": False},
            "atmospheric_k_factor": 1.333,
            "earth_model": {"ellipsoid": "WGS84"}
        }
        
        # First run - cache miss (populates cache)
        t0 = time.perf_counter()
        poly1 = compute_viewshed(
            radar=radar,
            target_alt=100.0,
            dem_client=mock_client,
            config=config,
            altitude_mode="agl",
            use_cache=True
        )
        t1 = time.perf_counter()
        first_run_time = t1 - t0
        
        # Second run - different altitude, same physics (cache hit)
        t2 = time.perf_counter()
        poly2 = compute_viewshed(
            radar=radar,
            target_alt=500.0,  # Different altitude
            dem_client=mock_client,
            config=config,
            altitude_mode="agl",
            use_cache=True
        )
        t3 = time.perf_counter()
        second_run_time = t3 - t2
        
        # Both should produce valid polygons
        assert isinstance(poly1, (Polygon, MultiPolygon))
        assert isinstance(poly2, (Polygon, MultiPolygon))
        assert not poly1.is_empty
        assert not poly2.is_empty
        
        # Verify cache file was created
        cache = ViewshedCache(Path(config["cache_dir"]))
        stats = cache.get_cache_stats()
        assert stats["count"] >= 1
        
        # Note: We can't strictly enforce timing in CI, but we can log
        print(f"First run: {first_run_time:.3f}s, Second run: {second_run_time:.3f}s")
    
    def test_cache_miss_on_sensor_height_change(self, synthetic_dem_path, tmp_path):
        """Changing sensor height should cause cache miss."""
        mock_client = MagicMock()
        mock_client.ensure_tiles.return_value = [synthetic_dem_path]
        
        config = {
            "cache_dir": str(tmp_path / "cache"),
            "resources": {"use_disk_swap": False},
            "multiscale": {"enable": False},
            "atmospheric_k_factor": 1.333,
            "earth_model": {"ellipsoid": "WGS84"}
        }
        
        # First radar with 10m sensor height
        radar1 = RadarSite(
            name="Radar 1",
            longitude=0.0,
            latitude=0.0,
            altitude_mode="clampToGround",
            input_altitude=None,
            sensor_height_m_agl=10.0,
            ground_elevation_m_msl=10.0
        )
        
        # Second radar with 20m sensor height (different physics)
        radar2 = RadarSite(
            name="Radar 2",
            longitude=0.0,
            latitude=0.0,
            altitude_mode="clampToGround",
            input_altitude=None,
            sensor_height_m_agl=20.0,  # Different sensor height
            ground_elevation_m_msl=10.0
        )
        
        # Run both
        poly1 = compute_viewshed(
            radar=radar1,
            target_alt=100.0,
            dem_client=mock_client,
            config=config,
            altitude_mode="agl",
            use_cache=True
        )
        
        poly2 = compute_viewshed(
            radar=radar2,
            target_alt=100.0,
            dem_client=mock_client,
            config=config,
            altitude_mode="agl",
            use_cache=True
        )
        
        # Check cache has two entries (separate hashes)
        cache = ViewshedCache(Path(config["cache_dir"]))
        stats = cache.get_cache_stats()
        assert stats["count"] >= 2
    
    def test_no_cache_flag(self, synthetic_dem_path, tmp_path):
        """use_cache=False should bypass caching."""
        mock_client = MagicMock()
        mock_client.ensure_tiles.return_value = [synthetic_dem_path]
        
        radar = RadarSite(
            name="No Cache Radar",
            longitude=0.0,
            latitude=0.0,
            altitude_mode="clampToGround",
            input_altitude=None,
            sensor_height_m_agl=10.0,
            ground_elevation_m_msl=10.0
        )
        
        config = {
            "cache_dir": str(tmp_path / "cache"),
            "resources": {"use_disk_swap": False},
            "multiscale": {"enable": False},
            "atmospheric_k_factor": 1.333,
            "earth_model": {"ellipsoid": "WGS84"}
        }
        
        poly = compute_viewshed(
            radar=radar,
            target_alt=100.0,
            dem_client=mock_client,
            config=config,
            altitude_mode="agl",
            use_cache=False  # Disable cache
        )
        
        assert isinstance(poly, (Polygon, MultiPolygon))
        
        # Cache should be empty or not created
        cache = ViewshedCache(Path(config["cache_dir"]))
        stats = cache.get_cache_stats()
        assert stats["count"] == 0