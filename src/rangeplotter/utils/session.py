import json
from pathlib import Path
from typing import Optional, Dict, Any
import datetime

class SessionManager:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.session_file = work_dir / "last_session.json"

    def save_session(self, input_path: Path, output_dir: Path, config_path: Path, status: str = "incomplete"):
        """Save the current session details."""
        data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "input_path": str(input_path.absolute()),
            "output_dir": str(output_dir.absolute()),
            "config_path": str(config_path.absolute()),
            "status": status
        }
        try:
            self.session_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass # Best effort

    def update_status(self, status: str):
        """Update the status of the current session."""
        data = self.load_last_session()
        if data:
            data["status"] = status
            data["timestamp"] = datetime.datetime.now().isoformat() # Update timestamp on status change? Maybe.
            try:
                self.session_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass

    def load_last_session(self) -> Optional[Dict[str, Any]]:
        """Load the last session details."""
        if not self.session_file.exists():
            return None
        try:
            return json.loads(self.session_file.read_text(encoding="utf-8"))
        except Exception:
            return None
