# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Comprehensive automated test suite using `pytest`.
- Achieved >86% code coverage across all modules.
- Added tests for interactive CLI prompts, authentication flows, and DEM caching logic.
- Added tests for complex KML geometries (MultiGeometry, holes in polygons).
- Included `example.env` in the distribution to help users configure authentication.
- Improved authentication error messages with actionable guidance.
- Added summary table to `detection-range` command output showing created files and execution stats.
- Added human-readable duration (e.g., `1h 23m`) to execution time summaries.

### Changed
- Renamed default log file from `visibility.log` to `rangeplotter.log`.
- Updated output KML filenames to use `rangeplotter-` prefix instead of `visibility-`.
- Standardized internal naming conventions to "RangePlotter".

### Fixed
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
