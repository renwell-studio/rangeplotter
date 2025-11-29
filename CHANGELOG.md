# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.6] - Unreleased
### Fixed
- **Network Input Resolution**: Fixed issue where `network run` would fail to find input files if they were not in the current directory (now checks `working_files/sensor_locations` as a fallback, matching `viewshed` behavior).

### Changed
- **CLI Verbosity**: Standardized verbosity flags across all commands. `network run` now correctly passes `-v` (INFO) and `-vv` (DEBUG) to subprocesses, and only displays raw command strings at the DEBUG level.

### Documentation
- **Getting Started**: Updated the "First Run" guide to clarify how to export placemarks from Google Earth.
- **Configuration**: Added comments to `config.yaml` clarifying that `sensor_height_m_agl` accepts a comma-separated list of values.
- **Metadata**: Added author details to the Python package metadata.

## [0.1.5] - 2025-11-28
### Added
- **Sensor Height Array**: Added support for calculating viewsheds for multiple sensor heights in a single run. The `sensor_height_m_agl` setting in `config.yaml` now accepts a list of heights (e.g., `[10.0, 20.0]`).
- **CLI Sensor Heights**: Added `--sensor-heights` / `-sh` option to the `viewshed` command to override configured sensor heights with a comma-separated list.
- **Integrated Network Workflow**: New `network run` command orchestrates the entire pipeline (`viewshed` -> `horizon` -> `detection-range`) in a single step.
- **Smart Resume**: The system now tracks the state of each simulation (hashing inputs and parameters). Re-running a command will automatically skip viewsheds that have already been calculated with the same parameters, saving significant time.
- **CSV Input Support**: Added support for defining radar sites via CSV files (`.csv`) in addition to KML.
- **Filtering**: Added `--filter` option to `viewshed` and `network` commands to process only specific sites matching a regex pattern.
- **Interactive Wizard**: The `network run` command features an interactive wizard to guide users through configuration if arguments are omitted. It now includes a review loop, allowing users to revise settings before starting the analysis.
- **Interactive Site Selection**: The `network run` wizard now allows users to select a subset of sites from the input file to process.
- **Package Entry Point**: The package can now be run directly via `python -m rangeplotter`.
- **Examples**: Added `examples/` directory with sample CSV and KML files.
- **Hybrid Distribution Model**: Now releasing both a standalone binary (Linux) and a standard Python Wheel (`.whl`) for cross-platform/developer use.
- **Graceful Upgrade Script**: Added `install_or_upgrade.sh` to the binary release. This script automates installation and upgrades while preserving user configuration (`config.yaml`) and data.
- **Release Candidate Workflow**: CI/CD pipeline now supports `-rc` tags (e.g., `v0.1.5-rc1`) for pre-release testing.
- **KML Export Altitude Mode**: Added `kml_export_altitude_mode` to `config.yaml`. Defaults to `"clamped"` (clampToGround) for better visualization in Google Earth, with an option for `"absolute"` to render at the calculated target altitude.
- **Sensor Altitude Override**: The `viewshed` command now respects altitude information in input KMLs. If a sensor uses `<altitudeMode>relativeToGround</altitudeMode>` with a valid altitude, this value overrides the default `sensor_height_m_agl` from `config.yaml` for that specific sensor.
- **Offline Capability**: The `viewshed` command now checks for cached DEM tiles before attempting to authenticate with Copernicus. If all required tiles are present locally, the tool runs fully offline without requiring an internet connection or valid credentials.
- **User Guide**: Added a comprehensive documentation set in `docs/guide/`, covering installation, configuration, commands, and best practices.

### Changed
- **Default Output Directory**: The `network run` command now defaults to `working_files/network/{input_name}_{timestamp}` if no output directory is specified, keeping the project workspace organized.
- Renamed default input directory from `working_files/input` to `working_files/sensor_locations` to better reflect its purpose.
- Updated `install_or_upgrade.sh` to automatically migrate the legacy `input` directory to `sensor_locations` and update `config.yaml` during upgrades.
- Streamlined `README.md` to focus on quick start and installation, moving detailed documentation to the new User Guide.
- Updated `docs/RELEASE_PROCESS.md` to reflect the new build artifacts and RC workflow.

### Fixed
- **Detection Range Union**: Fixed logic to prevent unioning viewsheds from the same sensor at different heights. They are now treated as variants.
- **Network Run Wizard**: Fixed a parsing issue in the network run wizard causing it to reject multiple sensor heights.
- **Absolute Altitude Logic**: Fixed a critical bug where the default sensor height offset was incorrectly added to sensors defined with `absolute` altitude mode in KML inputs. Absolute altitudes are now treated as exact MSL values.
- **Network Run**: Fixed issue where `network run` would fail to find input files if they were not in the current directory (now checks `working_files/sensor_locations`).
- **Network Run**: Fixed issue where `network run` would fail when running as a frozen binary (PyInstaller) due to incorrect subprocess call.
- **Help Text**: Removed "scaffold" from the main help text.
- **Cleanup**: Removed debug print statements from KML parsing module.

## [0.1.4] - 2025-11-24
### Added
- Comprehensive automated test suite using `pytest`.
- Achieved >86% code coverage across all modules.
- Added tests for interactive CLI prompts, authentication flows, and DEM caching logic.
- Added tests for complex KML geometries (MultiGeometry, holes in polygons).
- Included `example.env` in the distribution to help users configure authentication.
- Improved authentication error messages with actionable guidance.
- Added summary table to `detection-range` command output showing created files and execution stats.
- Added human-readable duration (e.g., `1h 23m`) to execution time summaries.
- Added `--verbose` / `-v` flag to `detection-range` command for detailed logging of parsing and processing steps.
- Added debug logging for geometry clipping and union operations.
- Implemented smart input file resolution: if a file is not found in the current directory, the CLI now checks `working_files/input` (for `viewshed`) or `working_files/viewshed` (for `detection-range`).
- `detection-range` now preserves `_MSL` or `_AGL` filename suffixes from input files, ensuring the vertical datum reference is maintained in the output filenames.
- Added sequential numbering prefixes (e.g., `01_`, `02_`) to `viewshed` and `detection-range` output filenames. Files are now sorted by target altitude to ensure correct ordering when imported into Google Earth.

### Changed
- Renamed default log file from `visibility.log` to `rangeplotter.log`.
- Updated output KML filenames to use `rangeplotter-` prefix instead of `visibility-`.
- Standardized internal naming conventions to "RangePlotter".

### Fixed
- Fixed XML parsing error in Google Earth when sensor names or filenames contain special characters (e.g., `&`). Names are now properly escaped in the generated KML.
- Fixed various edge cases in KML parsing and export logic discovered during testing.
- Fixed potential issues with DEM tile download and caching resilience.

## [0.1.3] - 2025-11-22
### Added
- Support for AGL (Above Ground Level) target altitudes in viewshed calculations.
- New CLI flag `--ref` / `--reference` to toggle between 'msl' and 'agl' modes.
- New configuration option `target_altitude_reference` in `config.yaml`.

### Changed
- Moved `target_altitude_reference` setting to the top level in `config.yaml` for better visibility.
- Updated KML export to use `relativeToGround` altitude mode when AGL reference is selected, ensuring polygons render correctly above terrain in Google Earth.
- Updated default configuration values in `config.yaml` for simpler initial testing (`altitudes_msl_m`=[0], `detection_ranges`=[50]).
- Updated `README.md` configuration table to match current settings.

### Fixed
- Fixed issue where `detection-range` output KMLs had internal document and polygon names that did not match the filename.

## [0.1.2] - 2025-11-22
### Fixed
- Fixed issue where `data_cache` was resolving to a path outside the project root when using the default config structure.

## [0.1.1] - 2025-11-21
### Added
- Portable Zip archive release format containing binary, config, and working files.
- Documentation for the new release process in `docs/RELEASE_PROCESS.md`.

### Changed
- Updated `settings.py` to prioritize loading `config.yaml` from the executable directory or CWD over bundled defaults.
- Updated `config.yaml` to use relative paths compatible with the new folder structure.
- Updated `README.md` with new installation instructions.

## [0.1.0] - 2025-11-21
### Added
- Initial release of RangePlotter.
- Core functionality: `viewshed`, `horizon`, and `detection-range` commands.
- Copernicus GLO-30 DEM integration.
- KML export support.
