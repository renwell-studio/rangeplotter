# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
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
