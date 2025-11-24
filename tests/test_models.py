
from rangeplotter.models.radar_site import RadarSite

def test_radar_site_height_calculation():
    # Case 1: clampToGround
    r1 = RadarSite(
        name="R1", longitude=0, latitude=0,
        altitude_mode="clampToGround",
        input_altitude=100.0, # Should be ignored
        sensor_height_m_agl=10.0,
        ground_elevation_m_msl=50.0
    )
    assert r1.radar_height_m_msl == 60.0 # 50 + 10

    # Case 2: relativeToGround
    r2 = RadarSite(
        name="R2", longitude=0, latitude=0,
        altitude_mode="relativeToGround",
        input_altitude=20.0,
        sensor_height_m_agl=10.0,
        ground_elevation_m_msl=50.0
    )
    assert r2.radar_height_m_msl == 80.0 # 50 + 20 + 10

    # Case 3: absolute
    r3 = RadarSite(
        name="R3", longitude=0, latitude=0,
        altitude_mode="absolute",
        input_altitude=200.0,
        sensor_height_m_agl=10.0,
        ground_elevation_m_msl=50.0
    )
    assert r3.radar_height_m_msl == 210.0 # 200 + 10

    # Case 4: Missing ground elevation
    r4 = RadarSite(
        name="R4", longitude=0, latitude=0,
        altitude_mode="clampToGround",
        input_altitude=0,
        sensor_height_m_agl=10.0,
        ground_elevation_m_msl=None
    )
    assert r4.radar_height_m_msl is None
