from rangeplotter.io.kml import parse_radars
import pytest

def test_sensor_altitude_override(tmp_path):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Override Radar</name>
      <altitudeMode>relativeToGround</altitudeMode>
      <Point>
        <coordinates>-1.0,50.0,50.0</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Default Radar</name>
      <altitudeMode>clampToGround</altitudeMode>
      <Point>
        <coordinates>-2.0,51.0,0.0</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Absolute Radar</name>
      <altitudeMode>absolute</altitudeMode>
      <Point>
        <coordinates>-3.0,52.0,100.0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    kml_file = tmp_path / "override.kml"
    kml_file.write_text(kml_content)
    
    default_height = 10.0
    radars = parse_radars(str(kml_file), default_sensor_height_m=default_height)
    
    assert len(radars) == 3
    
    # 1. Override Radar (relativeToGround, 50m)
    # Should use 50m as sensor height.
    # Implementation detail: sensor_height_m_agl becomes 0, input_altitude is 50.
    r1 = next(r for r in radars if r.name == "Override Radar")
    assert r1.input_altitude == 50.0
    assert r1.sensor_height_m_agl == 0.0
    
    # Check effective height calculation
    r1.ground_elevation_m_msl = 100.0
    # relativeToGround: ground + input + sensor_height = 100 + 50 + 0 = 150
    assert r1.radar_height_m_msl == 150.0

    # 2. Default Radar (clampToGround)
    # Should use default height (10m).
    r2 = next(r for r in radars if r.name == "Default Radar")
    assert r2.sensor_height_m_agl == default_height
    r2.ground_elevation_m_msl = 100.0
    # clampToGround: ground + sensor_height = 100 + 10 = 110
    assert r2.radar_height_m_msl == 110.0

    # 3. Absolute Radar (absolute, 100m)
    # Should use default height (10m) added to absolute position.
    r3 = next(r for r in radars if r.name == "Absolute Radar")
    assert r3.sensor_height_m_agl == default_height
    r3.ground_elevation_m_msl = 50.0 
    # absolute: (input_altitude) + sensor_height = 100 + 10 = 110
    assert r3.radar_height_m_msl == 110.0
