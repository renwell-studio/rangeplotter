# v0.1.5-rc Testing Checklist

## 1. Build & Packaging
- [x] **Build Artifacts**
    - Run `rm -rf dist/ build/ && python -m build && pyinstaller rangeplotter.spec --clean --noconfirm`.
    - Verify `dist/` contains `.whl`, `.tar.gz`, and `rangeplotter` binary.

## 2. Installation & Setup
- [x] **Clean Install (Wheel)**
    - Create a fresh virtual environment (`python -m venv /tmp/test_wheel_env && source /tmp/test_wheel_env/bin/activate`).
    - Install the artifact: `pip install dist/rangeplotter-*-py3-none-any.whl`.
    - Verify command: `rangeplotter --version` (Expect: `v0.1.5-rc2`).
    - Verify help: `rangeplotter --help` (Ensure "scaffold" is gone).
- [x] **Clean Install (Binary)**
    - Run `./dist/rangeplotter --version`.
    - Verify help: `./dist/rangeplotter --help`.

## 3. Integrated Workflow (`network run`)
*Note: Perform these tests in a clean directory (e.g., `/tmp/test_run`) with `config.yaml` and `.env` present.*

- [x] **Interactive Wizard (Wheel)**
    - Run `rangeplotter network run`.
    - **Input:** Provide `examples/radars.csv` (Ensure file exists or path is correct).
    - **Output:** Accept default.
    - **Site Selection:** Choose "Select specific sites" -> Pick one (e.g., "Site Alpha").
    - **Config Review:** Select "No" (Revise) -> Change a setting (e.g., Range 20km) -> Proceed.
    - **Verify:** Runs Viewshed -> Horizon -> Detection Range successfully.
- [x] **Non-Interactive Mode (Binary)**
    - Run `./dist/rangeplotter network run --input examples/radars.csv --yes`.
    - **Verify:** Runs all sites using defaults and auto-creates an output folder.
    - **Verify Subprocess:** Ensure the binary correctly spawns subprocesses (no "No such option: -m" error).
- [x] **Filtering**
    - Run `rangeplotter network run --input examples/radars.csv --filter "Beta" --yes`.
    - Verify only "Site Beta" is processed.
- [x] **Array of Heights (Network Run)**
    - Run `rangeplotter network run --input examples/radars.csv --sensor-heights 10,50 --yes`.
    - Verify output files exist for both heights (`_sh_10m`, `_sh_50m`) in the viewshed folder.

## 4. Smart Resume & State Management
- [x] **Skip Redundant Work**
    - Run the *exact same* network command from step 3 again.
    - Verify logs: "Skipping [Site]... (already exists)".
    - Verify execution is near-instant.
- [x] **Force Re-run**
    - Run the command again with `--force`.
    - Verify it re-calculates everything.
- [x] **Parameter Change Trigger**
    - Change `atmospheric_k_factor` in `config.yaml`.
    - Run command (no force).
    - Verify it detects state change (hash mismatch) and re-calculates.

## 5. Input Flexibility
- [x] **CSV Support:** Verify `examples/radars.csv` works as input.
- [x] **KML Support:** Verify a standard KML file works as input for `network run`.
- [x] **Input Resolution:**
    - Run `rangeplotter network run` and provide just the filename `radars_sample.kml` (which is in `working_files/sensor_locations`).
    - Verify it finds the file automatically.

## 6. Sensor Altitude Features
- [x] **Array of Heights (Viewshed CLI)**
    - Run `rangeplotter viewshed -i examples/radars.csv --sensor-heights 10,50`.
    - Verify output files exist for both heights.
- [x] **KML Override**
    - Use KML with `<altitudeMode>relativeToGround</altitudeMode>` and `<altitude>45</altitude>`.
    - Run `viewshed`.
    - Verify log indicates 45m AGL used.

## 7. Offline / Lazy Auth
- [x] **Offline Check**
    - **Disconnect Internet.**
    - Run viewshed for a site with cached DEM tiles.
    - Verify success without Copernicus auth request.

## 8. Output & Visualization
- [x] **KML Clamping:** Check output KML for `<altitudeMode>clampToGround</altitudeMode>`.
- [x] **Sequential Numbering:** Verify filenames start with `01_`, `02_`.

## 9. Documentation
- [x] **Pip Guide:** Verify `docs/guide/pip_install.md` exists and instructions work.
- [x] **User Guide:** Check `docs/guide/` for accuracy.
