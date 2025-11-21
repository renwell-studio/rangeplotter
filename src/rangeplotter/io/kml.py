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
    
    # Extract styles map
    styles = {}
    for style in root.findall(f".//{KML_NS}Style"):
        style_id = style.get("id")
        if style_id:
            styles[f"#{style_id}"] = style

    def extract_style_from_element(element, style_url=None):
        """Extract style attributes from a Style element or styleUrl."""
        style_el = None
        if style_url and style_url in styles:
            style_el = styles[style_url]
        elif element is not None:
            style_el = element.find(f"{KML_NS}Style")
            
        if style_el is None:
            return {}
            
        config = {}
        
        # LineStyle
        line_style = style_el.find(f"{KML_NS}LineStyle")
        if line_style is not None:
            color = line_style.find(f"{KML_NS}color")
            width = line_style.find(f"{KML_NS}width")
            if color is not None and color.text:
                kml_color = color.text.strip()
                if len(kml_color) == 8:
                    aa, bb, gg, rr = kml_color[0:2], kml_color[2:4], kml_color[4:6], kml_color[6:8]
                    config["line_color"] = f"#{rr}{gg}{bb}"
            if width is not None and width.text:
                try:
                    config["line_width"] = float(width.text)
                except ValueError:
                    pass
                    
        # PolyStyle
        poly_style = style_el.find(f"{KML_NS}PolyStyle")
        if poly_style is not None:
            color = poly_style.find(f"{KML_NS}color")
            fill = poly_style.find(f"{KML_NS}fill")
            if color is not None and color.text:
                kml_color = color.text.strip()
                if len(kml_color) == 8:
                    aa, bb, gg, rr = kml_color[0:2], kml_color[2:4], kml_color[4:6], kml_color[6:8]
                    config["fill_color"] = f"#{rr}{gg}{bb}"
                    config["fill_opacity"] = int(aa, 16) / 255.0
            
        return config

    radars: List[RadarSite] = []
    for pm in root.findall(f".//{KML_NS}Placemark"):
        name_el = pm.find(f"{KML_NS}name")
        name = name_el.text.strip() if name_el is not None and name_el.text else "Unnamed"
        
        desc_el = pm.find(f"{KML_NS}description")
        description = desc_el.text.strip() if desc_el is not None and desc_el.text else None
        
        style_url_el = pm.find(f"{KML_NS}styleUrl")
        style_url = style_url_el.text.strip() if style_url_el is not None and style_url_el.text else None
        
        # Extract style config
        style_config = extract_style_from_element(pm, style_url)

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
            description=description,
            style_url=style_url,
            style_config=style_config
        ))
    return radars

def parse_viewshed_kml(kml_path: str) -> List[dict]:
    """
    Parse a viewshed KML file to extract sensor locations, viewshed polygons, and styles.
    Returns a list of dicts: {'folder_name': str, 'sensor': (lon, lat), 'viewshed': geometry, 'style': dict}
    """
    tree = ET.parse(kml_path)
    root = tree.getroot()
    
    # Extract styles map
    styles = {}
    for style in root.findall(f".//{KML_NS}Style"):
        style_id = style.get("id")
        if style_id:
            styles[f"#{style_id}"] = style
            
    def extract_style_from_element(element, style_url=None):
        """Extract style attributes from a Style element or styleUrl."""
        style_el = None
        if style_url and style_url in styles:
            style_el = styles[style_url]
        elif element is not None:
            style_el = element.find(f"{KML_NS}Style")
            
        if style_el is None:
            return {}
            
        config = {}
        
        # LineStyle
        line_style = style_el.find(f"{KML_NS}LineStyle")
        if line_style is not None:
            color = line_style.find(f"{KML_NS}color")
            width = line_style.find(f"{KML_NS}width")
            if color is not None and color.text:
                # KML is aabbggrr, we want #RRGGBB
                # But export expects hex string, let's just pass it through or convert?
                # export.py expects #RRGGBB.
                # KML: aabbggrr -> #rrggbb
                kml_color = color.text.strip()
                if len(kml_color) == 8:
                    aa, bb, gg, rr = kml_color[0:2], kml_color[2:4], kml_color[4:6], kml_color[6:8]
                    config["line_color"] = f"#{rr}{gg}{bb}"
            if width is not None and width.text:
                try:
                    config["line_width"] = float(width.text)
                except ValueError:
                    pass
                    
        # PolyStyle
        poly_style = style_el.find(f"{KML_NS}PolyStyle")
        if poly_style is not None:
            color = poly_style.find(f"{KML_NS}color")
            fill = poly_style.find(f"{KML_NS}fill")
            if color is not None and color.text:
                kml_color = color.text.strip()
                if len(kml_color) == 8:
                    aa, bb, gg, rr = kml_color[0:2], kml_color[2:4], kml_color[4:6], kml_color[6:8]
                    config["fill_color"] = f"#{rr}{gg}{bb}"
                    config["fill_opacity"] = int(aa, 16) / 255.0
            
        return config

    results = []

    def extract_from_element(element):
        sensor_loc = None
        viewshed_poly = None
        style_config = {}
        
        # Find all Placemarks in this element context
        for pm in element.findall(f".//{KML_NS}Placemark"):
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
                
                # Extract style
                style_url = pm.find(f"{KML_NS}styleUrl")
                s_url = style_url.text.strip() if style_url is not None else None
                style_config = extract_style_from_element(pm, s_url)
                
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
        
        return sensor_loc, viewshed_poly, style_config

    # Strategy: Look for Folders.
    folders = root.findall(f".//{KML_NS}Folder")
    
    if folders:
        for folder in folders:
            name_el = folder.find(f"{KML_NS}name")
            folder_name = name_el.text.strip() if name_el is not None and name_el.text else None
            sensor, viewshed, style = extract_from_element(folder)
            if sensor and viewshed:
                results.append({'folder_name': folder_name, 'sensor': sensor, 'viewshed': viewshed, 'style': style})
    
    # If no results from folders, try the whole document (backward compatibility)
    if not results:
        sensor, viewshed, style = extract_from_element(root)
        if sensor and viewshed:
             results.append({'folder_name': None, 'sensor': sensor, 'viewshed': viewshed, 'style': style})
                        
    return results

def add_polygon_to_kml(kml_path: str, polygon: Union[Polygon, MultiPolygon], name: str, style_url: Optional[str] = None, folder_name: Optional[str] = None):
    """
    Add a polygon to an existing KML file.
    """
    ET.register_namespace("", "http://www.opengis.net/kml/2.2")
    tree = ET.parse(kml_path)
    root = tree.getroot()
    
    target_folder = None
    
    if folder_name:
        # Find specific folder
        for f in root.findall(f".//{KML_NS}Folder"):
            fn = f.find(f"{KML_NS}name")
            if fn is not None and fn.text and fn.text.strip() == folder_name:
                target_folder = f
                break
    
    if target_folder is None:
        # Find a Folder to add to, or Document
        target_folder = root.find(f".//{KML_NS}Folder")
        if target_folder is None:
            target_folder = root.find(f".//{KML_NS}Document")
    
    if target_folder is None:
        # Should not happen for valid KML
        target_folder = root
        
    placemark = ET.SubElement(target_folder, f"{KML_NS}Placemark")
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

def extract_kml_styles(kml_path: str) -> List[str]:
    """
    Extract all Style and StyleMap elements from a KML file as XML strings.
    """
    ET.register_namespace("", "http://www.opengis.net/kml/2.2")
    tree = ET.parse(kml_path)
    root = tree.getroot()
    
    styles = []
    # Find all Style and StyleMap elements anywhere in the document
    for elem in root.findall(f".//{KML_NS}Style"):
        styles.append(ET.tostring(elem, encoding="unicode"))
    for elem in root.findall(f".//{KML_NS}StyleMap"):
        styles.append(ET.tostring(elem, encoding="unicode"))
        
    return styles

__all__ = ["parse_radars", "parse_viewshed_kml", "add_polygon_to_kml", "extract_kml_styles"]
