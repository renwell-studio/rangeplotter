from __future__ import annotations
import typer
import psutil
from rich import print, progress
from pathlib import Path
from typing import Optional, List
from rangeplotter.config.settings import Settings
from rangeplotter.io.kml import parse_radars
from rangeplotter.los.rings import compute_horizons
from rangeplotter.io.dem import DemClient, approximate_bounding_box
from rangeplotter.auth.cdse import CdseAuth
from rangeplotter.utils.logging import setup_logging, log_memory_usage
import time

app = typer.Typer(help="Radar LOS utility scaffold")

def _resolve_inputs(input_path: Optional[Path]) -> List[Path]:
    """Resolve input path to a list of KML files."""
    if input_path is None:
        # Default to input/ directory
        input_dir = Path("input")
        if not input_dir.exists():
            return []
        return list(input_dir.glob("*.kml"))
    elif input_path.is_dir():
        return list(input_path.glob("*.kml"))
    else:
        return [input_path]

def _load_radars(kml_files: List[Path], radome_height: float) -> List:
    """Load radars from multiple KML files."""
    all_radars = []
    for kml_file in kml_files:
        if not kml_file.exists():
            typer.echo(f"[yellow]Warning: Input file {kml_file} not found.[/yellow]")
            continue
        radars = parse_radars(str(kml_file), radome_height)
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
    input_path: Optional[Path] = typer.Option(None, "--input", "-i", help="Path to radar KML file or directory"),
    limit: int = typer.Option(20, help="Max COP-DEM products per radar bbox")
):
    """Pre-fetch COP-DEM product metadata for each radar bounding box."""
    settings = Settings.from_file(config)
    setup_logging(settings.logging)
    
    kml_files = _resolve_inputs(input_path)
    if not kml_files:
        typer.echo("[red]No input KML files found.[/red]")
        raise typer.Exit(code=1)
        
    radars = _load_radars(kml_files, settings.radome_height_m_agl)
    
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
        horizon = mutual_horizon_distance(settings.radome_height_m_agl, max_alt, r.latitude, settings.atmospheric_k_factor)
        # Add 5% buffer to match compute_viewshed logic and prevent re-downloading fringe tiles
        horizon *= 1.05
        bbox = approximate_bounding_box(r.longitude, r.latitude, horizon)
        tiles = dem_client.query_tiles(bbox, limit=limit)
        typer.echo(f"Radar {r.name}: {len(tiles)} DEM products referenced (bbox radius ~{horizon/1000:.1f} km)")
    typer.echo("DEM metadata preparation complete.")

@app.command()
def debug_auth_dem(
    config: Path = typer.Option(Path("config/config.yaml"), "--config", help="Path to config YAML"),
    input_path: Optional[Path] = typer.Option(None, "--input", "-i", help="Path to radar KML file or directory")
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
        
    radars = _load_radars(kml_files, settings.radome_height_m_agl)
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
    config: Path = typer.Option(Path("config/config.yaml"), "--config", help="Path to config YAML"),
    input_path: Optional[Path] = typer.Option(None, "--input", "-i", help="Path to radar KML file or directory"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Override output directory"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Verbosity level: 0=Standard, 1=Info, 2=Debug")
):
    """
    Calculate the theoretical maximum geometric horizon (range rings) for each radar.
    
    This command computes the maximum possible detection range based on Earth curvature 
    and atmospheric refraction (k-factor), ignoring terrain obstructions.
    """
    start_time = time.time()
    settings = Settings.from_file(config)
    if output_dir:
        settings.output_dir = str(output_dir)
        
    log = setup_logging(settings.logging, verbose=verbose)
    altitudes = settings.effective_altitudes
    
    kml_files = _resolve_inputs(input_path)
    if not kml_files:
        typer.echo("[red]No input KML files found.[/red]")
        raise typer.Exit(code=1)
        
    radars = _load_radars(kml_files, settings.radome_height_m_agl)
    
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
    max_target_alt = max(settings.effective_altitudes)
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
    with progress.Progress(progress.SpinnerColumn(), progress.TextColumn("{task.description}")) as prog:
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
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    from rangeplotter.io.export import export_horizons_kml  # lazy import to avoid loading pyproj for other commands
    kml_path = output_dir / "horizons.kml"
    export_horizons_kml(str(kml_path), rings_all, meta, style=settings.style.model_dump())
    if verbose >= 2:
        print("[grey58]DEBUG: Export complete.")
    print(f"[green]Exported horizons to {kml_path}[/green]")
    
    end_time = time.time()
    total_time = end_time - start_time
    print(f"[bold]Total execution time: {total_time:.1f}s[/bold]")
    print(f"  - DEM Download time: {dem_client.total_download_time:.1f}s")
    print(f"  - Processing time: {total_time - dem_client.total_download_time:.1f}s")

@app.command()
def viewshed(
    config: Path = typer.Option(Path("config/config.yaml"), "--config", help="Path to config YAML"),
    input_path: Optional[Path] = typer.Option(None, "--input", "-i", help="Path to radar KML file or directory"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Override output directory"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Verbosity level: 0=Standard, 1=Info, 2=Debug")
):
    """
    Calculate the actual terrain-aware visibility (viewshed) for each radar.
    
    This command downloads Copernicus GLO-30 DEM data and performs a radial sweep 
    Line-of-Sight (LOS) calculation, accounting for Earth curvature, refraction, 
    and terrain obstructions.
    """
    start_time = time.time()
    settings = Settings.from_file(config)
    if output_dir:
        settings.output_dir = str(output_dir)
        
    log = setup_logging(settings.logging, verbose=verbose)
    altitudes = settings.effective_altitudes
    
    kml_files = _resolve_inputs(input_path)
    if not kml_files:
        typer.echo("[red]No input KML files found.[/red]")
        raise typer.Exit(code=1)
        
    radars = _load_radars(kml_files, settings.radome_height_m_agl)
    
    auth = CdseAuth(
        token_url=settings.copernicus_api.token_url,
        client_id=settings.copernicus_api.client_id or "cdse-public",
        username=settings.copernicus_api.username,
        password=settings.copernicus_api.password,
        refresh_token=settings.copernicus_api.refresh_token,
        verbose=verbose
    )
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
    max_target_alt = max(settings.effective_altitudes)
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

    from rangeplotter.los.viewshed import compute_viewshed
    from rangeplotter.io.export import export_viewshed_kml
    
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    total_tasks = len(radars) * len(settings.effective_altitudes) * 100
    
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
    ) as prog:
        overall_task = prog.add_task("Computing viewshed...", total=total_tasks)
        
        for r_idx, sensor in enumerate(radars):
            prog.update(overall_task, description=f"Processing {sensor.name}...")
            
            for alt_idx, alt in enumerate(settings.effective_altitudes):
                prog.update(overall_task, description=f"Computing viewshed for {sensor.name} @ {alt}m")
                
                # Create a transient task for the calculation details
                calc_task = prog.add_task("  Initializing...", total=100)
                
                # Base completion for previous tasks
                base_completed = (r_idx * len(settings.effective_altitudes) + alt_idx) * 100
                
                def _update_progress(step: str, pct: float):
                    # Ensure pct is within 0-100
                    pct = max(0.0, min(100.0, pct))
                    prog.update(calc_task, description=f"  {step}...", completed=pct)
                    
                    # Map sub-steps to overall progress (0-100 for this task)
                    # Heuristic weights:
                    # - Download/Reproject: 0-10%
                    # - LOS: 10-70% (60% weight)
                    # - Mask: 70-90% (20% weight)
                    # - Vectorize/Transform: 90-100%
                    
                    task_progress = 0.0
                    if step == "Downloading DEM":
                        task_progress = 0.0
                    elif step == "Reprojecting DEM":
                        task_progress = 5.0
                    elif step == "Computing LOS":
                        task_progress = 10.0 + (pct * 0.6)
                    elif step == "Generating Mask":
                        task_progress = 70.0 + (pct * 0.2)
                    elif step == "Vectorizing":
                        task_progress = 90.0
                    elif step == "Transforming to WGS84":
                        task_progress = 95.0
                        
                    prog.update(overall_task, completed=base_completed + task_progress)
                
                try:
                    if verbose >= 2:
                        log_memory_usage(log, f"Before {sensor.name} @ {alt}m")
                    # Use model_dump (Pydantic V2)
                    cfg_dict = settings.model_dump()
                    poly = compute_viewshed(sensor, alt, dem_client, cfg_dict, progress_callback=_update_progress, rich_progress=prog)
                    if verbose >= 2:
                        log_memory_usage(log, f"After {sensor.name} @ {alt}m")
                    
                    # Construct filename: {site_name}_{altitude}m_viewshed.kml
                    # Sanitize name for filename
                    safe_name = "".join(c for c in sensor.name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                    out_path = output_dir / f"{safe_name}_{alt}m_viewshed.kml"
                    
                    export_viewshed_kml(
                        viewshed_polygon=poly,
                        sensor_location=(sensor.longitude, sensor.latitude),
                        output_path=out_path,
                        sensor_name=sensor.name,
                        altitude=float(alt),
                        style_config=settings.style.model_dump()
                    )
                except Exception as e:
                    log.error(f"Failed to compute viewshed for {sensor.name} @ {alt}m: {e}", exc_info=True)
                    prog.console.print(f"[red]    Failed to compute viewshed for {sensor.name} @ {alt}m: {e}[/red]")
                    import traceback
                    traceback.print_exc()
                finally:
                    prog.remove_task(calc_task)
                
                # Ensure we hit exactly the next 100 mark
                prog.update(overall_task, completed=base_completed + 100)
            
    print("[green]Viewshed computation complete.[/green]")
    
    end_time = time.time()
    total_time = end_time - start_time
    print(f"[bold]Total execution time: {total_time:.1f}s[/bold]")
    print(f"  - DEM Download time: {dem_client.total_download_time:.1f}s")
    print(f"  - Processing time: {total_time - dem_client.total_download_time:.1f}s")

@app.command("detection-range")
def detection_range(
    input_path: Path = typer.Option(..., "--input", "-i", help="Path to viewshed KML file or directory"),
    max_range_km: float = typer.Option(..., "--range", "-r", help="Maximum detection range in kilometers"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Verbosity level")
):
    """
    Clip existing viewshed KMLs to a maximum detection range and append the result to the same file.
    """
    from rangeplotter.io.kml import parse_viewshed_kml, add_polygon_to_kml
    from rangeplotter.geo.geometry import create_geodesic_circle
    
    # Resolve inputs
    files = []
    if input_path.is_dir():
        files = list(input_path.glob("*_viewshed.kml"))
    else:
        files = [input_path]
        
    if not files:
        typer.echo("[red]No viewshed KML files found.[/red]")
        raise typer.Exit(code=1)
        
    with progress.Progress(
        progress.SpinnerColumn(),
        progress.TextColumn("[progress.description]{task.description}"),
        progress.BarColumn(),
        progress.TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    ) as prog:
        task = prog.add_task("Clipping viewsheds...", total=len(files))
        
        for f in files:
            prog.update(task, description=f"Processing {f.name}...")
            try:
                # Parse
                sensor_loc, viewshed_poly = parse_viewshed_kml(str(f))
                
                if not sensor_loc or not viewshed_poly:
                    if verbose >= 1:
                        print(f"[yellow]Skipping {f.name}: Could not find sensor location or viewshed polygon.[/yellow]")
                    prog.advance(task)
                    continue
                
                # Create range circle
                circle = create_geodesic_circle(sensor_loc[0], sensor_loc[1], max_range_km)
                
                # Intersect
                clipped_poly = viewshed_poly.intersection(circle)
                
                if clipped_poly.is_empty:
                    if verbose >= 1:
                        print(f"[yellow]Warning: {f.name} resulted in empty polygon after clipping.[/yellow]")
                
                # Append to existing file
                name = f"Viewshed @ {max_range_km}km Limit"
                # Reuse the existing polyStyle if available
                add_polygon_to_kml(str(f), clipped_poly, name, style_url="#polyStyle")
                
            except Exception as e:
                print(f"[red]Error processing {f.name}: {e}[/red]")
                if verbose >= 2:
                    import traceback
                    traceback.print_exc()
            
            prog.advance(task)
            
    print(f"[green]Processing complete. Files updated in place.[/green]")

if __name__ == "__main__":
    app()
