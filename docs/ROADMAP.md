# RangePlotter Roadmap

## 1. Objectives
- Compute theoretical radar geometric range rings for specified target altitudes using Earth curvature + atmospheric refraction adjustments.
- Refine each ring via terrain-aware line-of-sight (viewshed) using Copernicus GLO-30 DEM to produce polygons of actual visibility per altitude per radar.
- **New Feature**: `detection-range` command to clip viewsheds to a maximum instrumented range.
- Output KML/KMZ files organized in a logical directory structure for Google Earth Pro.
- Provide a modular, extensible Python codebase.

## 2. Architecture
- `rangeplotter` package structure.
- `io.export`: Handles KML generation. **Updated to produce self-contained KMLs with sensor location and viewshed.**
- `cli`: `horizon`, `viewshed`, `detection-range`.

## 3. Current Status
- **Core**: Basic viewshed and horizon calculation implemented.
- **DEM**: Copernicus GLO-30 integration working.
- **Export**: Basic KML polygon export.

## 4. Upcoming Features
### Feature: Detection Range Clipping
**Goal**: Allow users to limit the calculated viewshed to a specific maximum range (e.g., 100km) to simulate radar instrument limits.

**Implementation Plan**:
1.  **Refactor Viewshed Export**:
    *   Update `viewshed` command to output a single KML file per sensor/altitude.
    *   The KML will contain a `<Folder>` with:
        *   A `<Placemark>` for the Sensor Location (Point).
        *   A `<Placemark>` for the Viewshed (Polygon).
    *   This ensures the file is self-contained and easy to process.

2.  **Implement `detection-range` Command**:
    *   Input: Existing viewshed KML file(s).
    *   Argument: `--range` (km).
    *   Logic:
        *   Parse KML to find Sensor Point and Viewshed Polygon.
        *   Create a geodesic circle (polygon) of radius `--range` around the Sensor Point.
        *   Compute intersection: `Viewshed ∩ RangeCircle`.
        *   Add the result as a new `<Placemark>` to the KML folder.
    *   Output: Updated KML file.

## 5. Future Work
- Union polygons across multiple radars.
- Advanced propagation modeling.
- Web UI.
