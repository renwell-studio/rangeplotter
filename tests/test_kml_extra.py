
import pytest
from rangeplotter.io.kml import parse_viewshed_kml
from shapely.geometry import Polygon, MultiPolygon

def test_parse_viewshed_multigeometry(tmp_path):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Multi Viewshed</name>
      <Placemark>
        <name>Sensor Location</name>
        <Point><coordinates>0,0,0</coordinates></Point>
      </Placemark>
      <Placemark>
        <name>Viewshed Multi</name>
        <MultiGeometry>
          <Polygon>
            <outerBoundaryIs><LinearRing><coordinates>0,0,0 1,0,0 1,1,0 0,0,0</coordinates></LinearRing></outerBoundaryIs>
          </Polygon>
          <Polygon>
            <outerBoundaryIs><LinearRing><coordinates>2,2,0 3,2,0 3,3,0 2,2,0</coordinates></LinearRing></outerBoundaryIs>
          </Polygon>
        </MultiGeometry>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    kml_file = tmp_path / "multi.kml"
    kml_file.write_text(kml_content)
    
    results = parse_viewshed_kml(str(kml_file))
    assert len(results) == 1
    res = results[0]
    assert isinstance(res['viewshed'], MultiPolygon)
    assert len(res['viewshed'].geoms) == 2

def test_parse_viewshed_with_holes(tmp_path):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Holey Viewshed</name>
      <Placemark>
        <name>Sensor</name>
        <Point><coordinates>0,0,0</coordinates></Point>
      </Placemark>
      <Placemark>
        <name>Viewshed</name>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing><coordinates>0,0,0 10,0,0 10,10,0 0,10,0 0,0,0</coordinates></LinearRing>
          </outerBoundaryIs>
          <innerBoundaryIs>
            <LinearRing><coordinates>2,2,0 2,8,0 8,8,0 8,2,0 2,2,0</coordinates></LinearRing>
          </innerBoundaryIs>
        </Polygon>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    kml_file = tmp_path / "holes.kml"
    kml_file.write_text(kml_content)
    
    results = parse_viewshed_kml(str(kml_file))
    assert len(results) == 1
    res = results[0]
    poly = res['viewshed']
    assert isinstance(poly, Polygon)
    assert len(poly.interiors) == 1

def test_parse_viewshed_no_folders(tmp_path):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Sensor</name>
      <Point><coordinates>5,5,0</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>Viewshed</name>
      <Polygon>
        <outerBoundaryIs><LinearRing><coordinates>0,0,0 1,0,0 1,1,0 0,0,0</coordinates></LinearRing></outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""
    kml_file = tmp_path / "nofolder.kml"
    kml_file.write_text(kml_content)
    
    results = parse_viewshed_kml(str(kml_file))
    assert len(results) == 1
    assert results[0]['folder_name'] is None
    assert results[0]['sensor'] == (5.0, 5.0)

def test_parse_viewshed_sensor_name(tmp_path):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <Placemark>
        <name>My Custom Sensor</name>
        <Point><coordinates>1,1,0</coordinates></Point>
      </Placemark>
      <Placemark>
        <Polygon>
          <outerBoundaryIs><LinearRing><coordinates>0,0,0 1,0,0 1,1,0 0,0,0</coordinates></LinearRing></outerBoundaryIs>
        </Polygon>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""
    kml_file = tmp_path / "sensor_name.kml"
    kml_file.write_text(kml_content)
    
    results = parse_viewshed_kml(str(kml_file))
    assert len(results) == 1
    assert results[0]['sensor_name'] == "My Custom Sensor"
