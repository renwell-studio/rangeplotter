from __future__ import annotations
import typer
import psutil
import signal
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
from rangeplotter.utils.shutdown import (
    is_shutdown_requested, 
    reset_shutdown_state, 
    request_shutdown,
    request_force_quit,
    cleanup_temp_cache_files
)
from rangeplotter.processing import clip_viewshed, union_viewsheds
from rangeplotter.io.export import export_viewshed_kml
from rangeplotter.io.csv_input import parse_csv_radars
from rangeplotter.utils.state import StateManager
from rangeplotter.cli import network
import time
import re
import yaml
import datetime

__version__ = "0.1.6"

def _signal_handler(signum, frame):
    """Handle Ctrl-C interrupt signal.
    
    First interrupt: Set graceful shutdown flag, allowing current operation to finish.
    Second interrupt: Force quit immediately with cleanup.
    """
    if is_shutdown_requested():
        request_force_quit()
        print("\n[red]Force quit. Cleaning up...[/red]")
        cleanup_temp_cache_files()
        raise SystemExit(1)
    else:
        request_shutdown()
        print("\n[yellow]Interrupt received. Finishing current operation... Press Ctrl-C again to force quit.[/yellow]")

app = typer.Typer(help="Radar LOS utility", context_settings={"help_option_names": ["-h", "--help"]})
app.add_typer(network.app, name="network")
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
    default_input_dir = Path("working_files/sensor_locations")
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
    """Resolve input path to a list of KML or CSV files."""
    if input_path is None:
        # Default to configured input directory
        input_dir = default_input_dir
        if not input_dir.exists():
            return []
        return list(input_dir.glob("*.kml")) + list(input_dir.glob("*.csv"))
    elif input_path.is_dir():
        return list(input_path.glob("*.kml")) + list(input_path.glob("*.csv"))
    elif input_path.exists():
        return [input_path]
    else:
        # Check fallback in default input directory
        fallback = default_input_dir / input_path.name
        if fallback.exists():
            return [fallback]
        return [input_path]

def _load_radars(input_files: List[Path], sensor_height: float) -> List:
    """Load radars from multiple KML or CSV files."""
    all_radars = []
    for file_path in input_files:
        if not file_path.exists():
            typer.echo(f"[yellow]Warning: Input file {file_path} not found.[/yellow]")
            continue
            
        if file_path.suffix.lower() == '.kml':
            radars = parse_radars(str(file_path), sensor_height)
            all_radars.extend(radars)
        elif file_path.suffix.lower() == '.csv':
            radars = parse_csv_radars(file_path, sensor_height)
            all_radars.extend(radars)
        else:
            typer.echo(f"[yellow]Warning: Unsupported file type {file_path.suffix} for {file_path.name}[/yellow]")
            
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
    filter_pattern: Optional[str] = typer.Option(None, "--filter", help="Regex pattern to filter sensors by name."),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Verbosity level: 0=Standard, 1=Info, 2=Debug")
):
    """
    Calculate the theoretical maximum geometric horizon (range rings) for each radar.
    
    This command computes the maximum possible detection range based on Earth curvature 
    and atmospheric refraction (k-factor), ignoring terrain obstructions.
    """
    # Register signal handler for graceful shutdown
    reset_shutdown_state()
    signal.signal(signal.SIGINT, _signal_handler)
    
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

    if filter_pattern:
        import re
        try:
            pattern = re.compile(filter_pattern)
            radars = [r for r in radars if pattern.search(r.name)]
            if not radars:
                typer.echo(f"[yellow]No sensors matched filter '{filter_pattern}'.[/yellow]")
                raise typer.Exit(code=0)
            typer.echo(f"Filtered to {len(radars)} sensors matching '{filter_pattern}'")
        except re.error as e:
            typer.echo(f"[red]Invalid regex pattern: {e}[/red]")
            raise typer.Exit(code=1)
    
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
            print(f"    [green]✓[/green] Ground elevation: {r.ground_elevation_m_msl:.1f} m MSL")
        
        # Log how radar height is being calculated based on altitude mode
        if verbose >= 2:
            h_agl = r.sensor_height_m_agl
            if isinstance(h_agl, list):
                h_agl_str = f"[{', '.join(f'{h:.1f}' for h in h_agl)}]"
            else:
                h_agl_str = f"{h_agl:.1f}"
            
            if r.altitude_mode == "relativeToGround":
                kml_agl = r.input_altitude or 0.0
                radar_h = r.radar_height_m_msl or 0.0
                log.debug(f"{r.name}: relativeToGround mode - KML altitude ({kml_agl:.1f}m AGL) + DEM ground ({r.ground_elevation_m_msl:.1f}m) + sensor height ({h_agl_str}m) = {radar_h:.1f}m MSL")
            elif r.altitude_mode == "clampToGround":
                radar_h = r.radar_height_m_msl or 0.0
                log.debug(f"{r.name}: clampToGround mode - DEM ground ({r.ground_elevation_m_msl:.1f}m) + sensor height ({h_agl_str}m) = {radar_h:.1f}m MSL")
            elif r.altitude_mode == "absolute":
                kml_abs = r.input_altitude or r.ground_elevation_m_msl
                radar_h = r.radar_height_m_msl or 0.0
                log.debug(f"{r.name}: absolute mode - KML altitude ({kml_abs:.1f}m MSL) + sensor height ({h_agl_str}m) = {radar_h:.1f}m MSL")

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
            meta[r.name] = {
                'lon': r.longitude,
                'lat': r.latitude,
                'ground_elev': r.ground_elevation_m_msl,
                'height_agl': r.sensor_height_m_agl
            }
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
    
    metadata = {
        "Utility": f"RangePlotter {__version__}",
        "Command": "horizon",
        "Date": datetime.datetime.now().isoformat(),
        "Earth Radius Model": "Effective Radius (4/3 Earth)" if abs(settings.atmospheric_k_factor - 1.333) < 0.001 else f"k={settings.atmospheric_k_factor}",
        "Refraction Factor (k)": settings.atmospheric_k_factor,
    }
    
    export_horizons_kml(str(kml_path), rings_all, meta, style=settings.style.model_dump(), kml_export_mode=settings.kml_export_altitude_mode, metadata=metadata)
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
    input_path: Optional[Path] = typer.Option(default_input_dir, "--input", "-i", help="Path to input directory or KML file. If file not found, checks working_files/sensor_locations/."),
    output_dir: Optional[Path] = typer.Option(default_viewshed_dir, "--output", "-o", help="Path to output directory"),
    altitudes_cli: Optional[List[str]] = typer.Option(None, "--altitudes", "-a", help="Target altitudes in meters (comma separated). Overrides config."),
    sensor_heights_cli: Optional[List[str]] = typer.Option(None, "--sensor-heights", "-sh", help="Sensor heights AGL in meters (comma separated). Overrides config."),
    reference_cli: Optional[str] = typer.Option(None, "--reference", "--ref", help="Target altitude reference: 'msl' or 'agl'. Overrides config."),
    download_only: bool = typer.Option(False, "--download-only", help="Download DEM tiles only, skip viewshed calculation."),
    check_download: bool = typer.Option(False, "--check-download", "--check", help="Check download requirements without downloading full dataset."),
    force: bool = typer.Option(False, "--force", help="Force recalculation even if output exists and matches state."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass the MVA viewshed cache. Forces recomputation of all zones."),
    filter_pattern: Optional[str] = typer.Option(None, "--filter", help="Regex pattern to filter sensors by name."),
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
    # Register signal handler for graceful shutdown
    reset_shutdown_state()
    signal.signal(signal.SIGINT, _signal_handler)
    
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
            
    # Override sensor heights if provided via CLI
    if sensor_heights_cli:
        parsed_heights = []
        for h_str in sensor_heights_cli:
            parts = h_str.split(',')
            for p in parts:
                try:
                    parsed_heights.append(float(p.strip()))
                except ValueError:
                    typer.echo(f"[yellow]Warning: Invalid sensor height value '{p}'. Skipping.[/yellow]")
        if parsed_heights:
            settings.sensor_height_m_agl = sorted(list(set(parsed_heights)))
            typer.echo(f"Using sensor heights from CLI: {settings.sensor_height_m_agl}")

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
    
    if filter_pattern:
        import re
        try:
            pattern = re.compile(filter_pattern)
            radars = [r for r in radars if pattern.search(r.name)]
            if not radars:
                typer.echo(f"[yellow]No sensors matched filter '{filter_pattern}'.[/yellow]")
                raise typer.Exit(code=0)
            typer.echo(f"Filtered to {len(radars)} sensors matching '{filter_pattern}'")
        except re.error as e:
            typer.echo(f"[red]Invalid regex pattern: {e}[/red]")
            raise typer.Exit(code=1)
    
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
                print(f"    [green]✓[/green] Ground elevation: {r.ground_elevation_m_msl:.1f} m MSL")
            
            # Log how radar height is being calculated based on altitude mode
            if verbose >= 2:
                h_agl = r.sensor_height_m_agl
                if isinstance(h_agl, list):
                    h_agl_str = f"[{', '.join(f'{h:.1f}' for h in h_agl)}]"
                else:
                    h_agl_str = f"{h_agl:.1f}"
                
                if r.altitude_mode == "relativeToGround":
                    kml_agl = r.input_altitude or 0.0
                    radar_h = r.radar_height_m_msl or 0.0
                    log.debug(f"{r.name}: relativeToGround mode - KML altitude ({kml_agl:.1f}m AGL) + DEM ground ({r.ground_elevation_m_msl:.1f}m) + sensor height ({h_agl_str}m) = {radar_h:.1f}m MSL")
                elif r.altitude_mode == "clampToGround":
                    radar_h = r.radar_height_m_msl or 0.0
                    log.debug(f"{r.name}: clampToGround mode - DEM ground ({r.ground_elevation_m_msl:.1f}m) + sensor height ({h_agl_str}m) = {radar_h:.1f}m MSL")
                elif r.altitude_mode == "absolute":
                    kml_abs = r.input_altitude or r.ground_elevation_m_msl
                    radar_h = r.radar_height_m_msl or 0.0
                    log.debug(f"{r.name}: absolute mode - KML altitude ({kml_abs:.1f}m MSL) + sensor height ({h_agl_str}m) = {radar_h:.1f}m MSL")

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

    # Initialize state manager
    state_manager = StateManager(out_dir_path)

    # Determine sensor heights to process
    # If sensor_height_m_agl is a list, we iterate over it.
    # However, if a sensor has a specific override in KML (relativeToGround), that specific value is used instead of the list.
    # This creates a complexity: do we run multiple heights for a sensor that has a fixed height in KML?
    # Decision: If a sensor has a fixed height (from KML), we run it once with that height.
    # If it uses the default (from config/CLI), we run it for each height in the list.
    
    default_sensor_heights = settings.effective_sensor_heights

    with progress.Progress(
        progress.SpinnerColumn(),
        progress.TextColumn("[progress.description]{task.description}"),
        progress.BarColumn(),
        progress.TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        progress.TimeRemainingColumn(),
        console=console
    ) as prog:
        # Estimate total steps (radars * heights * altitudes)
        # This is an estimate because some radars might only have 1 height
        tasks_to_run = []
        
        for sensor in radars:
            # Determine applicable heights for this sensor
            # If the sensor has an explicit altitude mode (absolute/relative) from KML,
            # we respect that and do not apply the default AGL sensor heights.
            if (sensor.altitude_mode in ['relativeToGround', 'absolute']) and sensor.input_altitude is not None:
                heights = [sensor.sensor_height_m_agl]
            else:
                # Use the list from settings
                heights = default_sensor_heights
            
            for h in heights:
                for alt in altitudes:
                    tasks_to_run.append((sensor, h, alt))
        
        total_steps = len(tasks_to_run) * 100
        overall_task = prog.add_task("Computing viewsheds...", total=total_steps)
        
        current_step = 0
        
        for sensor, sensor_h, alt in tasks_to_run:
            # Check for graceful shutdown request
            if is_shutdown_requested():
                prog.console.print("[yellow]Shutdown requested. Stopping after cleanup...[/yellow]")
                cleanup_temp_cache_files()
                print(f"\n[bold]Interrupted. Completed {current_step // 100} of {len(tasks_to_run)} viewsheds.[/bold]")
                raise typer.Exit(code=130)  # 130 = 128 + SIGINT(2)
            
            # Temporarily override sensor height for calculation
            # We need to be careful not to permanently modify the sensor object if we are iterating
            original_h = sensor.sensor_height_m_agl
            sensor.sensor_height_m_agl = sensor_h
            
            # Prepare filename to check state
            safe_name = sensor.name.replace(" ", "_").replace("/", "-")
            alt_str = f"{int(alt)}" if alt.is_integer() else f"{alt}"
            
            # Add sensor height to filename if we are running multiple heights
            # or if it differs from the default single height?
            # To keep it simple and consistent, maybe we should always include it if it's not the standard default?
            # Or just always include it?
            # Existing naming convention: 01_rangeplotter-Site-tgt_alt_100m_AGL.kml
            # If we have multiple sensor heights, we need to distinguish them.
            # Let's add _sh_Xm if there are multiple heights configured globally, or if it's a non-standard run.
            
            sh_suffix = ""
            if len(default_sensor_heights) > 1:
                sh_str = f"{int(sensor_h)}" if sensor_h.is_integer() else f"{sensor_h}"
                sh_suffix = f"_sh_{sh_str}m"
            
            altitude_mode = settings.target_altitude_reference
            ref_str = altitude_mode.upper()
            
            # Find index for altitude sorting prefix
            try:
                alt_idx = altitudes.index(alt) + 1
            except ValueError:
                alt_idx = 0
            prefix = f"{alt_idx:02d}_"
            
            filename = f"{prefix}rangeplotter-{safe_name}{sh_suffix}-tgt_alt_{alt_str}m_{ref_str}.kml"
            
            # Calculate horizon for hash
            radar_h = sensor.radar_height_m_msl or 0.0
            horizon_m = mutual_horizon_distance(radar_h, alt, sensor.latitude, settings.atmospheric_k_factor)

            # Determine styling early so it can be included in the hash
            final_style = settings.style.model_dump()
            if sensor.style_config:
                final_style.update(sensor.style_config)

            # Compute hash - include sensor height and styling!
            current_hash = state_manager.compute_hash(
                sensor, 
                alt, 
                settings.atmospheric_k_factor,
                earth_radius_model=settings.earth_model.type,
                max_range=horizon_m,
                sensor_height_m_agl=sensor_h,
                fill_color=final_style.get('fill_color'),
                line_color=final_style.get('line_color'),
                fill_opacity=final_style.get('fill_opacity')
            )
            # Note: compute_hash uses sensor.radar_height_m_msl, which uses sensor.sensor_height_m_agl
            # So modifying sensor.sensor_height_m_agl above correctly affects the hash.
            
            should_run = force
            if not should_run:
                should_run = state_manager.should_run(sensor.name, alt, current_hash, filename)
                
            if not should_run:
                if verbose >= 1:
                    prog.console.print(f"[dim][INFO] Skipping: {filename} (Already exists, hash match)[/dim]")
                prog.update(overall_task, completed=current_step + 100)
                current_step += 100
                # Restore original height
                sensor.sensor_height_m_agl = original_h
                continue
            
            # If we are running, check if it's a recalculation (file exists but hash mismatch)
            out_path_check = out_dir_path / filename
            if out_path_check.exists() and not force:
                 if verbose >= 1:
                    prog.console.print(f"[yellow][INFO] Recalculating: {filename} (Parameters changed)[/yellow]")
            elif out_path_check.exists() and force:
                 if verbose >= 1:
                    prog.console.print(f"[yellow][INFO] Recalculating: {filename} (Forced)[/yellow]")

            prog.update(overall_task, description=f"Computing viewshed for {sensor.name} (SH: {sensor_h}m) @ {alt}m")
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
                poly = compute_viewshed(
                    sensor, 
                    alt, 
                    dem_client, 
                    cfg_dict, 
                    progress_callback=_update_progress, 
                    rich_progress=prog,
                    altitude_mode=altitude_mode,
                    use_cache=not no_cache
                )
                
                out_path = out_dir_path / filename
                
                # final_style was already computed before hash calculation
                
                metadata = {
                    "Utility": f"RangePlotter {__version__}",
                    "Command": "viewshed",
                    "Date": datetime.datetime.now().isoformat(),
                    "Sensor Name": sensor.name,
                    "Sensor Location": f"{sensor.latitude:.5f}, {sensor.longitude:.5f}",
                    "Sensor Ground Elevation": f"{sensor.ground_elevation_m_msl:.1f} m MSL",
                    "Sensor Height (AGL)": f"{sensor.sensor_height_m_agl} m",
                    "Sensor Height (MSL)": f"{sensor.radar_height_m_msl:.1f} m" if sensor.radar_height_m_msl else "N/A",
                    "Target Altitude": f"{alt} m ({altitude_mode.upper()})",
                    "Max Range": f"{mutual_horizon_distance(sensor.radar_height_m_msl or 0, alt, sensor.latitude, settings.atmospheric_k_factor)/1000:.1f} km (Horizon)",
                    "Refraction Factor (k)": settings.atmospheric_k_factor,
                    "Earth Radius Model": settings.earth_model.ellipsoid,
                    "state_hash": current_hash
                }

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
                    kml_export_mode=settings.kml_export_altitude_mode,
                    metadata=metadata
                )
                
                if verbose >= 1:
                    prog.console.print(f"    [green]Saved {filename}[/green]")
                
                if verbose >= 2:
                    log_memory_usage(log, f"After {sensor.name} @ {alt}m")
                
                # Update state
                state_manager.update_state(sensor.name, alt, current_hash, filename)
                    
            except Exception as e:
                log.error(f"Failed to compute viewshed for {sensor.name} @ {alt}m: {e}", exc_info=True)
                prog.console.print(f"[red]    Failed to compute viewshed for {sensor.name} @ {alt}m: {e}[/red]")
            finally:
                prog.remove_task(calc_task)
                current_step += 100
                prog.update(overall_task, completed=current_step)
                # Restore original height
                sensor.sensor_height_m_agl = original_h
            
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
    union: Optional[bool] = typer.Option(None, "--union/--no-union", help="Union all viewsheds into a single coverage map (default: True)"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Verbosity level: 0=Standard, 1=Info, 2=Debug")
):
    """
    Clip viewsheds to detection ranges and union them if multiple sensors are provided.
    """
    # Register signal handler for graceful shutdown
    reset_shutdown_state()
    signal.signal(signal.SIGINT, _signal_handler)
    
    start_time = time.time()
    created_files = []

    if config:
        settings = Settings.from_file(config)
    else:
        settings = load_settings()

    # Resolve union setting
    do_union = union if union is not None else settings.union_outputs

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

        # Extract sensor height from filename (optional)
        sh_match = re.search(r"_sh_([\d.]+)m", kml_file.name)
        sensor_height = float(sh_match.group(1)) if sh_match else None
        
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
                    'sensor_height': sensor_height,
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

    # Group by (Altitude, Reference, Sensor Height)
    by_alt_ref = {}
    for item in parsed_data:
        key = (item['altitude'], item['reference'], item['sensor_height'])
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
        
        for i, (alt, ref, sh) in enumerate(sorted_keys, 1):
            items = by_alt_ref[(alt, ref, sh)]
            
            # Group by location to detect collisions (same site, multiple viewsheds)
            # This handles the case where we have multiple heights for the same site in the same group
            # (e.g. if SH extraction failed, or if user wants to process variants)
            items_by_loc = {}
            for item in items:
                # Use rounded coordinates to group same locations (approx 1m precision)
                # item['sensor'] is a tuple (lon, lat)
                sensor_loc = item['sensor']
                loc_key = (round(sensor_loc[0], 5), round(sensor_loc[1], 5))
                if loc_key not in items_by_loc:
                    items_by_loc[loc_key] = []
                items_by_loc[loc_key].append(item)
            
            # Determine max variants (e.g. if Site A has 2 files, Site B has 1, max=2)
            max_variants = 0
            for loc_items in items_by_loc.values():
                max_variants = max(max_variants, len(loc_items))
            
            if verbose >= 2 and max_variants > 1:
                log.debug(f"Detected {max_variants} variants/scenarios for group Alt:{alt}m")

            # Process each variant scenario
            for v_idx in range(max_variants):
                scenario_items = []
                for loc_items in items_by_loc.values():
                    # Pick the v-th item, or the last one if not enough
                    # This ensures that sites with fewer variants are still included in all scenarios
                    # (e.g. Site B is static while Site A changes)
                    idx = min(v_idx, len(loc_items) - 1)
                    scenario_items.append(loc_items[idx])

                ref_str = f" ({ref})" if ref else ""
                sh_str = f" [SH: {sh}m]" if sh is not None else ""
                
                # Add variant indicator to log/progress if needed
                var_str = f" (Var {v_idx+1}/{max_variants})" if max_variants > 1 else ""

                for rng in final_ranges:
                    if verbose >= 2:
                        log.debug(f"Processing Alt: {alt}m{ref_str}{sh_str}{var_str}, Range: {rng}km with {len(scenario_items)} inputs")
                    prog.update(task, description=f"Processing Alt: {alt}m{ref_str}{sh_str}{var_str}, Range: {rng}km")
                    
                    valid_results = []
                    for item in scenario_items:
                        if verbose >= 2:
                            log.debug(f"Clipping {item['name']} to {rng}km")
                        clipped = clip_viewshed(item['viewshed'], item['sensor'], rng)
                        if not clipped.is_empty:
                            valid_results.append({'poly': clipped, 'item': item})
                    
                    if not valid_results:
                        if verbose >= 2:
                            log.debug("No polygons remained after clipping.")
                        continue

                    export_tasks = []
                    if do_union:
                        if verbose >= 2:
                            log.debug(f"Unioning {len(valid_results)} polygons")
                        final_poly = union_viewsheds([r['poly'] for r in valid_results])
                        export_tasks.append({
                            'poly': final_poly,
                            'items': [r['item'] for r in valid_results],
                            'is_union': True
                        })
                    else:
                        if verbose >= 2:
                            log.debug(f"Processing {len(valid_results)} polygons individually (no union)")
                        for r in valid_results:
                            export_tasks.append({
                                'poly': r['poly'],
                                'items': [r['item']],
                                'is_union': False
                            })

                    for export_task in export_tasks:
                        task_poly = export_task['poly']
                        task_items = export_task['items']
                        is_union = export_task['is_union']

                        # Determine output name
                        if output_name:
                            base_name = output_name
                            if not is_union and len(export_tasks) > 1:
                                # Append sensor name if we are forcing a name but splitting outputs
                                base_name = f"{base_name}_{task_items[0]['name']}"
                        elif len(task_items) == 1:
                            # Try to extract sensor name from filename
                            # viewshed-(.*)-tgt_alt
                            m_name = re.search(r"viewshed-(.*)-tgt_alt", task_items[0]['file'].name)
                            if m_name:
                                base_name = m_name.group(1)
                            else:
                                base_name = task_items[0]['name']
                        else:
                            base_name = "Union"
                        
                        # Determine style
                        style_to_use = task_items[0]['style'].copy()
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
                        alt_str = f"{int(alt)}" if alt.is_integer() else f"{alt}"
                        rng_str = f"{int(rng)}" if rng.is_integer() else f"{rng}"
                        ref_suffix = f"_{ref}" if ref else ""
                        var_suffix = f"-var{v_idx+1}" if max_variants > 1 else ""
                        prefix = f"{i:02d}_"
                        filename = f"{prefix}rangeplotter-{base_name}-tgt_alt_{alt_str}m{ref_suffix}-det_rng_{rng_str}km{var_suffix}.kml"
                        kml_doc_name = filename.replace(".kml", "")
                        
                        sensors_list = []
                        for item in task_items:
                            sensors_list.append({
                                'name': item['name'],
                                'location': item['sensor'],
                                'style_config': item['style']
                            })

                        metadata = {
                            "Utility": f"RangePlotter {__version__}",
                            "Command": "detection-range",
                            "Date": datetime.datetime.now().isoformat(),
                            "Target Altitude": f"{alt} m ({ref if ref else 'msl'})",
                            "Detection Range": f"{rng} km",
                            "Mode": "Union" if is_union else "Single",
                            "Sensor Count": len(task_items),
                            "Sensors": ", ".join([item['name'] for item in task_items]),
                            "Variant": f"{v_idx+1}/{max_variants}" if max_variants > 1 else "1/1"
                        }
                        
                        # If single sensor, add detailed sensor info
                        if len(task_items) == 1:
                            item = task_items[0]
                            # item['sensor'] is (lon, lat)
                            # We don't have ground elevation or AGL height easily available here unless we parsed it or looked it up.
                            # parsed_data has 'sensor_height' if extracted from filename.
                            # But ground elevation is not in the KML usually.
                            # However, we can include what we have.
                            metadata.update({
                                "Sensor Name": item['name'],
                                "Sensor Location": f"{item['sensor'][1]:.5f}, {item['sensor'][0]:.5f}",
                            })
                            if item.get('sensor_height') is not None:
                                metadata["Sensor Height (AGL)"] = f"{item['sensor_height']} m"
                            # Ground elevation is tricky as we don't have the RadarSite object here, just parsed KML data.
                            # Unless we re-instantiate RadarSite or pass it through.
                            # But detection-range works on KML inputs which might not have that info.
                            # So we skip Ground Elevation for detection-range unless we want to fetch it (which is slow).
                            # The user requirement: "metadata should contain ... unless it is a union".
                            # If we can't get it, we can't put it.
                            pass

                        export_viewshed_kml(
                            viewshed_polygon=task_poly,
                            output_path=specific_out_dir / filename,
                            altitude=alt,
                            style_config=style_to_use,
                            sensors=sensors_list,
                            document_name=kml_doc_name,
                            altitude_mode=ref if ref else "msl",
                            kml_export_mode=settings.kml_export_altitude_mode,
                            metadata=metadata
                        )
                        
                        created_files.append({
                            "altitude": alt,
                            "range": rng,
                            "filename": filename,
                            "path": specific_out_dir / filename
                        })
            
            # Advance progress bar for the group
            prog.advance(task, advance=len(final_ranges))

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
