
from rangeplotter.io.kml import parse_radars

def test_parse_radars(tmp_path, sample_kml_content):
    kml_file = tmp_path / "test.kml"
    kml_file.write_text(sample_kml_content)
    
    radars = parse_radars(str(kml_file), default_sensor_height_m=5.0)
    assert len(radars) == 1
    r = radars[0]
    assert r.name == "Test Radar"
    assert r.longitude == -1.5
    assert r.latitude == 50.5
    assert r.input_altitude == 100.0
    assert r.sensor_height_m_agl == 5.0
