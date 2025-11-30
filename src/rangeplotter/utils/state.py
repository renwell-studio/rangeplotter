import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from rangeplotter.models.radar_site import RadarSite
from rangeplotter.io.kml import read_metadata_from_kml

class StateManager:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        # Deprecated: .rangeplotter_state.json is no longer used for new checks,
        # but we keep the file path reference just in case we need to clean it up later.
        self.state_file = output_dir / ".rangeplotter_state.json"

    def compute_hash(self, site: RadarSite, target_alt: float, refraction_k: float, 
                     earth_radius_model: str = "ellipsoidal", max_range: float = 0.0,
                     sensor_height_m_agl: float = 0.0) -> str:
        """
        Compute a hash of the parameters that affect the viewshed calculation.
        Includes:
        - Site location (lat/lon)
        - Site effective height (MSL)
        - Target altitude
        - Physics constants (refraction, earth model)
        - Max range (horizon)
        - Sensor height AGL (explicitly)
        """
        # We use a fixed precision for floats to avoid floating point jitter
        h_msl = site.radar_height_m_msl
        h_val = f"{h_msl:.2f}" if h_msl is not None else "None"
        
        data = f"{site.name}|{site.latitude:.6f}|{site.longitude:.6f}|"
        data += f"{h_val}|{sensor_height_m_agl:.2f}|"
        data += f"{target_alt:.2f}|{refraction_k:.3f}|"
        data += f"{earth_radius_model}|{max_range:.1f}"
        
        return hashlib.md5(data.encode("utf-8")).hexdigest()

    def update_state(self, site_name: str, target_alt: float, current_hash: str, output_filename: str = None):
        """
        Deprecated: State is now embedded in the KML file itself.
        This method is kept for compatibility but does nothing.
        """
        pass

    def should_run(self, site_name: str, target_alt: float, current_hash: str, output_filename: str) -> bool:
        """
        Determine if the viewshed needs to be run.
        Returns True if:
        - Output file does not exist
        - Embedded hash in KML does not match current hash (params changed)
        - No hash found in KML
        """
        # Check if output file exists
        output_path = self.output_dir / output_filename
        if not output_path.exists():
            return True
            
        # Read metadata from KML
        metadata = read_metadata_from_kml(output_path)
        stored_hash = metadata.get("state_hash")
        
        if stored_hash is None:
             # If no hash in KML, we must re-run to ensure correctness and embed the hash
             return True
        
        return stored_hash != current_hash
