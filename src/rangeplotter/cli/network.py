from rangeplotter.config.settings import Settings, load_settings
from rangeplotter.io.kml import parse_radars
from rangeplotter.io.csv_input import parse_csv_radars
from rangeplotter.models.radar_site import RadarSite
from rangeplotter.utils.session import SessionManager
from rich.table import Table
from rich.prompt import Prompt, Confirm
import datetime
import typer
import subprocess
import sys
import csv
from pathlib import Path
from typing import Optional, List
from rich import print

app = typer.Typer(help="Network-level analysis commands")

@app.command()
def run(
    config: Optional[Path] = typer.Option(None, "--config", help="Path to config YAML"),
    input_path: Optional[Path] = typer.Option(None, "--input", "-i", help="Path to input directory or KML/CSV file."),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Path to project output directory"),
    force: bool = typer.Option(False, "--force", help="Force recalculation even if output exists."),
    filter_pattern: Optional[str] = typer.Option(None, "--filter", help="Regex pattern to filter sensors by name."),
    sensor_heights_cli: Optional[List[str]] = typer.Option(None, "--sensor-heights", "-sh", help="Sensor heights AGL in meters (comma separated). Overrides config."),
    union: Optional[bool] = typer.Option(None, "--union/--no-union", help="Union detection range outputs"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip interactive confirmation (non-interactive mode)."),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Verbosity level")
):
    """
    Run the complete analysis pipeline: Viewshed -> Horizon -> Detection Range.
    
    This command orchestrates the entire workflow:
    1. Calculates viewsheds for all sensors (skipping existing ones unless --force is used).
    2. Calculates theoretical horizons.
    3. Clips viewsheds to detection ranges and creates union coverage maps.
    
    If input/output are not specified, an interactive wizard will prompt for them.
    """
    
    # Load settings early for the wizard
    if config:
        settings = Settings.from_file(config)
    else:
        settings = load_settings()

    # Resolve input path extensions if file not found
    if input_path and not input_path.exists():
        # 1. Try resolving relative to configured input_dir
        potential_path = Path(settings.input_dir) / input_path
        if potential_path.exists():
            input_path = potential_path
        else:
            # 2. Try appending extensions if no extension provided (in CWD)
            if not input_path.suffix:
                for ext in ['.csv', '.kml']:
                    candidate = input_path.with_suffix(ext)
                    if candidate.exists():
                        input_path = candidate
                        print(f"[dim]Resolved input to: {input_path}[/dim]")
                        break
            
            # 3. Try appending extensions in input_dir
            if not input_path.exists() and not input_path.suffix:
                 for ext in ['.csv', '.kml']:
                    candidate = Path(settings.input_dir) / input_path.with_suffix(ext)
                    if candidate.exists():
                        input_path = candidate
                        print(f"[dim]Resolved input to: {input_path}[/dim]")
                        break

    # Override sensor heights if provided via CLI
    if sensor_heights_cli:
        parsed_heights = []
        for h_str in sensor_heights_cli:
            parts = h_str.split(',')
            for p in parts:
                try:
                    parsed_heights.append(float(p.strip()))
                except ValueError:
                    print(f"[yellow]Warning: Invalid sensor height value '{p}'. Skipping.[/yellow]")
        if parsed_heights:
            settings.sensor_height_m_agl = sorted(list(set(parsed_heights)))
            print(f"Using sensor heights from CLI: {settings.sensor_height_m_agl}")

    # Override union setting if provided via CLI
    if union is not None:
        settings.union_outputs = union

    # --- Session Management ---
    session_mgr = SessionManager(Path("working_files"))

    # --- Wizard / Interactive Mode ---
    if not yes:
        print(f"\n[bold cyan]RangePlotter Network Analysis Wizard[/bold cyan]")
        print("[dim]This wizard will help you configure the analysis run.[/dim]\n")
        
        if not input_path and not output_dir:
            last_session = session_mgr.load_last_session()
            if last_session:
                print(f"\n[bold]Found previous session:[/bold]")
                print(f"  Input: {last_session.get('input_path')}")
                print(f"  Output: {last_session.get('output_dir')}")
                print(f"  Time: {last_session.get('timestamp')}")
                
                if Confirm.ask("Resume this session?", default=True):
                    input_path = Path(str(last_session.get('input_path')))
                    output_dir = Path(str(last_session.get('output_dir')))
                    print("[green]Resuming session...[/green]")        # 1. Resolve Input
        if not input_path:
            default_input = "examples/radars.csv"
            input_str = Prompt.ask("Input file or directory", default=default_input)
            
            # Check if file exists in CWD or sensor_locations
            p = Path(input_str)
            if p.exists():
                input_path = p
            else:
                # Try sensor_locations
                p_loc = Path("working_files/sensor_locations") / input_str
                if p_loc.exists():
                    input_path = p_loc
                else:
                    # Try adding extension if missing? No, keep it simple.
                    input_path = p # Keep original to fail later or prompt again?
        
        if not input_path.exists():
            print(f"[bold red]Error: Input path '{input_path}' does not exist.[/bold red]")
            raise typer.Exit(code=1)

        # 2. Resolve Output
        if not output_dir:
            # Generate a default output name based on input
            stem = input_path.stem
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_output = f"working_files/network/{stem}_{timestamp}"
            
            output_str = Prompt.ask("Output directory", default=default_output)
            output_dir = Path(output_str)

        # --- Site Selection ---
        if input_path.is_file():
            all_sites = []
            if input_path.suffix.lower() == '.kml':
                all_sites = parse_radars(str(input_path), settings.sensor_height_m_agl)
            elif input_path.suffix.lower() == '.csv':
                all_sites = parse_csv_radars(input_path, settings.sensor_height_m_agl)
                
            selected_sites = all_sites
            if all_sites:
                print(f"\n[bold]Found {len(all_sites)} sites in input.[/bold]")
                if Confirm.ask("Do you want to select specific sites to process?", default=False):
                    # Show table
                    table = Table(show_header=True, header_style="bold magenta")
                    table.add_column("#", style="dim")
                    table.add_column("Name")
                    table.add_column("Location")
                    
                    for idx, site in enumerate(all_sites):
                        table.add_row(str(idx+1), site.name, f"{site.latitude:.4f}, {site.longitude:.4f}")
                    print(table)
                    
                    while True:
                        selection_str = Prompt.ask("Enter site numbers to process (comma-separated, e.g. 1,3,5)")
                        try:
                            indices = [int(x.strip()) - 1 for x in selection_str.split(",") if x.strip()]
                            if not indices:
                                raise ValueError
                            selected_sites = [all_sites[i] for i in indices if 0 <= i < len(all_sites)]
                            if not selected_sites:
                                print("[red]No valid sites selected. Please try again.[/red]")
                                continue
                            break
                        except (ValueError, IndexError):
                            print("[red]Invalid selection. Please enter comma-separated numbers.[/red]")

            # Generate CSV if subset selected or KML input (to standardize)
            if selected_sites and (len(selected_sites) < len(all_sites) or input_path.suffix.lower() == '.kml'):
                output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%H%M%S")
                generated_csv_path = output_dir / f"site_selection_{timestamp}.csv"
                
                print(f"[dim]Generating site list CSV: {generated_csv_path}[/dim]")
                
                with open(generated_csv_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Name', 'Latitude', 'Longitude', 'Height_AGL'])
                    for site in selected_sites:
                        # Determine Height AGL
                        h_val = ""
                        if site.altitude_mode == 'relativeToGround':
                            h_val = site.input_altitude if site.input_altitude is not None else 0.0
                        else:
                            # clampToGround
                            # If it matches the default used for parsing, leave empty to allow dynamic default
                            if site.sensor_height_m_agl != settings.sensor_height_m_agl:
                                h_val = site.sensor_height_m_agl
                        
                        writer.writerow([site.name, site.latitude, site.longitude, h_val])
                
                # Update input_path to use the new CSV
                input_path = generated_csv_path

        while True:
            # 3. Configure Settings
            print("\n[bold]Configuration Settings:[/bold]")
            
            # Target Altitudes
            default_alts = ",".join(map(str, settings.altitudes_msl_m))
            alts_str = Prompt.ask("Target Altitudes (m, comma-separated)", default=default_alts)
            try:
                settings.altitudes_msl_m = [float(x.strip()) for x in alts_str.split(",") if x.strip()]
            except ValueError:
                print("[red]Invalid altitude format. Using defaults.[/red]")

            # Reference
            settings.target_altitude_reference = Prompt.ask(
                "Target Altitude Reference", 
                choices=["agl", "msl"], 
                default=settings.target_altitude_reference
            )

            # Sensor Height
            h_str = Prompt.ask("Default Sensor Height (m AGL)", default=str(settings.sensor_height_m_agl))
            try:
                # Handle list format (e.g. "[2.0, 5.0]") or comma-separated string
                clean_str = h_str.strip("[]").replace("'", "").replace('"', "")
                parts = [float(x.strip()) for x in clean_str.split(",") if x.strip()]
                
                if not parts:
                    raise ValueError("No valid heights provided")
                
                if len(parts) == 1:
                    settings.sensor_height_m_agl = parts[0]
                else:
                    settings.sensor_height_m_agl = sorted(list(set(parts)))
            except ValueError:
                print("[red]Invalid height format. Using default.[/red]")

            # Atmosphere
            k_str = Prompt.ask("Atmospheric Refraction (k-factor)", default=str(settings.atmospheric_k_factor))
            try:
                settings.atmospheric_k_factor = float(k_str)
            except ValueError:
                print("[red]Invalid k-factor. Using default.[/red]")

            # Detection Ranges
            default_ranges = ",".join(map(str, settings.detection_ranges))
            ranges_str = Prompt.ask("Detection Ranges (km, comma-separated)", default=default_ranges)
            try:
                settings.detection_ranges = [float(x.strip()) for x in ranges_str.split(",") if x.strip()]
            except ValueError:
                print("[red]Invalid range format. Using defaults.[/red]")

            # Union Outputs
            if union is None:
                settings.union_outputs = Confirm.ask(
                    "Union viewsheds into single coverage map?", 
                    default=settings.union_outputs
                )

            # Multiscale
            settings.multiscale.enable = Confirm.ask(
                "Enable Multiscale Processing (faster)?", 
                default=settings.multiscale.enable
            )

            # 4. Review Configuration
            print("\n[bold]Configuration Review:[/bold]")
            table = Table(show_header=False, box=None)
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="yellow")
            
            table.add_row("Input Path", str(input_path))
            table.add_row("Output Directory", str(output_dir))
            table.add_row("Target Altitudes", str(settings.effective_altitudes) + f" ({settings.target_altitude_reference.upper()})")
            table.add_row("Sensor Height", f"{settings.sensor_height_m_agl} m AGL")
            table.add_row("Atmosphere (k)", str(settings.atmospheric_k_factor))
            table.add_row("Detection Ranges", str(settings.detection_ranges) if settings.detection_ranges else "None")
            table.add_row("Union Outputs", str(settings.union_outputs))
            table.add_row("Multiscale", f"Enabled (Near: {settings.multiscale.res_near_m}m, Far: {settings.multiscale.res_far_m}m)" if settings.multiscale.enable else "Disabled")
            
            print(table)
            print("")

            if Confirm.ask("Proceed with these settings?", default=True):
                break
            
            if not Confirm.ask("Would you like to revise the settings?", default=True):
                print("[yellow]Analysis cancelled.[/yellow]")
                raise typer.Exit(code=0)
            
            print("\n[dim]Restarting configuration wizard...[/dim]")

    # --- Non-Interactive Defaults ---
    else:
        if not input_path:
            print("[bold red]Error: --input is required in non-interactive mode.[/bold red]")
            raise typer.Exit(code=1)
        
        if not output_dir:
            # Auto-generate output dir in non-interactive mode if not specified
            stem = input_path.stem
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path(f"working_files/network/{stem}_{timestamp}")
            print(f"[yellow]No output directory specified. Using auto-generated: {output_dir}[/yellow]")

    # Define sub-directories
    viewshed_dir = output_dir / "viewshed"
    horizon_dir = output_dir / "horizon"
    detection_dir = output_dir / "detection"
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save run configuration
    import yaml
    run_config_path = output_dir / "run_config.yaml"
    with open(run_config_path, 'w') as f:
        # Dump settings to YAML
        # We use model_dump(mode='json') to ensure serialization of types
        yaml.dump(settings.model_dump(mode='json'), f)
    
    print(f"[bold blue]Starting Network Analysis[/bold blue]")
    print(f"Input: {input_path}")
    print(f"Output: {output_dir}")
    print(f"Config: {run_config_path}")

    
    # 1. Run Viewshed
    print("\n[bold]Step 1: Calculating Viewsheds[/bold]")
    
    # Construct command based on execution environment (frozen binary vs python script)
    if getattr(sys, 'frozen', False):
        # Running as compiled binary (PyInstaller)
        # sys.executable is the binary itself
        # We call the binary directly with the subcommand
        cmd_viewshed = [
            sys.executable, "viewshed",
            "--input", str(input_path),
            "--output", str(viewshed_dir),
            "--config", str(run_config_path),
        ]
    else:
        # Running as python script
        cmd_viewshed = [
            sys.executable, "-m", "rangeplotter", "viewshed",
            "--input", str(input_path),
            "--output", str(viewshed_dir),
            "--config", str(run_config_path),
        ]

    # Add optional flags
    if verbose > 0:
        cmd_viewshed.append("--verbose")
    if verbose > 1:
        cmd_viewshed.append("-v") # Add extra v for debug
            
    if force:
        cmd_viewshed.append("--force")
        
    if filter_pattern:
        cmd_viewshed.extend(["--filter", filter_pattern])
        
    # Filter out empty strings
    cmd_viewshed = [c for c in cmd_viewshed if c]
    
    if verbose >= 2:
        print(f"[dim]Running: {' '.join(cmd_viewshed)}[/dim]")
        
    result = subprocess.run(cmd_viewshed)
    if result.returncode != 0:
        print("[bold red]Viewshed calculation failed. Aborting.[/bold red]")
        raise typer.Exit(code=result.returncode)
        
    # 2. Run Horizon
    print("\n[bold]Step 2: Calculating Horizons[/bold]")
    
    if getattr(sys, 'frozen', False):
        cmd_horizon = [
            sys.executable, "horizon",
            "--input", str(input_path),
            "--output", str(horizon_dir),
            "--config", str(run_config_path),
        ]
    else:
        cmd_horizon = [
            sys.executable, "-m", "rangeplotter", "horizon",
            "--input", str(input_path),
            "--output", str(horizon_dir),
            "--config", str(run_config_path),
        ]

    if verbose > 0:
        cmd_horizon.append("--verbose")
    if verbose > 1:
        cmd_horizon.append("-v")
    
    if filter_pattern:
        cmd_horizon.extend(["--filter", filter_pattern])
        
    cmd_horizon = [c for c in cmd_horizon if c]
    
    if verbose >= 2:
        print(f"[dim]Running: {' '.join(cmd_horizon)}[/dim]")

    result = subprocess.run(cmd_horizon)
    if result.returncode != 0:
        print("[bold red]Horizon calculation failed. Aborting.[/bold red]")
        raise typer.Exit(code=result.returncode)

    # 3. Run Detection Range
    print("\n[bold]Step 3: Processing Detection Ranges[/bold]")
    # Input for detection range is the output of viewshed
    # We use a glob pattern to find the KMLs
    viewshed_pattern = str(viewshed_dir / "*.kml")
    
    if getattr(sys, 'frozen', False):
        cmd_detection = [
            sys.executable, "detection-range",
            "--input", viewshed_pattern,
            "--output", str(detection_dir),
            "--config", str(run_config_path),
        ]
    else:
        cmd_detection = [
            sys.executable, "-m", "rangeplotter", "detection-range",
            "--input", viewshed_pattern,
            "--output", str(detection_dir),
            "--config", str(run_config_path),
        ]

    if verbose > 0:
        cmd_detection.append("--verbose")
    if verbose > 1:
        cmd_detection.append("-v")
    
    if settings.union_outputs:
        cmd_detection.append("--union")
    else:
        cmd_detection.append("--no-union")
        
    cmd_detection = [c for c in cmd_detection if c]
    
    if verbose >= 2:
        print(f"[dim]Running: {' '.join(cmd_detection)}[/dim]")

    result = subprocess.run(cmd_detection)
    if result.returncode != 0:
        print("[bold red]Detection range processing failed. Aborting.[/bold red]")
        raise typer.Exit(code=result.returncode)
        
    print("\n[bold green]Network Analysis Complete![/bold green]")
    print(f"Results available in: {output_dir}")
    
    # Save session for smart resume
    session_mgr.save_session(input_path, output_dir, run_config_path)
