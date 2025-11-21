# RangePlotter

Prototype radar line-of-sight terrain visibility utility.

## Status
Active development. Core LOS algorithms and DEM integration implemented.

## Quick Start
```bash
# Calculate theoretical horizon (no terrain)
python -m rangeplotter.cli.main horizon --input working_files/input/radars_sample.kml

# Calculate terrain-aware viewshed
python -m rangeplotter.cli.main viewshed --input working_files/input/radars_sample.kml
```

## Workflow

### 1. Viewshed Calculation (`viewshed`)
The `viewshed` command performs the computationally intensive work of calculating geometric visibility. It determines the line-of-sight from a static sensor location to a target at a specific altitude (or set of altitudes), accounting for:
- Earth curvature
- Atmospheric refraction (k-factor)
- Terrain obstructions (using Copernicus GLO-30 DEM data)

**Output:**
This command generates "raw" viewshed polygons. Each output is a standalone KML file representing the visibility for **one sensor** at **one target altitude**.
- **Location:** `working_files/viewshed/` (default)
- **Naming:** `viewshed-[sensor_name]-tgt_alt_[altitude]m.kml`

These files are intended to be the foundational building blocks for further analysis or visualization. They are saved individually to allow for efficient caching and reprocessing without re-running the expensive visibility calculation.

### 2. Detection Range Clipping (`detection-range`)
The `detection-range` command takes the raw viewsheds and clips them to a maximum instrumented range. It can also combine multiple sensors into a single network coverage map (union).

**Output:**
- **Location:** `working_files/detection_range/` (default)
- **Naming:** `visibility-[name]-tgt_alt_[altitude]m-det_rng_[range]km.kml`

## Usage

The CLI supports several commands. Use `--help` for detailed information on any command.

### Common Flags
- `--config`: Path to config YAML (default: `config/config.yaml`)
- `--input` / `-i`: Path to radar KML file or directory containing KMLs (optional, defaults to `working_files/input`)
- `--output` / `-o`: Override output directory (optional)
- `--verbose` / `-v`: Verbosity level (use `-v` for Info, `-vv` for Debug)

### Commands

#### `horizon`
Calculate the theoretical maximum geometric horizon (range rings) for each sensor location based on Earth curvature and atmospheric refraction, but without terrain awareness.
```bash
python -m rangeplotter.cli.main horizon
```

#### `viewshed`
Calculate the actual terrain-aware visibility for each sensor location using Copernicus GLO-30 DEM data.
```bash
python -m rangeplotter.cli.main viewshed
```

#### `detection-range`
Clip viewsheds to maximum detection ranges and optionally union them.
```bash
# Process all viewsheds in the default output directory
python -m rangeplotter.cli.main detection-range --input working_files/viewshed/*.kml

# Process specific files with a custom range
python -m rangeplotter.cli.main detection-range --input "working_files/viewshed/MyRadar*.kml" --range 150
```

#### `prepare-dem`
Pre-download DEM tiles for a given area to populate the cache.
```bash
python -m rangeplotter.cli.main prepare-dem
```

#### `debug-auth-dem`
Test authentication and DEM download capabilities.
```bash
python -m rangeplotter.cli.main debug-auth-dem
```

## Environment Setup
**CRITICAL:** Always ensure you are running inside the project's virtual environment to avoid dependency conflicts.

1. Create and activate the virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Verify you are using the correct Python (should output `.../visibility/.venv/bin/python`):
```bash
which python
```

3. Install dependencies:
```bash
pip install --upgrade pip
pip install -e .
```

If editable install fails ensure `pyproject.toml` dependencies are correctly formatted and run again.

## Credentials
Copernicus Data Space Ecosystem uses an OpenID Connect / Keycloak endpoint with a **public client id** (`cdse-public`).
Token acquisition for downloads is performed via the Resource Owner Password Credentials grant (`grant_type=password`) OR subsequent `refresh_token` grants. There is **no client secret** for the public client.

Set credentials via environment (avoid putting them in YAML config):
```bash
export COPERNICUS_USERNAME="your_username"
export COPERNICUS_PASSWORD="your_password"
# Optional after first token retrieval – store only refresh token (preferred):
export COPERNICUS_REFRESH_TOKEN="your_refresh_token"
```
`COPERNICUS_CLIENT_ID` can override the default if needed (defaults to `cdse-public`).

Alternatively use a `.env` file (auto-loaded if present):
```bash
cp .env.example .env
chmod 600 .env
edit .env  # add your values
```
Keep `.env` out of version control (already gitignored).

### Recommended Storage Patterns

Development (local):
- Use `.env` with 600 permissions or shell `export` in a dedicated terminal session.
- After initial token fetch, remove password from `.env` and keep only `COPERNICUS_REFRESH_TOKEN`.
- Avoid putting secrets in your shell history (prefix with space in bash to skip history).

Production (systemd service):
- Create `/etc/visibility/credentials.env` owned by root:visibility with `chmod 640`.
- Reference in unit file: `EnvironmentFile=/etc/visibility/credentials.env`.
- Populate minimally (prefer refresh token only):
	```
	COPERNICUS_REFRESH_TOKEN=xxxxx
	COPERNICUS_CLIENT_ID=cdse-public
	```

Docker:
- Use Docker secrets or pass via environment at runtime (`--env-file env.prod`).
- Never bake credentials into the image.

Kubernetes:
- Store in Secret manifest; mount as env vars.
- Optionally use sealed-secrets or external secret store (e.g. Vault).

CI/CD:
- Inject as pipeline protected variables; never commit.
- Pipeline step runs `echo "$COPERNICUS_CLIENT_ID" >> $WORKSPACE/.env` only if needed.

Cloud Secret Managers:
- For scaling, retrieve at startup (e.g. AWS Secrets Manager, GCP Secret Manager) then set env vars before process spawn.
- Consider secret rotation pipeline that updates only the refresh token; running services refresh automatically.

### Rotation & Revocation
- Rotate regularly; keep previous credentials briefly to avoid downtime.
- On rotation: update secret store, restart service, verify token acquisition logs.
- If password compromised, revoke refresh token and change password; deploy new refresh token.

### Validation
Obtain an access token (password grant) and extract the access_token field:
```bash
curl -s -X POST \
	-d "grant_type=password" \
	-d "client_id=${COPERNICUS_CLIENT_ID:-cdse-public}" \
	-d "username=$COPERNICUS_USERNAME" \
	-d "password=$COPERNICUS_PASSWORD" \
	https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token | jq '.access_token != null'
```

Refresh using an existing refresh token (no password needed):
```bash
curl -s -X POST \
	-d "grant_type=refresh_token" \
	-d "client_id=${COPERNICUS_CLIENT_ID:-cdse-public}" \
	-d "refresh_token=$COPERNICUS_REFRESH_TOKEN" \
	https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token | jq '.access_token != null'
```

Never commit passwords; prefer storing only the refresh token in production.

### One-Time Refresh Token Extraction
Use the helper command to obtain a refresh token without exposing the access token:
```bash
python -m rangeplotter.cli.main extract-refresh-token \
	--username "$COPERNICUS_USERNAME" \
	--password   # will prompt hidden input
```
Print an .env snippet directly:
```bash
python -m rangeplotter.cli.main extract-refresh-token --username "$COPERNICUS_USERNAME" --password --print-env
```
Append to a specific file (creates if missing):
```bash
python -m rangeplotter.cli.main extract-refresh-token --username "$COPERNICUS_USERNAME" --password --env-output .env
chmod 600 .env
```
After success: remove `COPERNICUS_PASSWORD` and `COPERNICUS_USERNAME` from your environment and `.env`.

Example secure `.env` after onboarding:
```
COPERNICUS_REFRESH_TOKEN=eyJhbGciOiJSUzI1NiIsInR5cCI6...
COPERNICUS_CLIENT_ID=cdse-public
COPERNICUS_DATASET_IDENTIFIER=COP-DEM_GLO-30
```


## Troubleshooting
- Missing `yaml`: install `PyYAML` (`pip install PyYAML`).
- Geodesic failure: ensure `pyproj` installed; reinstall with `pip install --force-reinstall pyproj`.
- Slow performance: reduce altitudes or disable multiscale in config.


## Features (Planned)
- Ellipsoidal Earth model with atmospheric k-factor.
- Multiscale terrain LOS (Copernicus GLO-30, EGM2008).
- KML export of range rings & LOS polygons.
- Union visibility per altitude.

See `docs/ROADMAP.md` for detailed plan.
