
import pytest
from pathlib import Path
from shapely.geometry import Polygon
from rangeplotter.io.export import export_viewshed_kml
import xml.etree.ElementTree as ET

def test_export_kml_with_ampersand(tmp_path):
    output_path = tmp_path / "test_ampersand.kml"
    poly = Polygon([(0,0), (1,0), (1,1), (0,1)])
    
    # Name with ampersand
    doc_name = "UK&I Military Radar"
    sensor_name = "Sensor & Site"
    
    export_viewshed_kml(
        viewshed_polygon=poly,
        output_path=output_path,
        altitude=100.0,
        style_config={},
        sensors=[{
            'name': sensor_name,
            'location': (0,0),
            'style_config': {}
        }],
        document_name=doc_name
    )
    
    # Try to parse it back
    try:
        tree = ET.parse(output_path)
        root = tree.getroot()
        
        # Find Document name
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        doc = root.find('kml:Document', ns)
        if doc is None:
            # Maybe root is Document? Or kml -> Document
            # ET.parse returns ElementTree, getroot returns the root element (kml)
            pass
            
    except ET.ParseError as e:
        pytest.fail(f"KML parsing failed: {e}")

