from rangeplotter.io.export import (
    to_kml_color, _coords_to_kml_str, export_viewshed_kml, export_horizons_kml,
    export_kml_polygon, geodesic_circle_coords, kml_ring_placemark, export_combined_kml
)
from shapely.geometry import Polygon, MultiPolygon
from pathlib import Path
from rangeplotter.models.radar_site import RadarSite

def test_to_kml_color():
    # Red #FF0000 -> aabbggrr -> ff0000ff (full opacity)
    # Note: The implementation might return lowercase hex
    assert to_kml_color("#FF0000", 1.0).lower() == "ff0000ff"
    # Green #00FF00 -> ff00ff00
    assert to_kml_color("#00FF00", 1.0).lower() == "ff00ff00"
    # Blue #0000FF -> ffff0000
    assert to_kml_color("#0000FF", 1.0).lower() == "ffff0000"
    # 50% opacity
    c = to_kml_color("#FFFFFF", 0.5).lower()
    assert c.startswith("7f") or c.startswith("80")

def test_coords_to_kml_str():
    coords = [(0, 0), (1, 1)]
    s = _coords_to_kml_str(coords, 100)
    assert s == "0,0,100 1,1,100"

def test_export_viewshed_kml(tmp_path):
    poly = Polygon([(0,0), (1,0), (1,1), (0,1)])
    out_file = tmp_path / "test.kml"
    
    style = {
        "line_color": "#FF0000",
        "line_width": 2,
        "fill_color": "#00FF00",
        "fill_opacity": 0.5
    }
    
    sensors = [{
        "name": "S1",
        "location": (0.5, 0.5),
        "style_config": {}
    }]
    
    export_viewshed_kml(
        viewshed_polygon=poly,
        output_path=out_file,
        altitude=100,
        style_config=style,
        sensors=sensors,
        document_name="Test Doc",
        altitude_mode="msl"
    )
    
    assert out_file.exists()
    content = out_file.read_text()
    assert "<name>Test Doc</name>" in content
    assert "S1" in content
    # Fill color #00FF00 with 0.5 opacity -> 7f00ff00 (approx)
    # Check for the color part at least, or the full string if we are sure about hex conversion
    assert "00ff00" in content.lower() 
    assert "7f" in content.lower() or "80" in content.lower()

def test_export_viewshed_kml_multipolygon(tmp_path):
    p1 = Polygon([(0,0), (1,0), (1,1)])
    p2 = Polygon([(2,2), (3,2), (3,3)])
    mp = MultiPolygon([p1, p2])
    out_file = tmp_path / "multi.kml"
    
    export_viewshed_kml(
        viewshed_polygon=mp,
        output_path=out_file,
        altitude=100,
        style_config={},
        sensors=[],
        document_name="Multi",
        altitude_mode="agl",
        kml_export_mode="absolute"
    )
    
    assert out_file.exists()
    content = out_file.read_text()
    assert "<MultiGeometry>" in content
    assert "relativeToGround" in content

def test_export_viewshed_kml_holes(tmp_path):
    # Polygon with a hole
    shell = [(0,0), (3,0), (3,3), (0,3)]
    hole = [(1,1), (2,1), (2,2), (1,2)]
    poly = Polygon(shell, [hole])
    out_file = tmp_path / "holes.kml"
    
    export_viewshed_kml(
        viewshed_polygon=poly,
        output_path=out_file,
        altitude=100,
        style_config={},
        sensors=[],
        document_name="Holes",
        altitude_mode="msl"
    )
    
    assert out_file.exists()
    content = out_file.read_text()
    assert "<innerBoundaryIs>" in content

def test_export_horizons_kml(tmp_path):
    rings = {
        "R1": [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
    }
    meta = {
        "R1": {
            "lat": 0.0,
            "lon": 0.0,
            "ground_elev": 0.0,
            "height_agl": 0.0
        }
    }
    style = {
        "line_color": "#FF0000",
        "line_width": 2
    }
    out_file = tmp_path / "horizons.kml"
    
    export_horizons_kml(str(out_file), rings, meta, style)
    
    assert out_file.exists()
    content = out_file.read_text()
    assert "R1" in content
    assert "ff0000ff" in content.lower() # Red line
    content = out_file.read_text().lower()

    assert "<name>geometric horizons</name>" in content

def test_geodesic_circle_coords():
    coords = geodesic_circle_coords(0, 0, 1000, segments=4)
    assert len(coords) == 5 # 4 segments + closing point
    assert coords[0] == coords[-1]

def test_kml_ring_placemark():
    coords = ["0,0,0", "1,1,0"]
    kml = kml_ring_placemark("Ring", coords, "#FF0000", 2, "#00FF00", 0.5)
    assert "<name>Ring</name>" in kml
    assert "ff0000ff" in kml.lower()

def test_export_kml_polygon(tmp_path):
    poly = Polygon([(0,0), (1,0), (1,1)])
    out_file = tmp_path / "poly.kml"
    export_kml_polygon(poly, out_file, "Poly", color="#FF0000", width=2, fill_color="#00FF00", fill_opacity=0.5)
    assert out_file.exists()
    content = out_file.read_text()
    assert "<name>Poly</name>" in content

def test_export_combined_kml(tmp_path):
    r1 = RadarSite(name="R1", latitude=0, longitude=0, input_altitude=100, altitude_mode="relativeToGround")
    poly = Polygon([(0,0), (1,0), (1,1)])
    
    data = [
        {
            'radar': r1,
            'viewsheds': {100.0: poly}
        }
    ]
    out_file = tmp_path / "combined.kml"
    
    export_combined_kml(
        output_path=out_file,
        radars_data=data,
        styles=[],
        style_config={},
        document_name="Combined"
    )
    assert out_file.exists()
    content = out_file.read_text()
    assert "<name>Combined</name>" in content
    assert "R1" in content
