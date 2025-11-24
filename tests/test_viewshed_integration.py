
import pytest
from unittest.mock import MagicMock
from pathlib import Path
import rasterio
from rasterio.transform import from_origin
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from rangeplotter.los.viewshed import compute_viewshed
from rangeplotter.models.radar_site import RadarSite

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
