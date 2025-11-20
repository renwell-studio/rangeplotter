from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class RadarSite:
    name: str
    longitude: float
    latitude: float
    altitude_mode: str  # clampToGround | relativeToGround | absolute
    input_altitude: Optional[float]  # Raw altitude value from KML (may be 0 or None)
    ground_elevation_m_msl: Optional[float] = None  # To be populated after DEM query
    radome_height_agl_m: float = 5.0

    @property
    def radar_height_m_msl(self) -> Optional[float]:
        if self.ground_elevation_m_msl is None:
            return None
        if self.altitude_mode == "clampToGround":
            return self.ground_elevation_m_msl + self.radome_height_agl_m
        if self.altitude_mode == "relativeToGround":
            return self.ground_elevation_m_msl + (self.input_altitude or 0.0) + self.radome_height_agl_m
        if self.altitude_mode == "absolute":
            # input_altitude is already MSL
            return (self.input_altitude or self.ground_elevation_m_msl) + self.radome_height_agl_m
        # Fallback
        return self.ground_elevation_m_msl + self.radome_height_agl_m

__all__ = ["RadarSite"]
