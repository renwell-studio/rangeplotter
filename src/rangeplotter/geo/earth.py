from __future__ import annotations
import math
from typing import Tuple

WGS84_A = 6378137.0  # semi-major axis (m)
WGS84_F = 1 / 298.257223563
WGS84_E2 = 2 * WGS84_F - WGS84_F * WGS84_F

def local_radii_of_curvature(lat_deg: float) -> Tuple[float, float]:
    """Return (M, N) meridian and prime vertical radii at latitude (degrees)."""
    phi = math.radians(lat_deg)
    sin_phi = math.sin(phi)
    denom = math.sqrt(1 - WGS84_E2 * sin_phi * sin_phi)
    N = WGS84_A / denom
    M = WGS84_A * (1 - WGS84_E2) / (denom ** 3)
    return M, N

def gaussian_radius(lat_deg: float) -> float:
    M, N = local_radii_of_curvature(lat_deg)
    return math.sqrt(M * N)

def effective_earth_radius(lat_deg: float, k: float) -> float:
    return gaussian_radius(lat_deg) * k

def mutual_horizon_distance(observer_height_m: float, target_height_m: float, lat_deg: float, k: float) -> float:
    """Compute mutual LOS distance (m) between observer and target altitudes above MSL.
    d_max ≈ sqrt(2 * R_eff * h_obs) + sqrt(2 * R_eff * h_tgt)
    """
    R_eff = effective_earth_radius(lat_deg, k)
    return math.sqrt(2 * R_eff * observer_height_m) + math.sqrt(2 * R_eff * target_height_m)

def single_horizon_distance(observer_height_m: float, lat_deg: float, k: float) -> float:
    R_eff = effective_earth_radius(lat_deg, k)
    return math.sqrt(2 * R_eff * observer_height_m)

__all__ = [
    "local_radii_of_curvature",
    "gaussian_radius",
    "effective_earth_radius",
    "mutual_horizon_distance",
    "single_horizon_distance",
]
