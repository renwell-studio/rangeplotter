from __future__ import annotations
from pathlib import Path
from typing import List, Optional
import os
from dotenv import load_dotenv
import yaml
from pydantic import BaseModel, Field, field_validator

class StyleConfig(BaseModel):
    line_color: str = "#FFA500"
    line_width: int = 2
    fill_color: Optional[str] = None
    fill_opacity: float = 0.0

class ConcurrencyConfig(BaseModel):
    mode: str = Field("process", pattern="^(process|thread)$")
    max_workers: int = 8
    reserve_cpus: int = 4

class ResourcesConfig(BaseModel):
    max_ram_percent: float = 80.0
    use_disk_swap: bool = True

class ProgressConfig(BaseModel):
    enabled: bool = True
    refresh_hz: int = 10

class EarthModelConfig(BaseModel):
    type: str = Field("ellipsoidal", pattern="^(ellipsoidal)$")
    ellipsoid: str = "WGS84"

class VerticalConfig(BaseModel):
    dem_vertical_reference: str = "EGM2008"

class MultiscaleConfig(BaseModel):
    enable: bool = True
    near_m: int = 50_000
    mid_m: int = 200_000
    far_m: int = 800_000
    res_near_m: int = 30
    res_mid_m: int = 120
    res_far_m: int = 1000

class CopernicusAPIConfig(BaseModel):
    base_url: str
    token_url: str
    client_id: Optional[str] = None  # defaults to cdse-public if None
    # Runtime / env-sourced credentials (DO NOT put real values in YAML ideally)
    username: Optional[str] = None
    password: Optional[str] = None
    refresh_token: Optional[str] = None
    dataset_identifier: Optional[str] = None  # e.g. "COP-DEM_GLO-30" to narrow products

import sys

class Settings(BaseModel):
    input_dir: str = "working_files/input"
    output_viewshed_dir: str = "working_files/viewshed"
    output_horizon_dir: str = "working_files/horizon"
    output_detection_dir: str = "working_files/detection_range"
    cache_dir: str = "data_cache"
    altitudes_msl_m: List[float]
    target_altitude_reference: str = Field("msl", pattern="^(msl|agl)$")
    kml_export_altitude_mode: str = Field("clamped", pattern="^(clamped|absolute)$")
    sensor_height_m_agl: float = 5.0
    atmospheric_k_factor: float = 1.333
    working_crs_strategy: str = Field("auto_aeqd", pattern=r"^(auto_aeqd|manual:EPSG:\d+)$")
    max_threads: int = 8
    simplify_tolerance_m: float = 5.0
    export_format: str = Field("KML", pattern="^(KML|KMZ|GeoJSON)$")
    precision: int = 9
    style: StyleConfig = StyleConfig()
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    resources: ResourcesConfig = ResourcesConfig()
    progress: ProgressConfig = ProgressConfig()
    earth_model: EarthModelConfig = EarthModelConfig()
    vertical: VerticalConfig = VerticalConfig()
    multiscale: MultiscaleConfig = MultiscaleConfig()
    copernicus_api: CopernicusAPIConfig
    logging: dict = Field(default_factory=lambda: {"level": "INFO"})
    detection_ranges: List[float] = []
    
    # Internal field to track where config was loaded from
    _config_base_path: Optional[Path] = None

    @field_validator("altitudes_msl_m")
    @classmethod
    def sort_and_unique(cls, v):
        return sorted(set(v))

    @property
    def effective_altitudes(self) -> List[float]:
        return self.altitudes_msl_m

    def resolve_path(self, path_str: str) -> Path:
        """
        Resolve a path relative to the project root (parent of config dir) if it's not absolute.
        
        If config is at /app/config/config.yaml, we want 'data_cache' to resolve to /app/data_cache,
        NOT /app/config/data_cache.
        """
        p = Path(path_str)
        if p.is_absolute():
            return p
        
        if self._config_base_path:
            # If config is in a 'config' subdirectory, go up one level to find the project root
            if self._config_base_path.name == 'config':
                return self._config_base_path.parent / p
            return self._config_base_path / p
        
        return Path.cwd() / p

    def load_env_credentials(self):
        # Load .env first if present
        # Try relative to config base path first
        if self._config_base_path:
             env_path = self._config_base_path / '.env'
             if env_path.exists():
                 load_dotenv(env_path)
        
        # Fallback to CWD .env
        env_path_cwd = Path('.env')
        if env_path_cwd.exists():
            load_dotenv(env_path_cwd)

        # Public client id override (defaults later if still None)
        cid = os.getenv("COPERNICUS_CLIENT_ID")
        if cid and not self.copernicus_api.client_id:
            self.copernicus_api.client_id = cid
        # Username / password (resource owner password grant)
        user = os.getenv("COPERNICUS_USERNAME")
        pwd = os.getenv("COPERNICUS_PASSWORD")
        rtok = os.getenv("COPERNICUS_REFRESH_TOKEN")
        did = os.getenv("COPERNICUS_DATASET_IDENTIFIER")
        if user and not self.copernicus_api.username:
            self.copernicus_api.username = user
        if pwd and not self.copernicus_api.password:
            self.copernicus_api.password = pwd
        if rtok and not self.copernicus_api.refresh_token:
            self.copernicus_api.refresh_token = rtok
        if did and not self.copernicus_api.dataset_identifier:
            self.copernicus_api.dataset_identifier = did

    @classmethod
    def from_file(cls, path: str | Path) -> "Settings":
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        settings = cls(**data)
        
        # Store the base path of the config file to resolve relative paths later
        settings._config_base_path = path.parent.absolute()
        
        settings.load_env_credentials()
        if not settings.copernicus_api.client_id:
            settings.copernicus_api.client_id = "cdse-public"
        return settings

def load_settings(config_name: str = "config.yaml") -> Settings:
    """
    Load settings by searching for config.yaml in priority order:
    1. Current Working Directory (./config/config.yaml)
    2. Executable Directory ({exe_dir}/config/config.yaml) - for portable installs
    3. Internal Fallback (bundled) - Not implemented yet, assumes file exists in one of the above.
    """
    # 1. Check CWD
    cwd_config = Path.cwd() / "config" / config_name
    if cwd_config.exists():
        return Settings.from_file(cwd_config)
    
    # 2. Check Executable Directory (useful for PyInstaller / portable zip)
    # sys.executable points to the python interpreter or the frozen binary
    exe_dir = Path(sys.executable).parent
    exe_config = exe_dir / "config" / config_name
    if exe_config.exists():
        return Settings.from_file(exe_config)
        
    # 3. Fallback: Try just "config.yaml" in CWD (legacy)
    legacy_config = Path.cwd() / config_name
    if legacy_config.exists():
        return Settings.from_file(legacy_config)

    raise FileNotFoundError(
        f"Could not find {config_name} in {cwd_config} or {exe_config}. "
        "Please ensure the 'config' folder is present."
    )

__all__ = ["Settings", "load_settings"]
