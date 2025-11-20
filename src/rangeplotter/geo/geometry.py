from __future__ import annotations
from shapely.geometry import Polygon, Point
from pyproj import Geod

def create_geodesic_circle(center_lon: float, center_lat: float, radius_km: float, num_points: int = 360) -> Polygon:
    """
    Create a geodesic circle (Polygon) on the WGS84 ellipsoid.
    
    Args:
        center_lon: Longitude of center in degrees.
        center_lat: Latitude of center in degrees.
        radius_km: Radius in kilometers.
        num_points: Number of vertices to approximate the circle.
        
    Returns:
        Shapely Polygon representing the circle.
    """
    geod = Geod(ellps="WGS84")
    radius_m = radius_km * 1000.0
    
    # npts returns list of (lon, lat)
    # We need to generate points around the circle.
    # pyproj.Geod.fwd() or similar can be used, or npts if we define a path?
    # Actually, Geod doesn't have a direct "circle" method, but we can generate points.
    
    lons = []
    lats = []
    
    # Generate azimuths
    azimuths = [i * (360.0 / num_points) for i in range(num_points)]
    
    for az in azimuths:
        lon, lat, _ = geod.fwd(center_lon, center_lat, az, radius_m)
        lons.append(lon)
        lats.append(lat)
        
    # Close the polygon
    lons.append(lons[0])
    lats.append(lats[0])
    
    return Polygon(zip(lons, lats))
