from __future__ import annotations
from typing import Dict, List, Tuple, Union, Optional
import math
from pathlib import Path
from pyproj import Geod
from shapely.geometry import Polygon, MultiPolygon, Point

KML_HEADER = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<kml xmlns=\"http://www.opengis.net/kml/2.2\"><Document>"""
KML_FOOTER = "</Document></kml>"

GEOD = Geod(ellps="WGS84")

def _coords_to_kml_str(coords, altitude: float = 0.0) -> str:
    """Convert list of (lon, lat) or (lon, lat, z) to KML coordinate string."""
    return " ".join(f"{c[0]},{c[1]},{altitude}" for c in coords)

def export_viewshed_kml(
    viewshed_polygon: Union[Polygon, MultiPolygon],
    sensor_location: Tuple[float, float], # lon, lat
    output_path: Path,
    sensor_name: str,
    altitude: float,
    style_config: dict
) -> None:
    """
    Export a viewshed to a self-contained KML file with sensor location and polygon.
    """
    # Helper to convert hex #RRGGBB to KML aabbggrr
    def to_kml_color(hex_col: str, opacity_float: float) -> str:
        hex_col = hex_col.lstrip('#')
        if len(hex_col) != 6:
            return "ff0000ff" # Default red
        rr = hex_col[0:2]
        gg = hex_col[2:4]
        bb = hex_col[4:6]
        aa = f"{int(opacity_float * 255):02x}"
        return aa + bb + gg + rr

    line_color = style_config.get("line_color", "#FFA500")
    line_width = style_config.get("line_width", 2)
    fill_color = style_config.get("fill_color", None)
    fill_opacity = style_config.get("fill_opacity", 0.0)

    line_kml = to_kml_color(line_color, 1.0)
    
    fill_val = "0"
    fill_kml = "00000000"
    if fill_color and fill_opacity > 0:
        fill_val = "1"
        fill_kml = to_kml_color(fill_color, fill_opacity)

    kml_content = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        '  <Document>',
        f'    <name>{sensor_name} Viewshed @ {altitude}m</name>',
        '    <Style id="sensorStyle">',
        '      <IconStyle>',
        '        <scale>1.0</scale>',
        '        <Icon><href>http://maps.google.com/mapfiles/kml/shapes/target.png</href></Icon>',
        '      </IconStyle>',
        '    </Style>',
        '    <Style id="polyStyle">',
        '      <LineStyle>',
        f'        <color>{line_kml}</color>',
        f'        <width>{line_width}</width>',
        '      </LineStyle>',
        '      <PolyStyle>',
        f'        <color>{fill_kml}</color>',
        f'        <fill>{fill_val}</fill>',
        '      </PolyStyle>',
        '    </Style>',
        # '    <Folder>',
        # f'      <name>{sensor_name} Data</name>',
        '      <Placemark>',
        f'        <name>{sensor_name} Location</name>',
        '        <styleUrl>#sensorStyle</styleUrl>',
        '        <Point>',
        f'          <coordinates>{sensor_location[0]},{sensor_location[1]},0</coordinates>',
        '        </Point>',
        '      </Placemark>',
        '      <Placemark>',
        f'        <name>Viewshed @ {altitude}m</name>',
        '        <styleUrl>#polyStyle</styleUrl>',
        '        <MultiGeometry>'
    ]

    polys = []
    if isinstance(viewshed_polygon, Polygon):
        polys = [viewshed_polygon]
    elif isinstance(viewshed_polygon, MultiPolygon):
        polys = list(viewshed_polygon.geoms)
        
    for poly in polys:
        if poly.is_empty:
            continue
            
        # Exterior
        kml_content.append("        <Polygon>")
        kml_content.append("          <altitudeMode>absolute</altitudeMode>")
        kml_content.append("          <outerBoundaryIs><LinearRing><coordinates>")
        kml_content.append(_coords_to_kml_str(poly.exterior.coords, altitude))
        kml_content.append("          </coordinates></LinearRing></outerBoundaryIs>")
        
        # Interiors (holes)
        for interior in poly.interiors:
            kml_content.append("          <innerBoundaryIs><LinearRing><coordinates>")
            kml_content.append(_coords_to_kml_str(interior.coords, altitude))
            kml_content.append("          </coordinates></LinearRing></innerBoundaryIs>")
            
        kml_content.append("        </Polygon>")

    kml_content.append('        </MultiGeometry>')
    kml_content.append('      </Placemark>')
    # kml_content.append('    </Folder>')
    kml_content.append('  </Document>')
    kml_content.append('</kml>')

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(kml_content))

def export_kml_polygon(
    geometry: Union[Polygon, MultiPolygon],
    output_path: Path,
    name: str,
    color: str = "#FFA500", # Hex #RRGGBB
    width: int = 2,
    altitude: float = 0.0,
    fill_color: str | None = None,
    fill_opacity: float = 0.0
) -> None:
    """
    Export a Shapely Polygon or MultiPolygon to a KML file.
    """
    # Helper to convert hex #RRGGBB to KML aabbggrr
    def to_kml_color(hex_col: str, opacity_float: float) -> str:
        hex_col = hex_col.lstrip('#')
        if len(hex_col) != 6:
            return "ff0000ff" # Default red
        rr = hex_col[0:2]
        gg = hex_col[2:4]
        bb = hex_col[4:6]
        aa = f"{int(opacity_float * 255):02x}"
        return aa + bb + gg + rr

    line_kml = to_kml_color(color, 1.0) # Line always full opacity? Or use fill_opacity? Usually line is opaque.
    
    fill_val = "0"
    fill_kml = "00000000"
    if fill_color and fill_opacity > 0:
        fill_val = "1"
        fill_kml = to_kml_color(fill_color, fill_opacity)
    
    kml_header = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Style id="polyStyle">
      <LineStyle>
        <color>{line_kml}</color>
        <width>{width}</width>
      </LineStyle>
      <PolyStyle>
        <color>{fill_kml}</color>
        <fill>{fill_val}</fill>
      </PolyStyle>
    </Style>
    <Placemark>
      <name>{name}</name>
      <styleUrl>#polyStyle</styleUrl>
      <MultiGeometry>
"""
    kml_footer = """      </MultiGeometry>
    </Placemark>
  </Document>
</kml>
"""
    
    polys = []
    if isinstance(geometry, Polygon):
        polys = [geometry]
    elif isinstance(geometry, MultiPolygon):
        polys = list(geometry.geoms)
        
    body = []
    for poly in polys:
        if poly.is_empty:
            continue
            
        # Exterior
        body.append("        <Polygon>")
        body.append("          <altitudeMode>absolute</altitudeMode>")
        body.append("          <outerBoundaryIs><LinearRing><coordinates>")
        body.append(_coords_to_kml_str(poly.exterior.coords, altitude))
        body.append("          </coordinates></LinearRing></outerBoundaryIs>")
        
        # Interiors (holes)
        for interior in poly.interiors:
            body.append("          <innerBoundaryIs><LinearRing><coordinates>")
            body.append(_coords_to_kml_str(interior.coords, altitude))
            body.append("          </coordinates></LinearRing></innerBoundaryIs>")
            
        body.append("        </Polygon>")
        
    content = kml_header + "\n".join(body) + kml_footer
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")

def geodesic_circle_coords(lon: float, lat: float, radius_m: float, segments: int = 180) -> List[str]:
    coords: List[str] = []
    for i in range(segments):
        az = (360.0 * i) / segments
        lon2, lat2, _ = GEOD.fwd(lon, lat, az, radius_m)
        coords.append(f"{lon2},{lat2},0")
    coords.append(coords[0])
    return coords

def kml_ring_placemark(name: str, coords: List[str], line_color_hex: str, line_width: int, fill_color_hex: str | None, fill_opacity: float) -> str:
    # KML color format aabbggrr (little-endian style); convert from #RRGGBB + opacity
    def to_kml_color(hex_color: str, opacity: float) -> str:
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            hex_color = 'FFA500'  # default orange
        rr = hex_color[0:2]
        gg = hex_color[2:4]
        bb = hex_color[4:6]
        aa = f"{int(opacity * 255):02x}"
        # KML wants aabbggrr
        return aa + bb + gg + rr
    line_color_kml = to_kml_color(line_color_hex, 1.0)
    if fill_color_hex and fill_opacity > 0:
        poly_color_kml = to_kml_color(fill_color_hex, fill_opacity)
        fill_tag = f"<PolyStyle><color>{poly_color_kml}</color></PolyStyle>"
    else:
        fill_tag = "<PolyStyle><fill>0</fill></PolyStyle>"
    coord_str = " ".join(coords)
    return (
        f"<Placemark><name>{name}</name><Style><LineStyle><color>{line_color_kml}</color><width>{line_width}</width></LineStyle>{fill_tag}</Style>"
        f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coord_str}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
    )

def export_horizons_kml(path: str, rings: Dict[str, List[Tuple[float, float]]], radars_meta: Dict[str, Tuple[float, float]], style: Dict):
    parts = [KML_HEADER]
    for radar_name, entries in rings.items():
        lon, lat = radars_meta[radar_name]
        for alt, dist_m in entries:
            coords = geodesic_circle_coords(lon, lat, dist_m)
            placemark_name = f"{radar_name}_ALT_{int(alt)}m"
            parts.append(
                kml_ring_placemark(
                    placemark_name,
                    coords,
                    style.get("line_color", "#FFA500"),
                    style.get("line_width", 2),
                    style.get("fill_color"),
                    style.get("fill_opacity", 0.0),
                )
            )
    parts.append(KML_FOOTER)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

__all__ = ["export_horizons_kml"]
