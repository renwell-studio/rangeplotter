from rangeplotter.processing import create_geodesic_buffer, clip_viewshed, union_viewsheds
from shapely.geometry import Polygon, Point
from unittest.mock import MagicMock

def test_create_geodesic_buffer():
    poly = create_geodesic_buffer(0, 0, 100) # 100km
    assert isinstance(poly, Polygon)
    assert poly.is_valid
    # Check approximate area or bounds?
    # 1 degree is approx 111km. 100km radius is approx 0.9 degrees.
    # Bounds should be roughly -0.9 to 0.9
    minx, miny, maxx, maxy = poly.bounds
    assert -1.0 < minx < -0.8
    assert 0.8 < maxx < 1.0

def test_clip_viewshed():
    # Create a large square viewshed
    viewshed = Polygon([(-2, -2), (2, -2), (2, 2), (-2, 2)])
    sensor = (0, 0)
    radius_km = 100 # Approx 0.9 degrees
    
    clipped = clip_viewshed(viewshed, sensor, radius_km)
    
    assert not clipped.is_empty
    assert clipped.area < viewshed.area
    # The clipped area should be roughly the area of the circle
    # Circle area ~ pi * r^2. r ~ 0.9 deg. Area ~ 2.5 sq deg.
    # Square area = 16.
    assert clipped.area < 4.0

def test_clip_viewshed_exception():
    viewshed = MagicMock()
    viewshed.is_valid = True
    # First intersection fails
    # Fallback buffer succeeds
    # Second intersection (after buffer) fails
    viewshed.intersection.side_effect = Exception("Topology error")
    viewshed.buffer.return_value = viewshed 
    
    clipped = clip_viewshed(viewshed, (0,0), 100)
    assert clipped.is_empty

def test_union_viewsheds():
    p1 = Polygon([(0,0), (1,0), (1,1), (0,1)])
    p2 = Polygon([(1,0), (2,0), (2,1), (1,1)])
    
    union = union_viewsheds([p1, p2])
    
    assert union.area == 2.0
    assert isinstance(union, Polygon) # Should merge into one
