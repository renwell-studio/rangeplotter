
from rangeplotter.los.rings import compute_horizons
from rangeplotter.models.radar_site import RadarSite

def test_compute_horizons():
    r1 = RadarSite(name="R1", latitude=0, longitude=0, input_altitude=10, altitude_mode="agl", sensor_height_m_agl=10)
    # ground_elevation_m_msl is None initially
    
    radars = [r1]
    altitudes = [100, 1000]
    k = 1.333
    
    results = compute_horizons(radars, altitudes, k)
    
    assert "R1" in results
    rings = results["R1"]
    assert len(rings) == 2
    assert rings[0][0] == 100
    assert rings[0][1] > 0
    assert rings[1][0] == 1000
    assert rings[1][1] > rings[0][1]
    
    # Check that ground elevation was defaulted to 0.0 for agl
    assert r1.ground_elevation_m_msl == 0.0

def test_compute_horizons_absolute():
    r1 = RadarSite(name="R1", latitude=0, longitude=0, input_altitude=50, altitude_mode="absolute")
    # ground_elevation_m_msl is None initially
    
    radars = [r1]
    altitudes = [100]
    k = 1.333
    
    compute_horizons(radars, altitudes, k)
    
    # Check that ground elevation was defaulted to input_altitude for absolute
    assert r1.ground_elevation_m_msl == 50.0
