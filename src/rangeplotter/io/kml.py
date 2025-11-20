from __future__ import annotations
from xml.etree import ElementTree as ET
from typing import List, Tuple, Optional, Union
from rangeplotter.models.radar_site import RadarSite
from shapely.geometry import Polygon, MultiPolygon

KML_NS = "{http://www.opengis.net/kml/2.2}"

ALTITUDE_MODES = {"clampToGround", "relativeToGround", "absolute"}

def parse_radars(kml_path: str, default_radome_height_m: float) -> List[RadarSite]:
    tree = ET.parse(kml_path)
    root = tree.getroot()
    radars: List[RadarSite] = []
    for pm in root.findall(f".//{KML_NS}Placemark"):
        name_el = pm.find(f"{KML_NS}name")
        name = name_el.text.strip() if name_el is not None and name_el.text else "Unnamed"
        alt_mode_el = pm.find(f"{KML_NS}altitudeMode")
        altitude_mode = alt_mode_el.text.strip() if alt_mode_el is not None and alt_mode_el.text else "clampToGround"
        if altitude_mode not in ALTITUDE_MODES:
            altitude_mode = "clampToGround"
        coord_el = pm.find(f".//{KML_NS}Point/{KML_NS}coordinates")
        if coord_el is None or not coord_el.text:
            continue
        coord_text = coord_el.text.strip()
        parts = coord_text.split(",")
        if len(parts) < 2:
            continue
        lon = float(parts[0])
        lat = float(parts[1])
        alt = None
        if len(parts) > 2:
            try:
                alt = float(parts[2])
            except ValueError:
                alt = None
        radars.append(RadarSite(
            name=name,
            longitude=lon,
            latitude=lat,
            altitude_mode=altitude_mode,
            input_altitude=alt,
            radome_height_agl_m=default_radome_height_m,
        ))
    return radars

def parse_viewshed_kml(kml_path: str) -> Tuple[Optional[Tuple[float, float]], Optional[Union[Polygon, MultiPolygon]]]:
    """
    Parse a viewshed KML file to extract the sensor location and the viewshed polygon.
    Returns ((lon, lat), geometry).
    """
    tree = ET.parse(kml_path)
    root = tree.getroot()
    
    sensor_loc = None
    viewshed_poly = None
    
    # Find all Placemarks
    for pm in root.findall(f".//{KML_NS}Placemark"):
        name = pm.find(f"{KML_NS}name")
        name_text = name.text if name is not None and name.text else ""
        
        # Check for Point (Sensor Location)
        point = pm.find(f"{KML_NS}Point")
        if point is not None:
            # Heuristic: check name or if we haven't found one yet
            if "Location" in name_text or sensor_loc is None:
                coords = point.find(f"{KML_NS}coordinates")
                if coords is not None and coords.text:
                    parts = coords.text.strip().split(',')
                    if len(parts) >= 2:
                        sensor_loc = (float(parts[0]), float(parts[1]))
                    
        # Check for Polygon or MultiGeometry (Viewshed)
        def extract_polygon(poly_el) -> Optional[Polygon]:
            outer = poly_el.find(f"{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates")
            if outer is not None and outer.text:
                coords_str = outer.text.strip()
                points = []
                for p in coords_str.split():
                    parts = p.split(',')
                    if len(parts) >= 2:
                        points.append((float(parts[0]), float(parts[1])))
                
                if points:
                    # Handle inner boundaries (holes)
                    holes = []
                    for inner in poly_el.findall(f"{KML_NS}innerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates"):
                        if inner.text:
                            h_points = []
                            for p in inner.text.strip().split():
                                parts = p.split(',')
                                if len(parts) >= 2:
                                    h_points.append((float(parts[0]), float(parts[1])))
                            if h_points:
                                holes.append(h_points)
                                
                    return Polygon(shell=points, holes=holes)
            return None

        if "Viewshed" in name_text or viewshed_poly is None:
            poly = pm.find(f"{KML_NS}Polygon")
            multi = pm.find(f"{KML_NS}MultiGeometry")
            
            if poly is not None:
                p = extract_polygon(poly)
                if p:
                    viewshed_poly = p
            elif multi is not None:
                polys = []
                for p_el in multi.findall(f"{KML_NS}Polygon"):
                    p = extract_polygon(p_el)
                    if p:
                        polys.append(p)
                if polys:
                    viewshed_poly = MultiPolygon(polys)
                        
    return sensor_loc, viewshed_poly

def add_polygon_to_kml(kml_path: str, polygon: Union[Polygon, MultiPolygon], name: str, style_url: Optional[str] = None):
    """
    Add a polygon to an existing KML file.
    """
    ET.register_namespace("", "http://www.opengis.net/kml/2.2")
    tree = ET.parse(kml_path)
    root = tree.getroot()
    
    # Find a Folder to add to, or Document
    folder = root.find(f".//{KML_NS}Folder")
    if folder is None:
        folder = root.find(f".//{KML_NS}Document")
    
    if folder is None:
        # Should not happen for valid KML
        folder = root
        
    placemark = ET.SubElement(folder, f"{KML_NS}Placemark")
    name_el = ET.SubElement(placemark, f"{KML_NS}name")
    name_el.text = name
    
    if style_url:
        style = ET.SubElement(placemark, f"{KML_NS}styleUrl")
        style.text = style_url
        
    # Helper to create LinearRing coordinates
    def create_coords(coords):
        return " ".join([f"{x},{y},0" for x, y in coords])

    def create_poly_element(parent, poly_geom):
        poly_el = ET.SubElement(parent, f"{KML_NS}Polygon")
        alt_mode = ET.SubElement(poly_el, f"{KML_NS}altitudeMode")
        alt_mode.text = "absolute" # Assuming absolute for viewsheds
        
        outer = ET.SubElement(poly_el, f"{KML_NS}outerBoundaryIs")
        ring = ET.SubElement(outer, f"{KML_NS}LinearRing")
        coords = ET.SubElement(ring, f"{KML_NS}coordinates")
        coords.text = create_coords(poly_geom.exterior.coords)
        
        for interior in poly_geom.interiors:
            inner = ET.SubElement(poly_el, f"{KML_NS}innerBoundaryIs")
            ring = ET.SubElement(inner, f"{KML_NS}LinearRing")
            coords = ET.SubElement(ring, f"{KML_NS}coordinates")
            coords.text = create_coords(interior.coords)

    if isinstance(polygon, Polygon):
        create_poly_element(placemark, polygon)
    elif isinstance(polygon, MultiPolygon):
        multi = ET.SubElement(placemark, f"{KML_NS}MultiGeometry")
        for p in polygon.geoms:
            create_poly_element(multi, p)
            
    tree.write(kml_path, encoding="UTF-8", xml_declaration=True)

__all__ = ["parse_radars", "parse_viewshed_kml", "add_polygon_to_kml"]
