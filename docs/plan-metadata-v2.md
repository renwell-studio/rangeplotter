## Plan: Implement Metadata in Output KMLs

This plan implements comprehensive, consistent metadata embedding in all KML outputs. Metadata will be stored in two formats within each KML:
1.  **HTML Description**: A formatted table visible in Google Earth pop-ups for human inspection.
2.  **ExtendedData**: Machine-readable key-value pairs for future tooling (e.g., Smart Resume) and advanced inspection.

### Key Requirements
-   **Consistency**: Uniform style across `viewshed`, `detection-range`, and `horizon`.
-   **Content**: Must include Sensor Lat/Lon, **Ground Elevation (MSL)**, Sensor Height (AGL), and Target Altitude (unless Union).
-   **Display**: Metadata must appear in the main pane pop-up but **NOT** in the side navigation pane (use `<Snippet>`).
-   **Tagging**: Include "RangePlotter [version]" tag.

### Steps
1.  **Update Export Logic (`src/rangeplotter/io/export.py`)**
    *   Update `export_viewshed_kml` and `export_horizons_kml`.
    *   Implement `_format_metadata_html` and `_format_extended_data`.
    *   **Crucial**: Add `<Snippet maxLines="0"></Snippet>` to all Placemarks to suppress metadata in the Places pane.
    *   Update `export_horizons_kml` to accept per-sensor metadata (not just global).

2.  **Update Viewshed Command (`src/rangeplotter/cli/main.py`)**
    *   Construct metadata dictionary including:
        *   **System**: RangePlotter version, Timestamp.
        *   **Sensor**: Name, Lat, Lon, **Ground Elevation**, Height AGL, Height MSL.
        *   **Target**: Altitude, Reference.
        *   **Physics**: Max Range, Refraction, Earth Radius.
        *   **Processing**: Hash.

3.  **Update Horizon Command (`src/rangeplotter/cli/main.py`)**
    *   Update `export_horizons_kml` call to pass full sensor details (Ground Alt, AGL) for each radar, not just Lat/Lon.
    *   Generate per-sensor metadata in the export function.

4.  **Update Detection Range Command (`src/rangeplotter/cli/main.py`)**
    *   Construct metadata.
    *   If **Single Sensor**: Include full sensor details (Lat/Lon, Ground Alt, etc.).
    *   If **Union**: Include list of sources, but omit specific sensor geometry if it varies.

### Verification
-   Run `viewshed`, `horizon`, `detection-range`.
-   Check KML output for `<Snippet maxLines="0">`.
-   Check KML output for "Ground Elevation".
