# Smart Resume & Session Management

RangePlotter includes a robust "Smart Resume" feature designed to save time by avoiding unnecessary recalculations. This system allows you to interrupt a long-running batch process and resume it later, or re-run a batch with slightly modified settings where only the affected outputs are recalculated.

## How It Works

### Embedded State
Instead of relying on a fragile external "state file", RangePlotter embeds a cryptographic hash of the calculation parameters directly into the output KML files (in the `<ExtendedData>` section).

This hash includes:
*   Sensor location (Lat/Lon)
*   Sensor effective height (Ground Elevation + Tower Height)
*   Target altitude
*   Atmospheric refraction factor (k-factor)
*   Earth radius model
*   Maximum horizon range

### Resume Logic
When you run a viewshed calculation (via `viewshed` or `network run`), the system checks if the output file already exists.

1.  **File Exists**: It reads the embedded hash from the KML file.
2.  **Hash Match**: If the embedded hash matches the current configuration, the calculation is **skipped**.
3.  **Hash Mismatch**: If the parameters have changed (e.g., you changed the refraction factor or corrected the sensor height), the file is **recalculated** and overwritten.
4.  **File Missing**: The calculation proceeds as normal.

### Session Management
The `network run` command automatically tracks your last session. If you interrupt a run or it crashes, simply running `network run` again will detect the incomplete session and offer to resume it using the same input and output directories.

## Testing Strategy

To ensure the robustness of the Smart Resume feature, the following test scenarios should be verified:

### 1. Basic Resume
*   **Action**: Start a large batch run, interrupt it (Ctrl+C) halfway through. Run the command again.
*   **Expected**: The system should skip the already completed files (showing `[INFO] Skipping...`) and pick up exactly where it left off.

### 2. Parameter Change (Recalculation)
*   **Action**: Complete a run. Change a physics parameter (e.g., `atmospheric_k_factor` in `config.yaml`) or the sensor height. Run the command again.
*   **Expected**: The system should detect the parameter change (Hash Mismatch) and recalculate all affected files, showing `[INFO] Recalculating...`.

### 3. Force Overwrite
*   **Action**: Complete a run. Run the command again with the `--force` flag.
*   **Expected**: All files should be recalculated regardless of state.

### 4. Session Recovery
*   **Action**: Start a `network run` without specifying arguments. Interrupt it. Run `network run` again.
*   **Expected**: The CLI should prompt: "Found previous session... Resume this session?". Answering "Yes" should restore the input/output paths and continue.

### 5. Corrupt/Legacy Files
*   **Action**: Place a dummy KML file or an old version KML (without hash) in the output folder. Run the command.
*   **Expected**: The system should fail to find a matching hash and treat it as a "Mismatch", triggering a recalculation to ensure correctness.
