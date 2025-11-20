"""Copernicus GLO-30 DEM client skeleton.

This module provides a placeholder implementation for:
 - Token handling via CDSE password / refresh grant (delegated to auth module).
 - Tile query given a bounding box.
 - Download + caching stubs.

Actual API specifics (collection IDs, OData filters) must be filled once
dataset endpoints for COP-DEM are integrated.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import time
import sys
import json
from urllib.parse import quote
import zipfile
import io
import shutil

import requests
import rasterio
from shapely.geometry import box, Polygon
from shapely import wkt
from shapely.ops import unary_union
from rich import print
from rich.progress import track, Progress, SpinnerColumn, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn

try:
    from rangeplotter.auth.cdse import CdseAuth  # type: ignore
except Exception:  # pragma: no cover
    CdseAuth = None  # type: ignore


@dataclass
class DemTile:
    id: str
    bbox: Tuple[float, float, float, float]  # minx, miny, maxx, maxy (lon/lat)
    local_path: Path
    downloaded: bool = False


class DemClient:
    def __init__(self, base_url: str, auth: Optional["CdseAuth"], cache_dir: Path, verbose: int = 0):
        self.base_url = base_url.rstrip("/")  # Expected: https://catalogue.dataspace.copernicus.eu/odata/v1
        self.auth = auth
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self._index_path = self.cache_dir / "index.json"
        if not self._index_path.exists():
            self._index_path.write_text("{}", encoding="utf-8")
        self.total_download_time = 0.0

    def _log(self, msg: str, is_error: bool = False, level: int = 1):
        if is_error:
            sys.stderr.write(f"[DEM ERROR] {msg}\n")
            sys.stderr.flush()
        elif self.verbose >= level:
            sys.stderr.write(f"[DEM] {msg}\n")
            sys.stderr.flush()

    def _access_token(self) -> Optional[str]:
        if not self.auth:
            return None
        return self.auth.ensure_access_token()

    def _bbox_polygon_wkt(self, bbox: Tuple[float, float, float, float]) -> str:
        minx, miny, maxx, maxy = bbox
        return f"POLYGON(({minx} {miny},{minx} {maxy},{maxx} {maxy},{maxx} {miny},{minx} {miny}))"

    def _odata_products_url(self) -> str:
        return f"{self.base_url}/Products"

    def _load_index(self) -> dict:
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_index(self, idx: dict) -> None:
        try:
            self._index_path.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        except Exception as e:
            self._log(f"Failed to save DEM index: {e}", is_error=True)

    def query_tiles(self, bbox: Tuple[float, float, float, float], limit: int = 20) -> List[DemTile]:
        """Query COP-DEM products intersecting bbox. If auth missing, return synthetic tile."""
        if not self.auth:
            minx, miny, maxx, maxy = bbox
            tile_id = f"synthetic_{minx:.3f}_{miny:.3f}_{maxx:.3f}_{maxy:.3f}"
            path = self.cache_dir / f"{tile_id}.tif"
            return [DemTile(id=tile_id, bbox=bbox, local_path=path, downloaded=path.exists())]
        token = self._access_token()
        if not token or not isinstance(token, str):
            self._log("No valid access token; falling back to synthetic tile.", is_error=True)
            minx, miny, maxx, maxy = bbox
            tile_id = f"synthetic_{minx:.3f}_{miny:.3f}_{maxx:.3f}_{maxy:.3f}"
            path = self.cache_dir / f"{tile_id}.tif"
            return [DemTile(id=tile_id, bbox=bbox, local_path=path, downloaded=path.exists())]
        # Check local index coverage first
        local_tiles = self._check_local_coverage(bbox)
        if local_tiles:
            return local_tiles

        poly = self._bbox_polygon_wkt(bbox)
        # Build OData filter
        # Check query cache first
        query_key = f"{bbox[0]:.4f}_{bbox[1]:.4f}_{bbox[2]:.4f}_{bbox[3]:.4f}"
        query_cache_path = self.cache_dir / "query_cache.json"
        query_cache = {}
        if query_cache_path.exists():
            try:
                query_cache = json.loads(query_cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        cached_ids = query_cache.get(query_key)
        if cached_ids:
            # Reconstruct tiles from cache
            tiles = []
            for pid in cached_ids:
                # Check for existing file with supported extensions
                found_path = None
                for ext in [".dt2", ".dt1", ".tif"]:
                    p = self.cache_dir / f"{pid}{ext}"
                    if p.exists():
                        found_path = p
                        break
                
                if found_path:
                    path = found_path
                else:
                    path = self.cache_dir / f"{pid}.dt2" # Default
                
                tiles.append(DemTile(id=pid, bbox=bbox, local_path=path, downloaded=path.exists()))
            return tiles

        poly_enc = quote(f"SRID=4326;{poly}")
        base_filter = f"Collection/Name eq 'COP-DEM' and OData.CSC.Intersects(area=geography'{poly_enc}')"
        dataset_identifier = None
        try:
            # Attempt to read dataset identifier from auth (not ideal) or environment via index path context; left flexible
            import os
            dataset_identifier = os.getenv("COPERNICUS_DATASET_IDENTIFIER")
        except Exception:
            dataset_identifier = None
        if dataset_identifier:
            # Attributes/OData.CSC.StringAttribute filter
            attr_filter = (
                "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'datasetIdentifier' "
                f"and att/OData.CSC.StringAttribute/Value eq '{dataset_identifier}')"
            )
            flt = f"{base_filter} and {attr_filter}"
        else:
            flt = base_filter
        url = f"{self._odata_products_url()}?$filter={flt}&$select=Id,Name,Footprint&$top={limit}"
        headers = {"Authorization": f"Bearer {token}"}
        tiles: List[DemTile] = []
        try:
            # Handle pagination to ensure we get ALL tiles covering the area
            items = []
            while url:
                resp = requests.get(url, headers=headers, timeout=60)
                if resp.status_code != 200:
                    self._log(f"OData query failed ({resp.status_code}); using synthetic tile.", is_error=True)
                    raise RuntimeError(resp.text)
                data = resp.json()
                current_items = data.get("value") or data.get("result") or []
                items.extend(current_items)
                
                # Check for next link
                next_link = data.get("@odata.nextLink")
                if next_link:
                    url = next_link
                    # Ensure base URL is correct if nextLink is relative (usually absolute)
                    if not url.startswith("http"):
                         url = f"{self.base_url}/{url}"
                else:
                    url = None

            if not items:
                self._log("No COP-DEM products returned; using synthetic fallback.", is_error=True)
                raise RuntimeError("empty")
            idx = self._load_index()
            found_ids = []
            for it in items:
                pid = it.get("Id") or it.get("id")
                if not pid:
                    continue
                found_ids.append(pid)
                # Check for existing file with supported extensions
                found_path = None
                for ext in [".dt2", ".dt1", ".tif"]:
                    p = self.cache_dir / f"{pid}{ext}"
                    if p.exists():
                        found_path = p
                        break
                
                if found_path:
                    path = found_path
                else:
                    path = self.cache_dir / f"{pid}.dt2" # Default
                
                tiles.append(DemTile(id=pid, bbox=bbox, local_path=path, downloaded=path.exists()))
                if pid not in idx:
                    idx[pid] = {"name": it.get("Name"), "footprint": it.get("Footprint")}
            self._save_index(idx)
            
            # Update query cache
            query_cache[query_key] = found_ids
            try:
                query_cache_path.write_text(json.dumps(query_cache, indent=2), encoding="utf-8")
            except Exception as e:
                self._log(f"Failed to save query cache: {e}", is_error=True)
                
        except Exception as e:
            self._log(f"DEM query exception: {e}; falling back to synthetic tile.", is_error=True)
            if not tiles:
                minx, miny, maxx, maxy = bbox
                tile_id = f"synthetic_{minx:.3f}_{miny:.3f}_{maxx:.3f}_{maxy:.3f}"
                path = self.cache_dir / f"{tile_id}.tif"
                tiles = [DemTile(id=tile_id, bbox=bbox, local_path=path, downloaded=path.exists())]
        return tiles

    def sample_elevation(self, lon: float, lat: float) -> float:
        """Sample elevation (m) at lon/lat from the first available DEM tile.

        This is a minimal implementation that:
        - Uses the first GeoTIFF or DTED in the cache directory.
        - Assumes DEM is in geographic CRS (lon/lat, WGS84-like).
        - Returns 0.0 if no tiles are available or sampling fails.
        """
        try:
            # Find any .tif, .dt2, .dt1 in cache_dir
            files = list(self.cache_dir.glob("*.dt2")) + list(self.cache_dir.glob("*.dt1")) + list(self.cache_dir.glob("*.tif"))
            for fpath in files:
                if not fpath.exists() or fpath.stat().st_size == 0:
                    continue
                try:
                    with rasterio.open(fpath) as ds:
                        # If dataset CRS is geographic, we can index by lon/lat directly
                        if ds.crs and ds.crs.is_geographic:
                            row, col = ds.index(lon, lat)
                        else:
                            # Fallback: assume geographic coordinates; this may be wrong but
                            # keeps the function robust until proper reprojection is wired in.
                            row, col = ds.index(lon, lat)
                        if 0 <= row < ds.height and 0 <= col < ds.width:
                            val = ds.read(1)[row, col]
                            if val is not None:
                                try:
                                    return float(val)
                                except Exception:
                                    continue
                except Exception as e:
                    self._log(f"Failed to sample from {fpath.name}: {e}", is_error=True)
                    continue
        except Exception as e:
            self._log(f"Elevation sampling error: {e}", is_error=True)
        return 0.0

    def download_tile(self, tile: DemTile) -> Path:
        """Download a DEM product by ID into the cache directory if not present.

        This uses the OData `$value` endpoint:
        `<base_url>/Products(<id>)/$value`
        and streams the result.
        Since COP-DEM downloads as a ZIP containing a DTED/DGED file, we extract it.
        """
        if tile.local_path.exists() and tile.local_path.stat().st_size > 0:
            tile.downloaded = True
            return tile.local_path

        token = self._access_token()
        if not token or not isinstance(token, str):
            self._log("No valid access token for tile download; leaving placeholder.", is_error=True)
            return tile.local_path

        # Note: No quotes around ID for this endpoint
        url = f"{self.base_url}/Products({tile.id})/$value"
        headers = {"Authorization": f"Bearer {token}"}
        
        t0 = time.time()
        try:
            self._log(f"Downloading DEM tile {tile.id} ...")
            
            # Manual redirect handling to preserve Authorization header
            # requests strips Auth header on cross-domain redirects by default
            r = requests.get(url, headers=headers, allow_redirects=False, timeout=30)
            if r.status_code in (301, 302, 303, 307, 308):
                redirect_url = r.headers.get("Location")
                if redirect_url:
                    self._log(f"Following redirect to {redirect_url} ...")
                    r = requests.get(redirect_url, headers=headers, stream=True, timeout=600)
            
            if r.status_code != 200:
                self._log(f"DEM tile download failed for {tile.id} with HTTP {r.status_code}", is_error=True)
                self._log(f"Response: {r.text[:200]}", is_error=True)
                return tile.local_path

            # Download to memory buffer (or temp file if large, but DEM tiles are ~25MB)
            # Using memory buffer for simplicity of extraction
            content = io.BytesIO()
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    content.write(chunk)
            
            # Check if it's a zip
            content.seek(0)
            is_zip = False
            try:
                with zipfile.ZipFile(content) as z:
                    is_zip = True
                    # Find the DEM file (.dt2, .dt1, or .tif)
                    # We must strictly avoid auxiliary files like _EDM.tif, _FLM.tif, _HEM.tif, _ACM.tif
                    # The DEM file usually has _DEM in the name.
                    
                    all_files = z.namelist()
                    
                    def is_dem_candidate(fname: str) -> bool:
                        f = fname.lower()
                        # Must be a supported extension
                        if not f.endswith(('.dt2', '.dt1', '.tif')):
                            return False
                        # Must NOT be an auxiliary mask
                        if any(x in f for x in ['_edm', '_flm', '_hem', '_acm', '_wBM']):
                            return False
                        # Should ideally be in a DEM/ folder or have DEM in name
                        return True

                    candidates = [n for n in all_files if is_dem_candidate(n)]
                    
                    if not candidates:
                        self._log(f"No valid DEM file found in zip for {tile.id}", is_error=True)
                        self._log(f"Zip contents: {all_files}", is_error=True)
                        return tile.local_path
                    
                    # Scoring function to pick the best candidate
                    def score_candidate(fname: str) -> int:
                        f = fname.lower()
                        score = 0
                        # Prefer files in a DEM/ folder
                        if 'dem/' in f:
                            score += 100
                        # Prefer files with _DEM in the name
                        if '_dem' in f:
                            score += 50
                        # Prefer .dt2 (30m) > .dt1 (90m) > .tif
                        if f.endswith('.dt2'):
                            score += 3
                        elif f.endswith('.dt1'):
                            score += 2
                        return score
                    
                    candidates.sort(key=score_candidate, reverse=True)
                    best_candidate = candidates[0]
                    
                    self._log(f"Extracting {best_candidate} from zip...")
                    
                    with z.open(best_candidate) as src, open(tile.local_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                        
            except zipfile.BadZipFile:
                # Not a zip, maybe it's the file itself?
                content.seek(0)
                with open(tile.local_path, 'wb') as f:
                    f.write(content.read())
            
            tile.downloaded = True
            return tile.local_path
            
        except Exception as e:
            self._log(f"Download exception: {e}", is_error=True)
            return tile.local_path
        finally:
            self.total_download_time += (time.time() - t0)

    def ensure_tiles(self, bbox: Tuple[float, float, float, float], progress: Optional[Progress] = None) -> List[Path]:
        # Increase limit to ensure we get all tiles for large viewsheds (e.g. 500m altitude -> 100km+ radius)
        tiles = self.query_tiles(bbox, limit=100)
        paths = []
        
        # Filter for tiles that actually need downloading
        to_download = [t for t in tiles if not (t.local_path.exists() and t.local_path.stat().st_size > 0)]
        already_downloaded = [t for t in tiles if (t.local_path.exists() and t.local_path.stat().st_size > 0)]
        
        # Add already downloaded paths
        for t in already_downloaded:
            t.downloaded = True
            paths.append(t.local_path)
            
        if not to_download:
            return paths

        # Print summary
        total_tiles = len(tiles)
        cached_count = len(already_downloaded)
        download_count = len(to_download)
        # Estimate size: ~25MB per tile for GLO-30
        est_size_mb = download_count * 25.0
        
        if self.verbose >= 1:
            print(f"\n[bold]DEM Tile Summary:[/bold]")
            print(f"  Total required: {total_tiles}")
            print(f"  Cached locally: {cached_count}")
            print(f"  To download:    {download_count}")
            print(f"  Est. download:  ~{est_size_mb:.1f} MB\n")

        # Download missing tiles
        if progress:
            task = progress.add_task(f"Downloading {len(to_download)} DEM tiles...", total=len(to_download))
            for t in to_download:
                self.download_tile(t)
                if t.downloaded:
                    paths.append(t.local_path)
                progress.advance(task)
            progress.remove_task(task)
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                transient=True
            ) as p:
                task = p.add_task(f"Downloading {len(to_download)} DEM tiles...", total=len(to_download))
                
                for t in to_download:
                    self.download_tile(t)
                    if t.downloaded:
                        paths.append(t.local_path)
                    p.advance(task)
                
        return paths

    def _check_local_coverage(self, bbox: Tuple[float, float, float, float]) -> Optional[List[DemTile]]:
        """Check if local index has tiles covering the bbox."""
        idx = self._load_index()
        if not idx:
            return None
            
        minx, miny, maxx, maxy = bbox
        target_poly = box(minx, miny, maxx, maxy)
        
        covering_tiles = []
        covering_polys = []
        
        for pid, meta in idx.items():
            footprint_raw = meta.get("footprint")
            if not footprint_raw:
                continue
            
            # Parse WKT: geography'SRID=4326;POLYGON ((...))'
            try:
                wkt_str = footprint_raw.split(";", 1)[1].rstrip("'")
                poly = wkt.loads(wkt_str)
                
                if poly.intersects(target_poly):
                    # Check if file exists
                    found_path = None
                    for ext in [".dt2", ".dt1", ".tif"]:
                        p = self.cache_dir / f"{pid}{ext}"
                        if p.exists():
                            found_path = p
                            break
                    
                    # We include it if it intersects, but we prefer if we have the file.
                    # If we don't have the file, we can still return it as a candidate,
                    # but we can't skip OData if we are missing files?
                    # Actually, if we have the metadata, we know the ID, so we can download it without OData query.
                    # So we just need to know if the *metadata* covers the area.
                    
                    path = found_path if found_path else (self.cache_dir / f"{pid}.dt2")
                    tile = DemTile(id=pid, bbox=bbox, local_path=path, downloaded=path.exists())
                    
                    covering_tiles.append(tile)
                    covering_polys.append(poly)
            except Exception:
                continue
                
        if not covering_polys:
            return None
            
        # Check coverage
        # Union of all intersecting tiles
        union_poly = unary_union(covering_polys)
        
        if union_poly.contains(target_poly):
            self._log("Local index covers request; skipping OData query.", level=2)
            return covering_tiles
            
        return None

def approximate_bounding_box(lon: float, lat: float, radius_m: float) -> Tuple[float, float, float, float]:
    """Approximate lon/lat bbox for a radius (m). Uses simple degree conversions."""
    # Degrees per meter approximations (improved later using pyproj)
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * max(0.1, math.cos(math.radians(lat))))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)

import math  # placed after function to avoid unused import ordering issues

__all__ = ["DemClient", "DemTile", "approximate_bounding_box"]