import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from rangeplotter.models.radar_site import RadarSite

class StateManager:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.state_file = output_dir / ".rangeplotter_state.json"
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_state(self):
        try:
            self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        except Exception:
            pass # Best effort

    def compute_hash(self, site: RadarSite, target_alt: float, refraction_k: float) -> str:
        """
        Compute a hash of the parameters that affect the viewshed calculation.
        Includes:
        - Site location (lat/lon)
        - Site effective height (MSL) - which includes ground elevation + sensor height
        - Target altitude
        - Physics constants (refraction)
        """
        # We use a fixed precision for floats to avoid floating point jitter
        # Note: radar_height_m_msl depends on ground_elevation_m_msl being populated
        h_msl = site.radar_height_m_msl
        h_val = f"{h_msl:.2f}" if h_msl is not None else "None"
        
        data = f"{site.name}|{site.latitude:.6f}|{site.longitude:.6f}|"
        data += f"{h_val}|"
        data += f"{target_alt:.2f}|{refraction_k:.3f}"
        
        return hashlib.md5(data.encode("utf-8")).hexdigest()

    def update_state(self, site_name: str, target_alt: float, current_hash: str, output_filename: str = None):
        """Update the state with the new hash for this task."""
        # We include the filename in the key to support multiple files per site/altitude (e.g. different sensor heights)
        # But wait, should_run uses site_name and target_alt as key.
        # If we have multiple sensor heights, we have multiple tasks for the same site/alt.
        # We need a unique key for each task.
        # The caller (main.py) passes filename to should_run, but should_run ignores it for key generation.
        # We should change the key strategy to be based on the filename or include the hash in the key?
        # Actually, if we use the filename as the key, it's unique.
        
        if output_filename:
            key = output_filename
        else:
            # Fallback for backward compatibility or if filename not provided (though it should be)
            key = f"{site_name}_{target_alt}"
            
        self.state[key] = current_hash
        self._save_state()

    def should_run(self, site_name: str, target_alt: float, current_hash: str, output_filename: str) -> bool:
        """
        Determine if the viewshed needs to be run.
        Returns True if:
        - Output file does not exist
        - Stored hash does not match current hash (params changed)
        - No hash stored
        """
        # Check if output file exists
        output_path = self.output_dir / output_filename
        if not output_path.exists():
            return True
            
        # Check if hash matches
        # Prefer filename as key if available in state (new format), fallback to old format
        key = output_filename
        stored_hash = self.state.get(key)
        
        if stored_hash is None:
             # Try legacy key
             legacy_key = f"{site_name}_{target_alt}"
             stored_hash = self.state.get(legacy_key)
        
        return stored_hash != current_hash
