from __future__ import annotations
import typer
import psutil
from rich import print, progress
from rich.table import Table
from rich.console import Console
from pathlib import Path
from typing import Optional, List
from rangeplotter.config.settings import Settings, load_settings
from rangeplotter.io.kml import parse_radars, parse_viewshed_kml
from rangeplotter.los.rings import compute_horizons
from rangeplotter.io.dem import DemClient, approximate_bounding_box
from rangeplotter.auth.cdse import CdseAuth
from rangeplotter.utils.logging import setup_logging, log_memory_usage
from rangeplotter.processing import clip_viewshed, union_viewsheds
from rangeplotter.io.export import export_viewshed_kml
import time
import re
import yaml

__version__ = "0.1.4"

app = typer.Typer(help="Radar LOS utility scaffold", context_settings={"help_option_names": ["-h", "--help"]})
print("RangePlotter by Renwell | Licence: MIT | Support: ko-fi.com/renwell")

def version_callback(value: bool):
    if value:
        print(f"\n[bold cyan]RangePlotter v{__version__}[/bold cyan]")
        print("\n[bold]Advanced Sensor Line-of-Sight & Terrain Visibility Analysis[/bold]")
        print("\n[bold]Key Features:[/bold]")
        print(" • Terrain-aware viewshed analysis using Copernicus GLO-30 DEM")
        print(" • Earth curvature and atmospheric refraction modeling")
        print(" • Detection range clipping and network union")
        print("\n[bold]License:[/bold] MIT License")
        print("[bold]Author:[/bold] Renwell Studio")
        print("[bold]GitHub:[/bold] https://github.com/renwell-studio")
        print("[bold]Support:[/bold] https://ko-fi.com/renwell\n")
        raise typer.Exit()

@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True, help="Show version and info."
    )
):
    """
    RangePlotter: Advanced Sensor Line-of-Sight & Terrain Visibility Analysis
    """
    pass

# Load defaults from config if available
try:
    _settings = load_settings()
    default_input_dir = _settings.resolve_path(_settings.input_dir)
    default_viewshed_dir = _settings.resolve_path(_settings.output_viewshed_dir)
    default_horizon_dir = _settings.resolve_path(_settings.output_horizon_dir)
    default_detection_dir = _settings.resolve_path(_settings.output_detection_dir)
except Exception:
    # Fallback defaults if config is missing/broken (e.g. first run or bad path)
    default_input_dir = Path("working_files/input")
    default_viewshed_dir = Path("working_files/viewshed")
    default_horizon_dir = Path("working_files/horizon")
    default_detection_dir = Path("working_files/detection_range")

def format_duration(seconds: float) -> str:
    """Format seconds into human readable string (e.g. 1h 23m 45s)."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

def _resolve_inputs(input_path: Optional[Path]) -> List[Path]:
    """Resolve input path to a list of KML files."""
    if input_path is None:
        # Default to configured input directory
        input_dir = default_input_dir
        if not input_dir.exists():
            return []
        return list(input_dir.glob("*.kml"))
    elif input_path.is_dir():
        return list(input_path.glob("*.kml"))
    elif input_path.exists():
        return [input_path]
    else:
        # Check fallback in default input directory
        fallback = default_input_dir / input_path.name
        if fallback.exists():
            return [fallback]
        return [input_path]

def _load_radars(kml_files: List[Path], sensor_height: float) -> List:
    """Load radars from multiple KML files."""
    all_radars = []
    for kml_file in kml_files:
        if not kml_file.exists():
            typer.echo(f"[yellow]Warning: Input file {kml_file} not found.[/yellow]")
            continue
        radars = parse_radars(str(kml_file), sensor_height)
        all_radars.extend(radars)
    return all_radars

@app.command()
def extract_refresh_token(
    username: str = typer.Option(..., help="CDSE username"),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="CDSE password (not stored)"),
    client_id: str = typer.Option("cdse-public", help="OIDC public client id"),
    token_url: str = typer.Option("https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token", help="OIDC token endpoint"),
    env_output: Path = typer.Option(None, help="Optional path to write .env snippet with refresh token"),
    print_env: bool = typer.Option(False, help="Print .env lines to stdout"),
):
    """Perform password grant once and output only the refresh token (access token suppressed)."""
    from rangeplotter.auth.cdse import CdseAuth
    auth = CdseAuth(token_url=token_url, client_id=client_id, username=username, password=password)
    access = auth.ensure_access_token()
    if not access or not auth.refresh_token:
        typer.echo("[red]Failed to obtain refresh token. Check credentials.[/red]")
        raise typer.Exit(code=1)
    # Never print access token
    refresh = auth.refresh_token
    line = f"COPERNICUS_REFRESH_TOKEN={refresh}"
    if env_output:
        with open(env_output, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        typer.echo(f"Wrote refresh token to {env_output}")
    if print_env:
        typer.echo(line)
    typer.echo("Refresh token acquired. Remove password from environment now.")
@app.command()
def prepare_dem(
    config: Path = typer.Option(Path("config/config.yaml"), "--config", help="Path to config YAML"),
    input_path: Optional[Path] = typer.Option(default_input_dir, "--input", "-i", help="Path to radar KML file or directory"),
    limit: int = typer.Option(20, help="Max COP-DEM products per radar bbox")
):
    """Pre-fetch COP-DEM product metadata for each radar bounding box."""
    settings = Settings.from_file(config)
    setup_logging(settings.logging)
    
    kml_files = _resolve_inputs(input_path)
    if not kml_files:
        typer.echo("[red]No input KML files found.[/red]")
        raise typer.Exit(code=1)
        
    radars = _load_radars(kml_files, settings.sensor_height_m_agl)
    
    auth = CdseAuth(
        token_url=settings.copernicus_api.token_url,
        client_id=settings.copernicus_api.client_id or "cdse-public",
        username=settings.copernicus_api.username,
        password=settings.copernicus_api.password,
        refresh_token=settings.copernicus_api.refresh_token,
    )
    dem_cache = Path(settings.cache_dir) / "dem"
    dem_client = DemClient(base_url=settings.copernicus_api.base_url, auth=auth, cache_dir=dem_cache)
    from rangeplotter.geo.earth import mutual_horizon_distance
    max_alt = max(settings.effective_altitudes)
    for r in radars:
        horizon = mutual_horizon_distance(settings.sensor_height_m_agl, max_alt, r.latitude, settings.atmospheric_k_factor)
        # Add 5% buffer to match compute_viewshed logic and prevent re-downloading fringe tiles
        horizon *= 1.05
        bbox = approximate_bounding_box(r.longitude, r.latitude, horizon)
        tiles = dem_client.query_tiles(bbox, limit=limit)
        typer.echo(f"Radar {r.name}: {len(tiles)} DEM products referenced (bbox radius ~{horizon/1000:.1f} km)")
    typer.echo("DEM metadata preparation complete.")

@app.command()
def debug_auth_dem(
    config: Path = typer.Option(Path("config/config.yaml"), "--config", help="Path to config YAML"),
    input_path: Optional[Path] = typer.Option(default_input_dir, "--input", "-i", help="Path to radar KML file or directory")
):
    """Minimal auth+DEM test: get token and query a tiny bbox for first radar."""
    import faulthandler
    faulthandler.enable()
    settings = Settings.from_file(config)
    setup_logging(settings.logging)
    
    kml_files = _resolve_inputs(input_path)
    if not kml_files:
        typer.echo("[red]No input KML files found.[/red]")
        raise typer.Exit(code=1)
        
    radars = _load_radars(kml_files, settings.sensor_height_m_agl)
    if not radars:
        typer.echo("[red]No radars found in KML.[/red]")
        raise typer.Exit(code=1)
    r = radars[0]
    typer.echo(f"Testing auth+DEM for radar {r.name} at ({r.longitude}, {r.latitude})")
    auth = CdseAuth(
        token_url=settings.copernicus_api.token_url,
        client_id=settings.copernicus_api.client_id or "cdse-public",
        username=settings.copernicus_api.username,
        password=settings.copernicus_api.password,
        refresh_token=settings.copernicus_api.refresh_token,
    )
    token = auth.ensure_access_token()
    if not token:
        typer.echo("[red]Failed to obtain access token.[/red]")
        raise typer.Exit(code=1)
    typer.echo("Access token acquired (not shown). Querying DEM...")
    dem_cache = Path(settings.cache_dir) / "dem_debug"
    dem_client = DemClient(base_url=settings.copernicus_api.base_url, auth=auth, cache_dir=dem_cache)
    from rangeplotter.geo.earth import mutual_horizon_distance
    horizon = mutual_horizon_distance(5.0, max(settings.effective_altitudes), r.latitude, settings.atmospheric_k_factor)
    bbox = approximate_bounding_box(r.longitude, r.latitude, horizon * 0.1)  # smaller for test
    typer.echo(f"Requesting tiles for bbox={bbox}")
    tiles = dem_client.query_tiles(bbox, limit=3)
    typer.echo(f"Received {len(tiles)} tiles (synthetic or real).")

@app.command()
def horizon(
    config: Optional[Path] = typer.Option(None, "--config", help="Path to config YAML"),
    input_path: Optional[Path] = typer.Option(default_input_dir, "--input", "-i", help="Path to radar KML file or directory"),
    output_dir: Optional[Path] = typer.Option(default_horizon_dir, "--output", "-o", help="Override output directory"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Verbosity level: 0=Standard, 1=Info, 2=Debug")
):
    """
    Calculate the theoretical maximum geometric horizon (range rings) for each radar.
    
    This command computes the maximum possible detection range based on Earth curvature 
    and atmospheric refraction (k-factor), ignoring terrain obstructions.
    """
    start_time = time.time()
    import rangeplotter
    # print(f"DEBUG: rangeplotter imported from {rangeplotter.__file__}")
    if config:
        settings = Settings.from_file(config)
    else:
        settings = load_settings()
    # if output_dir:
    #     settings.output_dir = str(output_dir)
        
    from rich.console import Console
    console = Console()
    log = setup_logging(settings.logging, verbose=verbose, console=console)
    altitudes = settings.effective_altitudes
    
    kml_files = _resolve_inputs(input_path)
    if not kml_files:
        typer.echo("[red]No input KML files found.[/red]")
        raise typer.Exit(code=1)
        
    radars = _load_radars(kml_files, settings.sensor_height_m_agl)
    
    if verbose >= 2:
        print("[grey58]DEBUG: settings loaded, radars parsed.[/grey58]")
    if verbose >= 1:
        print(f"[bold cyan]Loaded {len(radars)} radar sites. Preparing DEM cache...[/bold cyan]")
    dem_cache = Path(settings.cache_dir) / "dem"
    auth = CdseAuth(
        token_url=settings.copernicus_api.token_url,
        client_id=settings.copernicus_api.client_id or "cdse-public",
        username=settings.copernicus_api.username,
        password=settings.copernicus_api.password,
        refresh_token=settings.copernicus_api.refresh_token,
        verbose=verbose
    )
    if verbose >= 2:
        print("[grey58]DEBUG: Auth object created.[/grey58]")

    # Friendly auth check
    if not auth.ensure_access_token():
        print("\n[bold red]Authentication Failed[/bold red]")
        print("Could not obtain an access token from Copernicus Data Space Ecosystem.")
        print("Please check your .env file or run 'rangeplotter extract-refresh-token'.")
        print("See README for details.\n")
        raise typer.Exit(code=1)

    dem_client = DemClient(
        base_url=settings.copernicus_api.base_url,
        auth=auth,
        cache_dir=dem_cache,
        verbose=verbose
    )
    if verbose >= 1:
        print("[bold blue]Initializing Radar Sites...[/bold blue]")
    
    # 1. Determine ground elevation for all radars (requires minimal DEM fetch)
    for r in radars:
        # We need the ground elevation to calculate the true radar height (MSL).
        # Fetch a small area around the radar (1km radius) to ensure we have the local tile.
        if verbose >= 1:
            print(f"  [cyan]•[/cyan] Sampling ground elevation for [bold]{r.name}[/bold]...")
        bbox_local = approximate_bounding_box(r.longitude, r.latitude, 1000)
        dem_client.ensure_tiles(bbox_local)
        
        r.ground_elevation_m_msl = dem_client.sample_elevation(r.longitude, r.latitude)
        if verbose >= 1:
            print(f"    [green]✓[/green] Elevation: {r.ground_elevation_m_msl:.1f} m MSL")

    # 2. Ensure full DEM coverage for the maximum possible range
    # Now that we have ground elevations, we can calculate the true horizon distance.
    if verbose >= 1:
        print("\n[bold blue]Verifying DEM Coverage...[/bold blue]")
    max_target_alt = max(altitudes)
    from rangeplotter.geo.earth import mutual_horizon_distance
    
    for r in radars:
        # Calculate max horizon based on radar height + max target altitude
        # radar_height_m_msl property now uses the sampled ground elevation
        radar_h = r.radar_height_m_msl or 0.0
        horizon_m = mutual_horizon_distance(radar_h, max_target_alt, r.latitude, settings.atmospheric_k_factor)
        
        # Add a 5% buffer to match viewshed logic
        search_radius = horizon_m * 1.05
        
        if verbose >= 1:
            print(f"  [cyan]•[/cyan] Checking coverage for [bold]{r.name}[/bold] (Radius: {search_radius/1000:.1f} km)...")
        bbox_full = approximate_bounding_box(r.longitude, r.latitude, search_radius)
        
        # This will download any missing tiles for the full range
        dem_client.ensure_tiles(bbox_full)
        
    if verbose >= 2:
        print("[grey58]DEBUG: Starting horizon computation loop.")
    with progress.Progress(progress.SpinnerColumn(), progress.TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("Computing geodesic horizons", total=len(radars))
        rings_all = {}
        meta = {}
        for r in radars:
            if verbose >= 2:
                print(f"[grey58]DEBUG: Computing horizons for {r.name}.")
            rings = compute_horizons([r], altitudes, settings.atmospheric_k_factor)
            rings_all.update(rings)
            meta[r.name] = (r.longitude, r.latitude)
            prog.advance(task)
    if verbose >= 2:
        print("[grey58]DEBUG: Horizon computation finished. Beginning export.")
    
    if output_dir:
        out_path = output_dir
    else:
        out_path = default_horizon_dir

    out_path.mkdir(parents=True, exist_ok=True)
    from rangeplotter.io.export import export_horizons_kml  # lazy import to avoid loading pyproj for other commands
    kml_path = out_path / "horizons.kml"
    export_horizons_kml(str(kml_path), rings_all, meta, style=settings.style.model_dump(), kml_export_mode=settings.kml_export_altitude_mode)
    if verbose >= 2:
        print("[grey58]DEBUG: Export complete.")
    print(f"[green]Exported horizons to {kml_path}[/green]")
    
    end_time = time.time()
    total_time = end_time - start_time
    print(f"[bold]Total execution time: {total_time:.1f}s ({format_duration(total_time)})[/bold]")
    print(f"  - DEM Download time: {dem_client.total_download_time:.1f}s")
    print(f"  - Processing time: {total_time - dem_client.total_download_time:.1f}s")

@app.command()
def viewshed(
    config: Optional[Path] = typer.Option(None, "--config", help="Path to config YAML"),
    input_path: Optional[Path] = typer.Option(default_input_dir, "--input", "-i", help="Path to input directory or KML file. If file not found, checks working_files/input/."),
    output_dir: Optional[Path] = typer.Option(default_viewshed_dir, "--output", "-o", help="Path to output directory"),
    altitudes_cli: Optional[List[str]] = typer.Option(None, "--altitudes", "-a", help="Target altitudes in meters (comma separated). Overrides config."),
    reference_cli: Optional[str] = typer.Option(None, "--reference", "--ref", help="Target altitude reference: 'msl' or 'agl'. Overrides config."),
    download_only: bool = typer.Option(False, "--download-only", help="Download DEM tiles only, skip viewshed calculation."),
    check_download: bool = typer.Option(False, "--check-download", "--check", help="Check download requirements without downloading full dataset."),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Verbosity level: 0=Standard, 1=Info, 2=Debug")
):
    """
    Calculate the actual terrain-aware visibility (viewshed) for each sensor.
    
    This command downloads Copernicus GLO-30 DEM data and performs a radial sweep 
    Line-of-Sight (LOS) calculation, accounting for Earth curvature, refraction, 
    and terrain obstructions.

    It produces a raw, geometric viewshed representing the area visible from a static
    sensor location to a target at a specified altitude (or set of altitudes).

    Outputs are saved as individual KML files per site and target altitude.
    """
    start_time = time.time()
    if config:
        settings = Settings.from_file(config)
    else:
        settings = load_settings()
    
    # Override altitudes if provided via CLI
    if altitudes_cli:
        parsed_alts = []
        for a_str in altitudes_cli:
            parts = a_str.split(',')
            for p in parts:
                try:
                    parsed_alts.append(float(p.strip()))
                except ValueError:
                    typer.echo(f"[yellow]Warning: Invalid altitude value '{p}'. Skipping.[/yellow]")
        if parsed_alts:
            settings.altitudes_msl_m = parsed_alts
            typer.echo(f"Using target altitudes from CLI: {settings.altitudes_msl_m}")
            
    # Override reference if provided via CLI
    if reference_cli:
        if reference_cli.lower() in ["msl", "agl"]:
            settings.target_altitude_reference = reference_cli.lower()
            typer.echo(f"Using target altitude reference from CLI: {settings.target_altitude_reference.upper()}")
        else:
            typer.echo(f"[yellow]Warning: Invalid reference '{reference_cli}'. Using config value.[/yellow]")
        
    from rich.console import Console
    console = Console()
    log = setup_logging(settings.logging, verbose=verbose, console=console)
    altitudes = sorted(settings.effective_altitudes)
    
    kml_files = _resolve_inputs(input_path)
    if not kml_files:
        typer.echo("[red]No input KML files found.[/red]")
        raise typer.Exit(code=1)
        
    radars = _load_radars(kml_files, settings.sensor_height_m_agl)
    
    auth = CdseAuth(
        token_url=settings.copernicus_api.token_url,
        client_id=settings.copernicus_api.client_id or "cdse-public",
        username=settings.copernicus_api.username,
        password=settings.copernicus_api.password,
        refresh_token=settings.copernicus_api.refresh_token,
        verbose=verbose
    )

    # Friendly auth check
    if not auth.ensure_access_token():
        print("\n[bold red]Authentication Failed[/bold red]")
        print("Could not obtain an access token from Copernicus Data Space Ecosystem.")
        print("Please check your .env file or run 'rangeplotter extract-refresh-token'.")
        print("See README for details.\n")
        raise typer.Exit(code=1)

    dem_cache = Path(settings.cache_dir) / "dem"
    dem_client = DemClient(
        base_url=settings.copernicus_api.base_url,
        auth=auth,
        cache_dir=dem_cache,
        verbose=verbose
    )
    
    if verbose >= 1:
        print("[bold blue]Initializing Radar Sites...[/bold blue]")
    
    # 1. Determine ground elevation for all radars (requires minimal DEM fetch)
    all_tiles_map = {}  # Track unique tiles for check mode
    missing_local_tiles = []

    for r in radars:
        # We need the ground elevation to calculate the true radar height (MSL).
        # Fetch a small area around the radar (1km radius) to ensure we have the local tile.
        if verbose >= 1:
            print(f"  [cyan]•[/cyan] Sampling ground elevation for [bold]{r.name}[/bold]...")
        bbox_local = approximate_bounding_box(r.longitude, r.latitude, 1000)
        
        if check_download:
            # In check mode, we query but do not download
            local_tiles = dem_client.query_tiles(bbox_local)
            for t in local_tiles:
                all_tiles_map[t.id] = t
            
            # If we happen to have the tiles, we can sample elevation to get a better horizon estimate
            missing_here = [t for t in local_tiles if not (t.local_path.exists() and t.local_path.stat().st_size > 0)]
            
            if not missing_here and local_tiles:
                r.ground_elevation_m_msl = dem_client.sample_elevation(r.longitude, r.latitude)
                if verbose >= 1:
                    print(f"    [green]✓[/green] Elevation: {r.ground_elevation_m_msl:.1f} m MSL (Cached)")
            else:
                # Fallback if missing
                missing_local_tiles.extend(missing_here)
                r.ground_elevation_m_msl = 0.0
                if verbose >= 1:
                    print(f"    [yellow]![/yellow] Local tile missing. Assuming 0m MSL for horizon check.")
        else:
            # Normal mode: ensure tiles are present
            dem_client.ensure_tiles(bbox_local)
            r.ground_elevation_m_msl = dem_client.sample_elevation(r.longitude, r.latitude)
            if verbose >= 1:
                print(f"    [green]✓[/green] Elevation: {r.ground_elevation_m_msl:.1f} m MSL")

    # Interactive check for missing local tiles
    local_tiles_fixed = False
    if check_download and missing_local_tiles:
        print(f"\n[yellow]Warning: {len(missing_local_tiles)} local DEM tiles are missing.[/yellow]")
        print("Ground elevation cannot be determined, so horizon calculations will be inaccurate (using 0m MSL).")
        
        if typer.confirm("Would you like to download these local tiles now to improve accuracy?"):
            print("[bold blue]Downloading local tiles...[/bold blue]")
            # Deduplicate based on ID
            unique_missing = {t.id: t for t in missing_local_tiles}.values()
            
            for t in unique_missing:
                try:
                    dem_client.download_tile(t)
                except Exception as e:
                    print(f"[red]Failed to download {t.id}: {e}[/red]")
            
            # Re-sample elevations
            print("[bold blue]Re-sampling ground elevations...[/bold blue]")
            for r in radars:
                r.ground_elevation_m_msl = dem_client.sample_elevation(r.longitude, r.latitude)
                if verbose >= 1:
                     print(f"  [cyan]•[/cyan] {r.name}: {r.ground_elevation_m_msl:.1f} m MSL")
            local_tiles_fixed = True

    # 2. Ensure full DEM coverage for the maximum possible range
    # Now that we have ground elevations, we can calculate the true horizon distance.
    if verbose >= 1:
        print("\n[bold blue]Verifying DEM Coverage...[/bold blue]")
    max_target_alt = max(settings.effective_altitudes)
    from rangeplotter.geo.earth import mutual_horizon_distance
    
    if check_download:
        print("[bold]Checking download requirements...[/bold]")
        # all_tiles_map already contains local tiles
        for r in radars:
            radar_h = r.radar_height_m_msl or 0.0
            horizon_m = mutual_horizon_distance(radar_h, max_target_alt, r.latitude, settings.atmospheric_k_factor)
            search_radius = horizon_m * 1.05
            bbox_full = approximate_bounding_box(r.longitude, r.latitude, search_radius)
            
            # Use query_tiles directly to get objects, but don't download
            # We use limit=100 as in ensure_tiles
            tiles = dem_client.query_tiles(bbox_full, limit=100)
            for t in tiles:
                all_tiles_map[t.id] = t
        
        unique_tiles = list(all_tiles_map.values())
        to_download = [t for t in unique_tiles if not (t.local_path.exists() and t.local_path.stat().st_size > 0)]
        cached = [t for t in unique_tiles if (t.local_path.exists() and t.local_path.stat().st_size > 0)]
        
        est_size_mb = len(to_download) * 25.0
        
        print(f"\n[bold]Download Check Summary (All Sites):[/bold]")
        print(f"  Total tiles required: {len(unique_tiles)}")
        print(f"  Cached locally:       {len(cached)}")
        print(f"  To download:          {len(to_download)}")
        print(f"  Est. download size:   ~{est_size_mb:.1f} MB")
        
        if missing_local_tiles and not local_tiles_fixed:
             print(f"[yellow]Note: Some local tiles are missing. Horizon calculation used 0m MSL fallback where necessary.[/yellow]")

        raise typer.Exit()

    for r in radars:
        # Calculate max horizon based on radar height + max target altitude
        # radar_height_m_msl property now uses the sampled ground elevation
        radar_h = r.radar_height_m_msl or 0.0
        horizon_m = mutual_horizon_distance(radar_h, max_target_alt, r.latitude, settings.atmospheric_k_factor)
        
        # Add a 5% buffer to match viewshed logic
        search_radius = horizon_m * 1.05
        
        if verbose >= 1:
            print(f"  [cyan]•[/cyan] Checking coverage for [bold]{r.name}[/bold] (Radius: {search_radius/1000:.1f} km)...")
        bbox_full = approximate_bounding_box(r.longitude, r.latitude, search_radius)
        
        # This will download any missing tiles for the full range
        dem_client.ensure_tiles(bbox_full)

    if download_only:
        print("[green]Download complete. Skipping viewshed calculation.[/green]")
        raise typer.Exit()

    from rangeplotter.los.viewshed import compute_viewshed
    from rangeplotter.io.export import export_viewshed_kml
    
    if output_dir:
        # User specified output directory, use it directly
        out_dir_path = Path(output_dir)
    else:
        # Default behavior: use config output_dir + /viewshed
        out_dir_path = Path(settings.output_viewshed_dir)
        
    out_dir_path.mkdir(parents=True, exist_ok=True)
    
    # Map populated radars by location for easy lookup
    radar_map = {(r.longitude, r.latitude): r for r in radars}

    # Check system memory before starting
    mem = psutil.virtual_memory()
    max_ram_percent = settings.resources.max_ram_percent
    if mem.percent > max_ram_percent:
        print(f"[yellow]WARNING: System memory is already at {mem.percent}%. This may cause instability.[/yellow]")

    with progress.Progress(
        progress.SpinnerColumn(),
        progress.TextColumn("[progress.description]{task.description}"),
        progress.BarColumn(),
        progress.TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        progress.TimeRemainingColumn(),
        console=console
    ) as prog:
        # Estimate total steps (files * radars * altitudes)
        total_steps = len(radars) * len(altitudes) * 100
        overall_task = prog.add_task("Computing viewsheds...", total=total_steps)
        
        current_step = 0
        
        for kml_file in kml_files:
            file_radars_raw = parse_radars(str(kml_file), settings.sensor_height_m_agl)
            
            for r_raw in file_radars_raw:
                # Find the populated radar object (with elevation data)
                sensor = radar_map.get((r_raw.longitude, r_raw.latitude))
                if not sensor:
                    prog.console.print(f"[red]Could not find sensor for {r_raw.name} at {r_raw.longitude}, {r_raw.latitude}[/red]")
                    # Debug keys
                    # print(f"Keys: {list(radar_map.keys())}")
                    continue
                
                for i, alt in enumerate(altitudes, 1):
                    prog.update(overall_task, description=f"Computing viewshed for {sensor.name} @ {alt}m")
                    calc_task = prog.add_task(f"  {sensor.name} @ {alt}m", total=100)
                    
                    def _update_progress(step: str, pct: float):
                        pct = max(0.0, min(100.0, pct))
                        prog.update(calc_task, description=f"  {step}...", completed=pct)
                        
                        task_progress = 0.0
                        if step == "Initializing": task_progress = 5.0
                        elif step == "Computing LOS": task_progress = 10.0 + (pct * 0.6)
                        elif step == "Generating Mask": task_progress = 70.0 + (pct * 0.2)
                        elif step == "Vectorizing": task_progress = 90.0
                        elif step == "Transforming to WGS84": task_progress = 95.0
                        
                        prog.update(overall_task, completed=current_step + task_progress)

                    try:
                        if verbose >= 2:
                            log_memory_usage(log, f"Before {sensor.name} @ {alt}m")
                        
                        cfg_dict = settings.model_dump()
                        altitude_mode = settings.target_altitude_reference
                        poly = compute_viewshed(
                            sensor, 
                            alt, 
                            dem_client, 
                            cfg_dict, 
                            progress_callback=_update_progress, 
                            rich_progress=prog,
                            altitude_mode=altitude_mode
                        )
                        
                        # Export individual KML
                        safe_name = sensor.name.replace(" ", "_").replace("/", "-")
                        alt_str = f"{int(alt)}" if alt.is_integer() else f"{alt}"
                        
                        # Include reference in filename
                        ref_str = altitude_mode.upper()
                        prefix = f"{i:02d}_"
                        filename = f"{prefix}rangeplotter-{safe_name}-tgt_alt_{alt_str}m_{ref_str}.kml"
                        out_path = out_dir_path / filename
                        
                        # Merge sensor style with default style
                        final_style = settings.style.model_dump()
                        if sensor.style_config:
                            final_style.update(sensor.style_config)
                        
                        export_viewshed_kml(
                            viewshed_polygon=poly,
                            output_path=out_path,
                            altitude=alt,
                            style_config=final_style,
                            sensors=[{
                                'name': sensor.name,
                                'location': (sensor.longitude, sensor.latitude),
                                'style_config': final_style
                            }],
                            document_name=f"viewshed-{safe_name}-tgt_alt_{alt_str}m_{ref_str}",
                            altitude_mode=altitude_mode,
                            kml_export_mode=settings.kml_export_altitude_mode
                        )
                        
                        if verbose >= 1:
                            prog.console.print(f"    [green]Saved {filename}[/green]")
                        
                        if verbose >= 2:
                            log_memory_usage(log, f"After {sensor.name} @ {alt}m")
                            
                    except Exception as e:
                        log.error(f"Failed to compute viewshed for {sensor.name} @ {alt}m: {e}", exc_info=True)
                        prog.console.print(f"[red]    Failed to compute viewshed for {sensor.name} @ {alt}m: {e}[/red]")
                    finally:
                        prog.remove_task(calc_task)
                        current_step += 100
                        prog.update(overall_task, completed=current_step)
            
    print("[green]Viewshed computation complete.[/green]")
    
    end_time = time.time()
    total_time = end_time - start_time
    print(f"[bold]Total execution time: {total_time:.1f}s ({format_duration(total_time)})[/bold]")
    print(f"  - DEM Download time: {dem_client.total_download_time:.1f}s")
    print(f"  - Processing time: {total_time - dem_client.total_download_time:.1f}s")

@app.command()
def detection_range(
    config: Optional[Path] = typer.Option(None, "--config", help="Path to config YAML"),
    input_files: Optional[List[str]] = typer.Option(None, "--input", "-i", help="Input viewshed KML files (supports wildcards). If not found, checks working_files/viewshed/."),
    extra_files: Optional[List[str]] = typer.Argument(None, help="Additional input files (supports wildcards). If not found, checks working_files/viewshed/."),
    ranges: Optional[List[str]] = typer.Option(None, "--range", "-r", help="Detection ranges in km (can be comma separated). Overrides config when specified."),
    output_name: str = typer.Option(None, "--name", "-n", help="Output group name (default: sensor name or 'Union')"),
    output_dir: Path = typer.Option(default_detection_dir, "--output", "-o", help="Output directory"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Verbosity level: 0=Standard, 1=Info, 2=Debug")
):
    """
    Clip viewsheds to detection ranges and union them if multiple sensors are provided.
    """
    start_time = time.time()
    created_files = []

    if config:
        settings = Settings.from_file(config)
    else:
        settings = load_settings()

    from rich.console import Console
    console = Console()
    log = setup_logging(settings.logging, verbose=verbose, console=console)

    # Combine inputs
    all_inputs = []
    if input_files:
        all_inputs.extend(input_files)
    if extra_files:
        all_inputs.extend(extra_files)

    if not all_inputs:
        typer.echo("[red]No input files provided. Use --input or positional arguments.[/red]")
        raise typer.Exit(code=1)

    # Resolve inputs (handle wildcards manually if shell didn't)
    resolved_files = []
    import glob
    for inp in all_inputs:
        # Check if it's a glob pattern
        if "*" in inp or "?" in inp or "[" in inp:
            matches = glob.glob(inp)
            if not matches:
                # Try fallback dir
                fallback_pattern = str(default_viewshed_dir / inp)
                matches = glob.glob(fallback_pattern)
                
            if not matches:
                typer.echo(f"[yellow]Warning: No files matched pattern {inp} (checked CWD and {default_viewshed_dir})[/yellow]")
            for m in matches:
                p = Path(m)
                if p.is_file():
                    resolved_files.append(p)
        else:
            p = Path(inp)
            if p.exists() and p.is_file():
                resolved_files.append(p)
            else:
                # Check fallback
                fallback = default_viewshed_dir / p.name
                if fallback.exists() and fallback.is_file():
                    resolved_files.append(fallback)
                elif p.is_dir():
                     typer.echo(f"[yellow]Warning: {inp} is a directory. Skipping.[/yellow]")
                else:
                    typer.echo(f"[yellow]Warning: File {inp} not found (checked CWD and {default_viewshed_dir}).[/yellow]")
    
    if not resolved_files:
        typer.echo("[red]No valid input files provided.[/red]")
        raise typer.Exit(code=1)

    # Resolve ranges
    final_ranges = []
    if ranges:
        for r_str in ranges:
            # Split by comma
            parts = r_str.split(',')
            for p in parts:
                try:
                    final_ranges.append(float(p.strip()))
                except ValueError:
                    typer.echo(f"[yellow]Warning: Invalid range value '{p}'. Skipping.[/yellow]")
    
    # Fallback to config
    if not final_ranges:
        if settings.detection_ranges:
            final_ranges = settings.detection_ranges
            typer.echo(f"Using default detection ranges from config: {final_ranges}")
        else:
            typer.echo("[red]No detection ranges provided via CLI or config.[/red]")
            raise typer.Exit(code=1)
    
    final_ranges.sort()

    # Parse inputs
    if verbose >= 1:
        console.print(f"[bold blue]Parsing {len(resolved_files)} input files...[/bold blue]")
    parsed_data = []
    for kml_file in resolved_files:
        if verbose >= 2:
            log.debug(f"Parsing file: {kml_file}")

        # Extract altitude from filename
        match = re.search(r"tgt_alt_([\d.]+)m(?:_([A-Za-z]+))?", kml_file.name)
        if not match:
            msg = f"Warning: Could not extract altitude from filename {kml_file.name}. Skipping."
            if verbose >= 1:
                log.warning(msg)
            else:
                typer.echo(f"[yellow]{msg}[/yellow]")
            continue
        altitude = float(match.group(1))
        reference = match.group(2)
        
        # Parse KML
        try:
            results = parse_viewshed_kml(str(kml_file))
            if verbose >= 2:
                log.debug(f"  Found {len(results)} viewshed(s) in {kml_file.name}")
            
            for res in results:
                parsed_data.append({
                    'file': kml_file,
                    'altitude': altitude,
                    'reference': reference,
                    'sensor': res['sensor'],
                    'viewshed': res['viewshed'],
                    'style': res.get('style', {}),
                    'name': res.get('sensor_name') or res.get('folder_name') or kml_file.stem
                })
        except Exception as e:
            log.error(f"Failed to parse {kml_file}: {e}")
            if verbose >= 1:
                console.print(f"[red]Failed to parse {kml_file}: {e}[/red]")

    if not parsed_data:
        typer.echo("[red]No valid data found in input files.[/red]")
        raise typer.Exit(code=1)

    # Group by (Altitude, Reference)
    by_alt_ref = {}
    for item in parsed_data:
        key = (item['altitude'], item['reference'])
        if key not in by_alt_ref:
            by_alt_ref[key] = []
        by_alt_ref[key].append(item)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Process
    with progress.Progress(
        progress.SpinnerColumn(),
        progress.TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console
    ) as prog:
        # Total tasks = groups * ranges
        total_steps = len(by_alt_ref) * len(final_ranges)
        task = prog.add_task("Processing detection ranges...", total=total_steps)
        
        # Sort by altitude
        sorted_keys = sorted(by_alt_ref.keys(), key=lambda x: x[0])
        
        for i, (alt, ref) in enumerate(sorted_keys, 1):
            items = by_alt_ref[(alt, ref)]
            ref_str = f" ({ref})" if ref else ""
            for rng in final_ranges:
                if verbose >= 2:
                    log.debug(f"Processing Alt: {alt}m{ref_str}, Range: {rng}km with {len(items)} inputs")
                prog.update(task, description=f"Processing Alt: {alt}m{ref_str}, Range: {rng}km")
                
                clipped_polys = []
                
                # Collect styles to merge or pick one
                # For union, we might just pick the first one or a default union style
                # For single, we use the item's style
                
                for item in items:
                    if verbose >= 2:
                        log.debug(f"Clipping {item['name']} to {rng}km")
                    clipped = clip_viewshed(item['viewshed'], item['sensor'], rng)
                    if not clipped.is_empty:
                        clipped_polys.append(clipped)
                
                if not clipped_polys:
                    if verbose >= 2:
                        log.debug("No polygons remained after clipping.")
                    prog.advance(task)
                    continue
                
                if verbose >= 2:
                    log.debug(f"Unioning {len(clipped_polys)} polygons")
                final_poly = union_viewsheds(clipped_polys)
                
                # Determine output name
                if output_name:
                    base_name = output_name
                elif len(items) == 1:
                    # Try to extract sensor name from filename
                    # viewshed-(.*)-tgt_alt
                    m_name = re.search(r"viewshed-(.*)-tgt_alt", items[0]['file'].name)
                    if m_name:
                        base_name = m_name.group(1)
                    else:
                        base_name = items[0]['name']
                else:
                    base_name = "Union"
                
                # Determine style
                # If single item, use its style. If union, use first item's style or default?
                # Let's use first item's style as base, but maybe ensure opacity is reasonable
                style_to_use = items[0]['style'].copy()
                if not style_to_use:
                     style_to_use = {
                        "line_color": "#00FF00",
                        "line_width": 2,
                        "fill_color": "#00FF00",
                        "fill_opacity": 0.3
                    }
                
                # Create specific output directory
                specific_out_dir = output_dir / base_name
                specific_out_dir.mkdir(parents=True, exist_ok=True)
                
                # Construct filename
                # rangeplotter-[name]-tgt_alt_[alt]m[_ref]-det_rng_[rng]km.kml
                alt_str = f"{int(alt)}" if alt.is_integer() else f"{alt}"
                rng_str = f"{int(rng)}" if rng.is_integer() else f"{rng}"
                ref_suffix = f"_{ref}" if ref else ""
                prefix = f"{i:02d}_"
                filename = f"{prefix}rangeplotter-{base_name}-tgt_alt_{alt_str}m{ref_suffix}-det_rng_{rng_str}km.kml"
                kml_doc_name = filename.replace(".kml", "")
                
                sensors_list = []
                for item in items:
                    sensors_list.append({
                        'name': item['name'],
                        'location': item['sensor'],
                        'style_config': item['style']
                    })

                export_viewshed_kml(
                    viewshed_polygon=final_poly,
                    output_path=specific_out_dir / filename,
                    altitude=alt,
                    style_config=style_to_use,
                    sensors=sensors_list,
                    document_name=kml_doc_name,
                    altitude_mode=ref if ref else "msl",
                    kml_export_mode=settings.kml_export_altitude_mode
                )
                
                created_files.append({
                    "altitude": alt,
                    "range": rng,
                    "filename": filename,
                    "path": specific_out_dir / filename
                })
                
                prog.advance(task)

    end_time = time.time()
    duration = end_time - start_time
    
    console = Console()
    
    if created_files:
        table = Table(title="Detection Range Processing Summary")
        table.add_column("Altitude (m)", justify="right")
        table.add_column("Range (km)", justify="right")
        table.add_column("Output File", style="cyan")
        
        for f in created_files:
            table.add_row(str(f["altitude"]), str(f["range"]), f["filename"])
            
        console.print(table)
        
    console.print(f"\n[bold]Total Execution Time:[/bold] {duration:.2f}s ({format_duration(duration)})")
    console.print(f"[bold]Files Created:[/bold] {len(created_files)}")
    console.print(f"[bold]Output Directory:[/bold] {output_dir}")

if __name__ == "__main__":
    app()
