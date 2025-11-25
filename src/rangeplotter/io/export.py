from __future__ import annotations
from typing import Dict, List, Tuple, Union, Optional, Any
import math
from pathlib import Path
from pyproj import Geod
from shapely.geometry import Polygon, MultiPolygon, Point
from xml.sax.saxutils import escape

KML_HEADER = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<kml xmlns=\"http://www.opengis.net/kml/2.2\"><Document>"""
KML_FOOTER = "</Document></kml>"

GEOD = Geod(ellps="WGS84")

def _coords_to_kml_str(coords, altitude: float = 0.0) -> str:
    """Convert list of (lon, lat) or (lon, lat, z) to KML coordinate string."""
    return " ".join(f"{c[0]},{c[1]},{altitude}" for c in coords)

def to_kml_color(hex_col: str, opacity_float: float) -> str:
    """Convert hex #RRGGBB to KML aabbggrr."""
    hex_col = hex_col.lstrip('#')
    if len(hex_col) != 6:
        return "ff0000ff" # Default red
    rr = hex_col[0:2]
    gg = hex_col[2:4]
    bb = hex_col[4:6]
    aa = f"{int(opacity_float * 255):02x}"
    return aa + bb + gg + rr

def export_viewshed_kml(
    viewshed_polygon: Union[Polygon, MultiPolygon],
    output_path: Path,
    altitude: float,
    style_config: dict,
    sensors: Optional[List[Dict[str, Any]]] = None,
    document_name: Optional[str] = None,
    altitude_mode: str = "msl"
) -> None:
    """
    Export a viewshed to a self-contained KML file with sensor location(s) and polygon.
    
    altitude_mode: 'msl' (absolute) or 'agl' (relativeToGround).
    """
    # Normalize inputs
    if sensors is None:
        sensors = []
    
    if document_name is None:
        document_name = "Viewshed Output"
    
    # Polygon style
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
        f'    <name>{escape(document_name)}</name>',
    ]
    
    # Generate styles for each sensor
    # To avoid duplicate IDs, we can use a hash or index.
    # Or just embed styles? KML prefers shared styles.
    # Let's generate a style for each sensor if they differ.
    
    # For simplicity, let's define a default sensor style and then specific ones if needed.
    # Actually, let's just write a style for each sensor using its index to ensure uniqueness.
    
    for i, sensor in enumerate(sensors):
        s_config = sensor.get('style_config', {})
        icon_href = s_config.get("icon_href", "http://maps.google.com/mapfiles/kml/shapes/target.png")
        icon_scale = s_config.get("icon_scale", 1.0)
        icon_color = s_config.get("icon_color", None)
        
        kml_content.extend([
            f'    <Style id="sensorStyle_{i}">',
            '      <IconStyle>',
            f'        <scale>{icon_scale}</scale>',
            f'        <Icon><href>{icon_href}</href></Icon>',
        ])
        if icon_color:
            kml_content.append(f'        <color>{icon_color}</color>')
        kml_content.extend([
            '      </IconStyle>',
            '    </Style>'
        ])

    kml_content.extend([
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
    ])
    
    # Add Sensor Placemarks
    for i, sensor in enumerate(sensors):
        name = sensor['name']
        loc = sensor['location']
        kml_content.extend([
            '      <Placemark>',
            f'        <name>{escape(name)}</name>',
            f'        <styleUrl>#sensorStyle_{i}</styleUrl>',
            '        <Point>',
            f'          <coordinates>{loc[0]},{loc[1]},0</coordinates>',
            '        </Point>',
            '      </Placemark>'
        ])

    # Add Viewshed Placemark
    # If it's a union, we use document_name or constructed name.
    # If it's a single sensor, we might want to use "viewshed-{sensor_name}"
    # But document_name is already set to that in the single case.
    # So using document_name is safe.
    
    # Wait, if document_name is "MyRun", the polygon name becomes "MyRun".
    # The user said: "never used ... for polygons which have not been unioned".
    # If not unioned (single sensor), document_name is "viewshed-{sensor}-..." (calculated above).
    # If unioned (detection-range with --name), document_name is "MyRun".
    # So using document_name seems correct for the Polygon name too?
    # "The use of a supplied --name should be applied ... within the kml filenames themselves, but never used in placemarks ... or for polygons which have not been unioned"
    
    # If I supply --name "MyRun" for a SINGLE sensor:
    # document_name = "MyRun"
    # Polygon Name = "MyRun" -> This violates "never used ... for polygons which have not been unioned".
    # It should be "viewshed-{sensor}-...".
    
    # So I need a separate `polygon_name` argument or logic.
    
    poly_name = document_name
    # Heuristic: if document_name doesn't start with "viewshed-" and we have 1 sensor, maybe revert to default?
    # But detection-range passes base_name as document_name.
    
    # Let's just use a generic name if it's a union, or specific if single.
    # Actually, let's construct the polygon name based on sensors if possible?
    # If len(sensors) == 1, use "viewshed-{sensors[0]['name']}-..."
    # If len(sensors) > 1, use document_name (which is likely "Union" or "MyRun").
    
    alt_str = f"{int(altitude)}" if altitude.is_integer() else f"{altitude}"
    
    poly_name = document_name

    kml_content.extend([
        '      <Placemark>',
        f'        <name>{escape(poly_name)}</name>',
        '        <styleUrl>#polyStyle</styleUrl>',
        '        <MultiGeometry>'
    ])

    polys = []
    if isinstance(viewshed_polygon, Polygon):
        polys = [viewshed_polygon]
    elif isinstance(viewshed_polygon, MultiPolygon):
        polys = list(viewshed_polygon.geoms)
        
    for poly in polys:
        if poly.is_empty:
            continue
            
        # Determine KML altitude mode
        kml_alt_mode = "absolute"
        if altitude_mode.lower() == "agl":
            kml_alt_mode = "relativeToGround"
            
        # Exterior
        kml_content.append("        <Polygon>")
        kml_content.append(f"          <altitudeMode>{kml_alt_mode}</altitudeMode>")
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
      <name>{escape(name)}</name>
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
    """
    Export horizon rings to a KML file with shared styles and folder structure.
    """
    line_color = style.get("line_color", "#FFA500")
    line_width = style.get("line_width", 2)
    fill_color = style.get("fill_color", None)
    fill_opacity = style.get("fill_opacity", 0.0)

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
        '    <name>Geometric Horizons</name>',
        '    <Style id="sensorStyle">',
        '      <IconStyle>',
        '        <scale>1.0</scale>',
        '        <Icon><href>http://maps.google.com/mapfiles/kml/shapes/target.png</href></Icon>',
        '      </IconStyle>',
        '    </Style>',
        '    <Style id="horizonStyle">',
        '      <LineStyle>',
        f'        <color>{line_kml}</color>',
        f'        <width>{line_width}</width>',
        '      </LineStyle>',
        '      <PolyStyle>',
        f'        <color>{fill_kml}</color>',
        f'        <fill>{fill_val}</fill>',
        '      </PolyStyle>',
        '    </Style>'
    ]

    for radar_name, entries in rings.items():
        lon, lat = radars_meta[radar_name]
        
        kml_content.append('    <Folder>')
        kml_content.append(f'      <name>{escape(radar_name)}</name>')
        
        # Sensor Placemark
        kml_content.extend([
            '      <Placemark>',
            f'        <name>{escape(radar_name)}</name>',
            '        <styleUrl>#sensorStyle</styleUrl>',
            '        <Point>',
            f'          <coordinates>{lon},{lat},0</coordinates>',
            '        </Point>',
            '      </Placemark>'
        ])

        # Horizon Rings
        for alt, dist_m in entries:
            coords = geodesic_circle_coords(lon, lat, dist_m)
            coord_str = " ".join(coords)
            
            alt_label = f"{int(alt)}" if alt.is_integer() else f"{alt}"
            
            kml_content.extend([
                '      <Placemark>',
                f'        <name>Horizon ({alt_label}m target altitude)</name>',
                '        <styleUrl>#horizonStyle</styleUrl>',
                '        <Polygon>',
                '          <outerBoundaryIs><LinearRing><coordinates>',
                f'            {coord_str}',
                '          </coordinates></LinearRing></outerBoundaryIs>',
                '        </Polygon>',
                '      </Placemark>'
            ])
            
        kml_content.append('    </Folder>')

    kml_content.append('  </Document>')
    kml_content.append('</kml>')

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(kml_content))

def export_combined_kml(
    output_path: Path,
    radars_data: List[dict],
    styles: List[str],
    style_config: dict,
    document_name: str = "Viewshed Analysis"
) -> None:
    """
    Export multiple radars and their viewsheds to a single KML file.
    radars_data: List of dicts {'radar': RadarSite, 'viewsheds': {alt: poly}}
    """
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
        f'    <name>{escape(document_name)}</name>'
    ]
    
    # Add extracted styles
    for style_xml in styles:
        kml_content.append(style_xml)
        
    # Add default styles if not present (or always add them with unique IDs)
    kml_content.extend([
        '    <Style id="defaultSensorStyle">',
        '      <IconStyle>',
        '        <scale>1.0</scale>',
        '        <Icon><href>http://maps.google.com/mapfiles/kml/shapes/target.png</href></Icon>',
        '      </IconStyle>',
        '    </Style>',
        '    <Style id="defaultPolyStyle">',
        '      <LineStyle>',
        f'        <color>{line_kml}</color>',
        f'        <width>{line_width}</width>',
        '      </LineStyle>',
        '      <PolyStyle>',
        f'        <color>{fill_kml}</color>',
        f'        <fill>{fill_val}</fill>',
        '      </PolyStyle>',
        '    </Style>'
    ])
    
    use_folders = len(radars_data) > 1
    
    for item in radars_data:
        radar = item['radar']
        viewsheds = item['viewsheds']
        
        indent = "    "
        if use_folders:
            kml_content.append(f'{indent}<Folder>')
            kml_content.append(f'{indent}  <name>{escape(radar.name)}</name>')
            indent += "  "
            
        # Sensor Placemark
        style_url = radar.style_url if radar.style_url else "#defaultSensorStyle"
        kml_content.append(f'{indent}<Placemark>')
        kml_content.append(f'{indent}  <name>{escape(radar.name)}</name>')
        if radar.description:
             # Wrap description in CDATA to handle HTML content safely
             kml_content.append(f'{indent}  <description><![CDATA[{radar.description}]]></description>')
        kml_content.append(f'{indent}  <styleUrl>{style_url}</styleUrl>')
        kml_content.append(f'{indent}  <Point>')
        kml_content.append(f'{indent}    <coordinates>{radar.longitude},{radar.latitude},0</coordinates>')
        kml_content.append(f'{indent}  </Point>')
        kml_content.append(f'{indent}</Placemark>')
        
        # Viewshed Placemarks
        for alt, poly in viewsheds.items():
            if poly.is_empty:
                continue
                
            kml_content.append(f'{indent}<Placemark>')
            kml_content.append(f'{indent}  <name>viewshed ({alt}m target altitude)</name>')
            kml_content.append(f'{indent}  <styleUrl>#defaultPolyStyle</styleUrl>')
            kml_content.append(f'{indent}  <MultiGeometry>')
            
            polys = []
            if isinstance(poly, Polygon):
                polys = [poly]
            elif isinstance(poly, MultiPolygon):
                polys = list(poly.geoms)
                
            for p in polys:
                if p.is_empty: continue
                kml_content.append(f'{indent}    <Polygon>')
                kml_content.append(f'{indent}      <altitudeMode>absolute</altitudeMode>')
                kml_content.append(f'{indent}      <outerBoundaryIs><LinearRing><coordinates>')
                kml_content.append(f'{indent}      {_coords_to_kml_str(p.exterior.coords, float(alt))}')
                kml_content.append(f'{indent}      </coordinates></LinearRing></outerBoundaryIs>')
                for interior in p.interiors:
                    kml_content.append(f'{indent}      <innerBoundaryIs><LinearRing><coordinates>')
                    kml_content.append(f'{indent}      {_coords_to_kml_str(interior.coords, float(alt))}')
                    kml_content.append(f'{indent}      </coordinates></LinearRing></innerBoundaryIs>')
                kml_content.append(f'{indent}    </Polygon>')
                
            kml_content.append(f'{indent}  </MultiGeometry>')
            kml_content.append(f'{indent}</Placemark>')
            
        if use_folders:
            kml_content.append('    </Folder>')
            
    kml_content.append('  </Document>')
    kml_content.append('</kml>')
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(kml_content))

__all__ = ["export_horizons_kml", "export_viewshed_kml", "export_combined_kml"]
