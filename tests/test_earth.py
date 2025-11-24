
import math
from rangeplotter.geo.earth import mutual_horizon_distance, single_horizon_distance

def test_single_horizon():
    # h = 100m, k=1.333
    # R approx 6371km * 1.333
    # d = sqrt(2 * R * h)
    # Just check it returns a reasonable positive number
    d = single_horizon_distance(100, 0, 1.333)
    assert d > 0
    assert isinstance(d, float)

def test_mutual_horizon():
    h1 = 100
    h2 = 100
    d = mutual_horizon_distance(h1, h2, 0, 1.333)
    d_single = single_horizon_distance(h1, 0, 1.333)
    assert math.isclose(d, d_single * 2, rel_tol=1e-5)
