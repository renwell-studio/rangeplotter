
from rangeplotter.io.kml import parse_radars, parse_viewshed_kml
from shapely.geometry import Polygon, MultiPolygon
import pytest
from xml.etree import ElementTree as ET

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

def test_parse_radars_with_styles(tmp_path):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Style id="style1">
      <IconStyle>
        <color>ff0000ff</color>
        <scale>1.2</scale>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href>
        </Icon>
      </IconStyle>
      <LineStyle>
        <color>ff00ff00</color>
        <width>2</width>
      </LineStyle>
    </Style>
    <StyleMap id="styleMap1">
      <Pair>
        <key>normal</key>
        <styleUrl>#style1</styleUrl>
      </Pair>
    </StyleMap>
    <Placemark>
      <name>Styled Radar</name>
      <styleUrl>#styleMap1</styleUrl>
      <Point>
        <coordinates>-1.0,50.0,100</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    kml_file = tmp_path / "styled.kml"
    kml_file.write_text(kml_content)
    
    radars = parse_radars(str(kml_file), default_sensor_height_m=10.0)
    assert len(radars) == 1
    r = radars[0]
    assert r.style_config is not None
    # KML color is aabbggrr. ff0000ff -> red=ff, green=00, blue=00, alpha=ff.
    # The parser converts to hex #rrggbb for line/fill if possible.
    # Wait, let's check the implementation logic in kml.py
    # aa, bb, gg, rr = kml_color[0:2], kml_color[2:4], kml_color[4:6], kml_color[6:8]
    # hex_color = f"#{rr}{gg}{bb}"
    # ff0000ff -> aa=ff, bb=00, gg=00, rr=ff -> #ff0000 (Red)
    
    assert r.style_config.get("icon_color") == "ff0000ff"
    assert r.style_config.get("line_color") == "#00ff00" # ff00ff00 -> aa=ff, bb=00, gg=ff, rr=00 -> #00ff00 (Green)
    assert r.style_config.get("icon_scale") == 1.2
    assert "placemark_circle.png" in r.style_config.get("icon_href", "")

def test_parse_viewshed_kml(tmp_path):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Radar 1 Viewshed</name>
      <Placemark>
        <name>Radar 1</name>
        <Point>
          <coordinates>10.0,20.0,0</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name>Viewshed Polygon</name>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                10.0,20.0,0 10.1,20.0,0 10.1,20.1,0 10.0,20.1,0 10.0,20.0,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    kml_file = tmp_path / "viewshed.kml"
    kml_file.write_text(kml_content)
    
    results = parse_viewshed_kml(str(kml_file))
    assert len(results) == 1
    res = results[0]
    assert res['folder_name'] == "Radar 1 Viewshed"
    assert res['sensor_name'] == "Radar 1"
    assert res['sensor'] == (10.0, 20.0)
    assert isinstance(res['viewshed'], Polygon)
    assert not res['viewshed'].is_empty

def test_parse_radars_complex_style(tmp_path):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Style id="polyStyle">
      <PolyStyle>
        <color>8000ff00</color> <!-- 50% Green -->
        <fill>1</fill>
      </PolyStyle>
    </Style>
    <Placemark>
      <name>Poly Radar</name>
      <description>Test Description</description>
      <styleUrl>#polyStyle</styleUrl>
      <altitudeMode>absolute</altitudeMode>
      <Point>
        <coordinates>-1.0,50.0,100</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    kml_file = tmp_path / "complex.kml"
    kml_file.write_text(kml_content)
    
    radars = parse_radars(str(kml_file), 10.0)
    assert len(radars) == 1
    r = radars[0]
    assert r.description == "Test Description"
    assert r.altitude_mode == "absolute"
    assert r.style_config.get("fill_color") == "#00ff00"
    assert abs(r.style_config.get("fill_opacity") - 0.5) < 0.01

def test_parse_viewshed_kml_stylemap(tmp_path):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Style id="normalStyle">
      <LineStyle>
        <color>ff0000ff</color>
      </LineStyle>
    </Style>
    <StyleMap id="mapStyle">
      <Pair>
        <key>normal</key>
        <styleUrl>#normalStyle</styleUrl>
      </Pair>
    </StyleMap>
    <Folder>
      <name>Viewshed Folder</name>
      <Placemark>
        <name>Sensor</name>
        <Point><coordinates>0,0,0</coordinates></Point>
      </Placemark>
      <Placemark>
        <name>Viewshed</name>
        <styleUrl>#mapStyle</styleUrl>
        <Polygon>
          <outerBoundaryIs><LinearRing><coordinates>0,0,0 1,0,0 1,1,0 0,0,0</coordinates></LinearRing></outerBoundaryIs>
        </Polygon>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    kml_file = tmp_path / "viewshed_stylemap.kml"
    kml_file.write_text(kml_content)
    
    results = parse_viewshed_kml(str(kml_file))
    assert len(results) == 1
    res = results[0]
    style = res['style']
    assert style.get("line_color") == "#ff0000"

def test_parse_radars_invalid_file(tmp_path):
    kml_file = tmp_path / "invalid.kml"
    kml_file.write_text("Not XML")
    
    with pytest.raises(ET.ParseError):
        parse_radars(str(kml_file), 10.0)

def test_parse_radars_missing_file():
    with pytest.raises(FileNotFoundError):
        parse_radars("non_existent.kml", 10.0)
