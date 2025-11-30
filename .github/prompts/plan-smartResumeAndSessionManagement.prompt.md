## Plan: Smart Resume & Session Management

This plan implements a robust "Smart Resume" system that allows `rangeplotter` to pick up where it left off by embedding state data directly into output files, deprecating the fragile sidecar JSON file.

### Steps

1.  **Enhance Hashing Logic**
    *   Update `StateManager.compute_hash` in `src/rangeplotter/utils/state.py` to explicitly include `earth_radius_model` and `max_range` (horizon distance) in the hash calculation.
    *   Ensure `sensor_height_m_agl` is explicitly part of the hash string.

2.  **Implement KML Metadata Reader**
    *   Add a new function `read_metadata_from_kml` to `src/rangeplotter/io/kml.py`.
    *   This function will parse the `<ExtendedData>` block of a KML file and return a dictionary of key-value pairs, specifically looking for "Smart Resume Hash".

3.  **Upgrade State Verification (Deprecate JSON)**
    *   Modify `StateManager.should_run` in `src/rangeplotter/utils/state.py`.
    *   **New Logic:**
        1.  Check if the output file exists.
        2.  If yes, read the "Smart Resume Hash" directly from the KML header using `read_metadata_from_kml`.
        3.  Compare with the current parameter hash.
        4.  **Match:** Return `False` (Skip).
        5.  **Mismatch/No Hash:** Return `True` (Run).
    *   **Remove** all code related to reading/writing `.rangeplotter_state.json`.
    *   **Default Output Handling:** Ensure that if no output directory is specified by the user:
        *   `viewshed`: Defaults to `working_files/viewshed` (as per existing logic), allowing resume if files exist there.
        *   `network run`: Defaults to the directory found in `last_session.json` (if valid/incomplete), otherwise creates a new timestamped folder.

4.  **Implement Session Tracking**
    *   Create a new `SessionManager` class (in `src/rangeplotter/utils/session.py`).
    *   Manage a `working_files/network/last_session.json` file containing: `{ "path": "...", "status": "incomplete|complete", "timestamp": "..." }`.

5.  **Integrate with Network Command**
    *   Update `src/rangeplotter/cli/network.py` to check `last_session.json` on startup.
    *   If an incomplete session is found (and no explicit output dir is provided), automatically resume using that output directory (logging an INFO message).
    *   Update the session status to "complete" upon successful finish.

6.  **Refine CLI Feedback**
    *   Update `src/rangeplotter/cli/main.py` (viewshed loop) to print clear INFO messages:
        *   `[INFO] Resuming: {file} (Hash match)`
        *   `[INFO] Skipping: {file} (Already exists)`
        *   `[INFO] Recalculating: {file} (Parameters changed)`

### Further Considerations
1.  **Backward Compatibility:** Old KML files without the "Smart Resume Hash" tag will simply trigger a recalculation, which is safe default behavior.
2.  **Cleanup:** The `.rangeplotter_state.json` file will no longer be created. Existing ones can be ignored or deleted by the user.