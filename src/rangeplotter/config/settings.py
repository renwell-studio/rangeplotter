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
    target_altitude_reference: str = Field("msl", pattern="^(msl)$")
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

class Settings(BaseModel):
    input_dir: str = "working_files/input"
    output_viewshed_dir: str = "working_files/viewshed"
    output_horizon_dir: str = "working_files/horizon"
    output_detection_dir: str = "working_files/detection_range"
    cache_dir: str = "data_cache"
    altitudes_msl_m: List[float]
    radome_height_m_agl: float = 5.0
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

    @field_validator("altitudes_msl_m")
    @classmethod
    def sort_and_unique(cls, v):
        return sorted(set(v))

    @property
    def effective_altitudes(self) -> List[float]:
        return self.altitudes_msl_m

    def load_env_credentials(self):
        # Load .env first if present
        env_path = Path('.env')
        if env_path.exists():
            load_dotenv(env_path)
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
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        settings = cls(**data)
        settings.load_env_credentials()
        if not settings.copernicus_api.client_id:
            settings.copernicus_api.client_id = "cdse-public"
        return settings

__all__ = ["Settings"]
