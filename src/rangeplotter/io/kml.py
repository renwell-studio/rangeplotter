from __future__ import annotations
from xml.etree import ElementTree as ET
from typing import List
from rangeplotter.models.radar_site import RadarSite

KML_NS = "{http://www.opengis.net/kml/2.2}"

ALTITUDE_MODES = {"clampToGround", "relativeToGround", "absolute"}

def parse_radars(kml_path: str, default_radome_height_m: float) -> List[RadarSite]:
    tree = ET.parse(kml_path)
    root = tree.getroot()
    radars: List[RadarSite] = []
    for pm in root.findall(f".//{KML_NS}Placemark"):
        name_el = pm.find(f"{KML_NS}name")
        name = name_el.text.strip() if name_el is not None else "Unnamed"
        alt_mode_el = pm.find(f"{KML_NS}altitudeMode")
        altitude_mode = alt_mode_el.text.strip() if alt_mode_el is not None else "clampToGround"
        if altitude_mode not in ALTITUDE_MODES:
            altitude_mode = "clampToGround"
        coord_el = pm.find(f".//{KML_NS}Point/{KML_NS}coordinates")
        if coord_el is None:
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

__all__ = ["parse_radars"]
