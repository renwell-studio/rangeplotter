from __future__ import annotations
from typing import List, Dict
from rangeplotter.models.radar_site import RadarSite
from rangeplotter.geo.earth import mutual_horizon_distance

def compute_horizons(radars: List[RadarSite], altitudes_msl: List[float], k: float) -> Dict[str, List[tuple]]:
    """Return dict mapping radar name -> list of (altitude_msl, distance_m_msl)."""
    results: Dict[str, List[tuple]] = {}
    for r in radars:
        # Until DEM integration, assume ground elevation ~ input altitude if absolute, else 0.
        if r.ground_elevation_m_msl is None:
            if r.altitude_mode == "absolute" and r.input_altitude is not None:
                r.ground_elevation_m_msl = r.input_altitude
            else:
                r.ground_elevation_m_msl = 0.0
        radar_height = r.radar_height_m_msl or 0.0
        ring_list: List[tuple] = []
        for alt in altitudes_msl:
            # Mutual horizon distance between radar height and target altitude plane.
            d_max = mutual_horizon_distance(radar_height, alt, r.latitude, k)
            ring_list.append((alt, d_max))
        results[r.name] = ring_list
    return results

__all__ = ["compute_horizons"]
