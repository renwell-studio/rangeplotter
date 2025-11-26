from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Union, List

@dataclass
class RadarSite:
    name: str
    longitude: float
    latitude: float
    altitude_mode: str  # clampToGround | relativeToGround | absolute
    input_altitude: Optional[float]  # Raw altitude value from KML (may be 0 or None)
    ground_elevation_m_msl: Optional[float] = None  # To be populated after DEM query
    sensor_height_m_agl: Union[float, List[float]] = 5.0
    description: Optional[str] = None
    style_url: Optional[str] = None
    style_config: Optional[dict] = None

    @property
    def radar_height_m_msl(self) -> Optional[float]:
        """
        Returns the radar height MSL.
        If sensor_height_m_agl is a list, this property returns the MSL height using the MAX value in the list.
        This is primarily used for horizon calculation (max possible horizon).
        For individual viewshed calculations, sensor_height_m_agl should be temporarily set to a float.
        """
        if self.ground_elevation_m_msl is None:
            return None
            
        # Handle list case by taking max
        h_agl = self.sensor_height_m_agl
        if isinstance(h_agl, list):
            h_agl = max(h_agl)
            
        if self.altitude_mode == "clampToGround":
            return self.ground_elevation_m_msl + h_agl
        if self.altitude_mode == "relativeToGround":
            return self.ground_elevation_m_msl + (self.input_altitude or 0.0) + h_agl
        if self.altitude_mode == "absolute":
            # input_altitude is already MSL
            return (self.input_altitude or self.ground_elevation_m_msl) + h_agl
        # Fallback
        return self.ground_elevation_m_msl + h_agl

__all__ = ["RadarSite"]
