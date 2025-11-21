from typing import List, Tuple, Union
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from pyproj import Geod

GEOD = Geod(ellps="WGS84")

def create_geodesic_buffer(lon: float, lat: float, radius_km: float, points: int = 128) -> Polygon:
    """
    Create a geodesic circle (buffer) around a point.
    """
    lons = []
    lats = []
    angles = [360.0 * i / points for i in range(points)]
    
    for angle in angles:
        lon_out, lat_out, _ = GEOD.fwd(lon, lat, angle, radius_km * 1000.0)
        lons.append(lon_out)
        lats.append(lat_out)
        
    return Polygon(zip(lons, lats))

def clip_viewshed(viewshed: Union[Polygon, MultiPolygon], sensor_loc: Tuple[float, float], radius_km: float) -> Union[Polygon, MultiPolygon]:
    """
    Clip the viewshed polygon with a geodesic buffer of the given radius.
    """
    buffer = create_geodesic_buffer(sensor_loc[0], sensor_loc[1], radius_km)
    
    # Ensure validity before intersection
    if not buffer.is_valid:
        buffer = buffer.buffer(0)
    
    if not viewshed.is_valid:
        viewshed = viewshed.buffer(0)
        
    try:
        clipped = viewshed.intersection(buffer)
    except Exception:
        # Fallback for topology errors
        # Try slightly buffering the viewshed to fix micro-self-intersections
        try:
            viewshed = viewshed.buffer(0.000001)
            clipped = viewshed.intersection(buffer)
        except Exception:
             # If still failing, return empty or original (depending on desired behavior, but empty is safer)
             return Polygon()

    return clipped

def union_viewsheds(viewsheds: List[Union[Polygon, MultiPolygon]]) -> Union[Polygon, MultiPolygon]:
    """
    Compute the geometric union of multiple viewsheds.
    """
    return unary_union(viewsheds)
