from __future__ import annotations
from xml.etree import ElementTree as ET
from typing import List, Tuple, Optional, Union
from rangeplotter.models.radar_site import RadarSite
from shapely.geometry import Polygon, MultiPolygon

KML_NS = "{http://www.opengis.net/kml/2.2}"

ALTITUDE_MODES = {"clampToGround", "relativeToGround", "absolute"}

def parse_radars(kml_path: str, default_sensor_height_m: float) -> List[RadarSite]:
    tree = ET.parse(kml_path)
    root = tree.getroot()
    
    # Extract styles map
    styles = {}
    for style in root.findall(f".//{KML_NS}Style"):
        style_id = style.get("id")
        if style_id:
            styles[f"#{style_id}"] = style
            
    # Extract StyleMaps
    style_maps = {}
    for sm in root.findall(f".//{KML_NS}StyleMap"):
        sm_id = sm.get("id")
        if sm_id:
            # Find the 'normal' key
            normal_style_url = None
            for pair in sm.findall(f"{KML_NS}Pair"):
                key = pair.find(f"{KML_NS}key")
                if key is not None and key.text == "normal":
                    url = pair.find(f"{KML_NS}styleUrl")
                    if url is not None:
                        normal_style_url = url.text.strip()
                        break
            if normal_style_url:
                style_maps[f"#{sm_id}"] = normal_style_url

    def extract_style_from_element(element, style_url=None):
        """Extract style attributes from a Style element or styleUrl."""
        style_el = None
        
        # Resolve StyleMap if needed
        if style_url and style_url in style_maps:
            style_url = style_maps[style_url]
            
        if style_url and style_url in styles:
            style_el = styles[style_url]
        elif element is not None:
            style_el = element.find(f"{KML_NS}Style")
            
        if style_el is None:
            return {}
            
        config = {}
        
        # IconStyle
        icon_style = style_el.find(f"{KML_NS}IconStyle")
        if icon_style is not None:
            color = icon_style.find(f"{KML_NS}color")
            scale = icon_style.find(f"{KML_NS}scale")
            icon = icon_style.find(f"{KML_NS}Icon")
            
            if color is not None and color.text:
                kml_color = color.text.strip()
                if len(kml_color) == 8:
                    aa, bb, gg, rr = kml_color[0:2], kml_color[2:4], kml_color[4:6], kml_color[6:8]
                    hex_color = f"#{rr}{gg}{bb}"
                    # Use Icon color as default for Line/Poly if not specified?
                    config["line_color"] = hex_color
                    config["fill_color"] = hex_color
                    config["icon_color"] = kml_color # Keep original KML aabbggrr for IconStyle
            
            if scale is not None and scale.text:
                try:
                    config["icon_scale"] = float(scale.text)
                except ValueError:
                    pass
            
            if icon is not None:
                href = icon.find(f"{KML_NS}href")
                if href is not None and href.text:
                    config["icon_href"] = href.text.strip()
        
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

        alt_mode_el = pm.find(f".//{KML_NS}altitudeMode")
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
        
        # Determine sensor height logic
        # If KML specifies relativeToGround and a valid altitude, use that as the sensor height
        # and set the additional sensor_height_m_agl to 0 to avoid double counting.
        # If KML specifies absolute, we also assume the altitude includes the sensor height.
        # Otherwise, use the default sensor height from config.
        final_sensor_height = default_sensor_height_m
        if (altitude_mode == "relativeToGround" or altitude_mode == "absolute") and alt is not None:
            final_sensor_height = 0.0

        radars.append(RadarSite(
            name=name,
            longitude=lon,
            latitude=lat,
            altitude_mode=altitude_mode,
            input_altitude=alt,
            sensor_height_m_agl=final_sensor_height,
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
    style_maps = {}
    
    for style in root.findall(f".//{KML_NS}Style"):
        style_id = style.get("id")
        if style_id:
            styles[f"#{style_id}"] = style

    for style_map in root.findall(f".//{KML_NS}StyleMap"):
        map_id = style_map.get("id")
        if map_id:
            style_maps[f"#{map_id}"] = style_map
            
    def resolve_style(style_url):
        if not style_url:
            return None
        
        # If it's a StyleMap, resolve to normal style
        if style_url in style_maps:
            sm = style_maps[style_url]
            for pair in sm.findall(f"{KML_NS}Pair"):
                key = pair.find(f"{KML_NS}key")
                if key is not None and key.text == "normal":
                    url = pair.find(f"{KML_NS}styleUrl")
                    if url is not None and url.text:
                        return resolve_style(url.text.strip())
        
        # If it's a Style, return it
        if style_url in styles:
            return styles[style_url]
            
        return None
            
    def extract_style_from_element(element, style_url=None):
        """Extract style attributes from a Style element or styleUrl."""
        style_el = resolve_style(style_url)
        
        if style_el is None and element is not None:
            # Try finding inline style
            style_el = element.find(f"{KML_NS}Style")
            
        if style_el is None:
            return {}
            
        config = {}
        
        # IconStyle
        icon_style = style_el.find(f"{KML_NS}IconStyle")
        if icon_style is not None:
            color = icon_style.find(f"{KML_NS}color")
            scale = icon_style.find(f"{KML_NS}scale")
            icon = icon_style.find(f"{KML_NS}Icon")
            
            if color is not None and color.text:
                kml_color = color.text.strip()
                if len(kml_color) == 8:
                    aa, bb, gg, rr = kml_color[0:2], kml_color[2:4], kml_color[4:6], kml_color[6:8]
                    # hex_color = f"#{rr}{gg}{bb}"
                    config["icon_color"] = kml_color
            
            if scale is not None and scale.text:
                try:
                    config["icon_scale"] = float(scale.text)
                except ValueError:
                    pass
            
            if icon is not None:
                href = icon.find(f"{KML_NS}href")
                if href is not None and href.text:
                    config["icon_href"] = href.text.strip()
        
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
        sensor_name = None
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
                            sensor_name = name_text # Capture the name of the sensor placemark
                    
                    # Extract style from sensor placemark (IconStyle)
                    style_url = pm.find(f"{KML_NS}styleUrl")
                    s_url = style_url.text.strip() if style_url is not None else None
                    sensor_style = extract_style_from_element(pm, s_url)
                    style_config.update(sensor_style)
                    
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
                poly_style = extract_style_from_element(pm, s_url)
                style_config.update(poly_style)
                
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
        
        return sensor_loc, sensor_name, viewshed_poly, style_config

    # Strategy: Look for Folders.
    folders = root.findall(f".//{KML_NS}Folder")
    
    if folders:
        for folder in folders:
            name_el = folder.find(f"{KML_NS}name")
            folder_name = name_el.text.strip() if name_el is not None and name_el.text else None
            sensor, s_name, viewshed, style = extract_from_element(folder)
            if sensor and viewshed:
                results.append({'folder_name': folder_name, 'sensor': sensor, 'sensor_name': s_name, 'viewshed': viewshed, 'style': style})
    
    # If no results from folders, try the whole document (backward compatibility)
    if not results:
        sensor, s_name, viewshed, style = extract_from_element(root)
        if sensor and viewshed:
             results.append({'folder_name': None, 'sensor': sensor, 'sensor_name': s_name, 'viewshed': viewshed, 'style': style})
                        
    return results

__all__ = ["parse_radars", "parse_viewshed_kml"]
