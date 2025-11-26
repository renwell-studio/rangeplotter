from rangeplotter.config.settings import Settings, load_settings
from rich.table import Table
from rich.prompt import Prompt, Confirm
import datetime
import typer
import subprocess
import sys
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

    # --- Wizard / Interactive Mode ---
    if not yes:
        print(f"\n[bold cyan]RangePlotter Network Analysis Wizard[/bold cyan]")
        print("[dim]This wizard will help you configure the analysis run.[/dim]\n")

        # 1. Resolve Input
        if not input_path:
            default_input = "examples/radars.csv"
            input_str = Prompt.ask("Input file or directory", default=default_input)
            input_path = Path(input_str)
        
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

        # 3. Review Configuration
        print("\n[bold]Configuration Review:[/bold]")
        table = Table(show_header=False, box=None)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="yellow")
        
        table.add_row("Input Path", str(input_path))
        table.add_row("Output Directory", str(output_dir))
        table.add_row("Target Altitudes", str(settings.effective_altitudes) + f" ({settings.target_altitude_reference.upper()})")
        table.add_row("Sensor Height", f"{settings.sensor_height_m_agl} m AGL")
        table.add_row("Atmosphere (k)", str(settings.atmospheric_k_factor))
        table.add_row("Detection Ranges", str(settings.detection_ranges) if settings.detection_ranges else "None (using defaults)")
        table.add_row("Multiscale", f"Enabled (Near: {settings.multiscale.res_near_m}m, Far: {settings.multiscale.res_far_m}m)" if settings.multiscale.enable else "Disabled")
        
        print(table)
        print("")

        if not Confirm.ask("Proceed with these settings?", default=True):
            print("[yellow]Analysis cancelled.[/yellow]")
            raise typer.Exit(code=0)

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
    
    print(f"[bold blue]Starting Network Analysis[/bold blue]")
    print(f"Input: {input_path}")
    print(f"Output: {output_dir}")

    
    # 1. Run Viewshed
    print("\n[bold]Step 1: Calculating Viewsheds[/bold]")
    cmd_viewshed = [
        sys.executable, "-m", "rangeplotter", "viewshed",
        "--input", str(input_path),
        "--output", str(viewshed_dir),
        "--verbose" if verbose > 0 else "",
    ]
    if verbose > 1:
        cmd_viewshed.append("-vv")
    if config:
        cmd_viewshed.extend(["--config", str(config)])
    if force:
        cmd_viewshed.append("--force")
    if filter_pattern:
        cmd_viewshed.extend(["--filter", filter_pattern])
        
    # Filter out empty strings
    cmd_viewshed = [c for c in cmd_viewshed if c]
    
    if verbose >= 1:
        print(f"[dim]Running: {' '.join(cmd_viewshed)}[/dim]")
        
    result = subprocess.run(cmd_viewshed)
    if result.returncode != 0:
        print("[bold red]Viewshed calculation failed. Aborting.[/bold red]")
        raise typer.Exit(code=result.returncode)
        
    # 2. Run Horizon
    print("\n[bold]Step 2: Calculating Horizons[/bold]")
    cmd_horizon = [
        sys.executable, "-m", "rangeplotter", "horizon",
        "--input", str(input_path),
        "--output", str(horizon_dir),
        "--verbose" if verbose > 0 else "",
    ]
    if verbose > 1:
        cmd_horizon.append("-vv")
    if config:
        cmd_horizon.extend(["--config", str(config)])
        
    cmd_horizon = [c for c in cmd_horizon if c]
    
    if verbose >= 1:
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
    
    cmd_detection = [
        sys.executable, "-m", "rangeplotter", "detection-range",
        "--input", viewshed_pattern,
        "--output", str(detection_dir),
        "--verbose" if verbose > 0 else "",
    ]
    if verbose > 1:
        cmd_detection.append("-vv")
    if config:
        cmd_detection.extend(["--config", str(config)])
        
    cmd_detection = [c for c in cmd_detection if c]
    
    if verbose >= 1:
        print(f"[dim]Running: {' '.join(cmd_detection)}[/dim]")

    result = subprocess.run(cmd_detection)
    if result.returncode != 0:
        print("[bold red]Detection range processing failed. Aborting.[/bold red]")
        raise typer.Exit(code=result.returncode)
        
    print("\n[bold green]Network Analysis Complete![/bold green]")
    print(f"Results available in: {output_dir}")
