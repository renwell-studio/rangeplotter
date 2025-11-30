## Plan: Implement Metadata in Output KMLs

This plan implements comprehensive, consistent metadata embedding in all KML outputs. Metadata will be stored in two formats within each KML:
1.  **HTML Description**: A formatted table visible in Google Earth pop-ups for human inspection.
2.  **ExtendedData**: Machine-readable key-value pairs for future tooling (e.g., Smart Resume) and advanced inspection.

### Steps
1.  **Update Export Logic (`src/rangeplotter/io/export.py`)**
    *   Update `export_viewshed_kml` signature to accept an optional `metadata: Dict[str, Any]` parameter.
    *   Implement `_format_metadata_html(metadata)` helper to generate a clean HTML table string.
    *   Implement `_format_extended_data(metadata)` helper to generate KML `<ExtendedData><Data name="...">...` tags.
    *   Inject the HTML into the `<description>` tag and ExtendedData into the `<Placemark>` of the generated KML.

2.  **Update Viewshed Command (`src/rangeplotter/cli/main.py`)**
    *   In the `viewshed` loop, construct a metadata dictionary containing:
        *   **System**: RangePlotter version, Timestamp.
        *   **Sensor**: Name, Lat, Lon, Height AGL, Height MSL (calculated).
        *   **Target**: Altitude, Reference (AGL/MSL).
        *   **Physics**: Max Range (Horizon), Refraction (k-factor), Earth Radius.
        *   **Processing**: Multiscale settings (if enabled), Smart Resume Hash.
    *   Pass this dictionary to `export_viewshed_kml`.

3.  **Update Detection Range Command (`src/rangeplotter/cli/main.py`)**
    *   In the `detection_range` loop, construct a metadata dictionary containing:
        *   **System**: RangePlotter version, Timestamp.
        *   **Parameters**: Detection Range (km), Target Altitude.
        *   **Mode**: Union (True/False), Variant Count.
        *   **Source**: List of sensor names included in the coverage map.
    *   Pass this dictionary to `export_viewshed_kml`.

### Further Considerations
1.  **Version Tagging**: Ensure `__version__` is imported from `rangeplotter` to tag files correctly.
2.  **Smart Resume**: The `param_hash` should be included in `ExtendedData` to pave the way for future robust resume logic (reading hash from file instead of sidecar JSON).
3.  **Formatting**: Use `CDATA` for the HTML description to prevent XML parsing errors.
