"""
Shutdown handling for graceful Ctrl-C interruption.

This module provides a simple mechanism for signaling and checking
shutdown requests across the application.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

# Module-level state
_shutdown_requested = False
_force_quit = False

def request_shutdown():
    """Signal that a graceful shutdown has been requested."""
    global _shutdown_requested
    _shutdown_requested = True

def request_force_quit():
    """Signal that an immediate force quit has been requested."""
    global _shutdown_requested, _force_quit
    _shutdown_requested = True
    _force_quit = True

def is_shutdown_requested() -> bool:
    """Check if a graceful shutdown has been requested."""
    return _shutdown_requested

def is_force_quit_requested() -> bool:
    """Check if a force quit has been requested."""
    return _force_quit

def reset_shutdown_state():
    """Reset all shutdown flags. Called at start of each command."""
    global _shutdown_requested, _force_quit
    _shutdown_requested = False
    _force_quit = False

def cleanup_temp_cache_files(cache_dir: Optional[Path] = None):
    """Remove any .tmp.* files from viewshed cache directory.
    
    Args:
        cache_dir: Optional explicit cache directory. If not provided,
                   attempts to load from settings or uses default.
    """
    if cache_dir is None:
        try:
            from rangeplotter.config.settings import load_settings
            settings = load_settings()
            cache_dir = Path(settings.cache_dir) / "viewsheds"
        except Exception:
            cache_dir = Path("data_cache/viewsheds")
    
    if cache_dir.exists():
        for tmp_file in cache_dir.glob("*.tmp.*"):
            try:
                tmp_file.unlink()
            except OSError:
                pass

__all__ = [
    "request_shutdown",
    "request_force_quit",
    "is_shutdown_requested",
    "is_force_quit_requested",
    "reset_shutdown_state",
    "cleanup_temp_cache_files",
]
