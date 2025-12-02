# RangePlotter Development & Release Process

This document outlines the standard workflow for developing features, managing git branches, and creating releases for RangePlotter.

## 1. Git Workflow

We follow a simple feature-branch workflow to maintain stability.

### Core Rules
*   **The `main` branch is sacred**: It should always be stable and deployable. **Never commit directly to `main`.**
*   **Use Feature Branches**: All changes (features, bugs, docs) must happen in a dedicated branch.
*   **Merge via Pull Request**: Ideally, use PRs to merge changes back to `main` to ensure code review.

### Branch Naming
*   Features: `feature/description` (e.g., `feature/add-agl-support`)
*   Bug Fixes: `fix/description` (e.g., `fix/memory-leak`)
*   Documentation: `docs/description` (e.g., `docs/update-readme`)

### Starting a New Feature
1.  **Update Main**: Ensure your local `main` branch is up to date.
    ```bash
    git checkout main
    git pull origin main
    ```
2.  **Create Branch**: Create a new branch for your feature or fix.
    ```bash
    git checkout -b feature/my-new-feature
    ```

### Development
1.  **Make Changes**: Edit files as needed.
2.  **Test**: Run the application to verify your changes.
    ```bash
    python3 src/rangeplotter/cli/main.py [command] [flags]
    ```
3.  **Update Documentation**: Edit `docs/guide/`, `README.md`, `RELEASE_PROCESS.md`, etc. as required.
4.  **Update Changlog**: Record your changes in `CHANGELOG.md`.
5.  **Commit**: Stage and commit your changes with clear messages.
    ```bash
    git add .
    git commit -m "Description of changes"
    ```

### Merging
Always use `--no-ff` (no fast-forward) merges to preserve branch topology and maintain a clear audit trail. This applies to all branch types (features, fixes, docs).

1.  **Switch to Main**:
    ```bash
    git checkout main
    ```
2.  **Merge Branch (No Fast-Forward)**:
    ```bash
    git merge --no-ff branch-name -m "Merge branch 'branch-name': Brief description"
    ```
3.  **Push**:
    ```bash
    git push origin main
    ```
4.  **Cleanup**: Delete the branch if no longer needed.
    ```bash
    git branch -d branch-name
    ```

> **Why `--no-ff`?** It creates a merge commit that groups all branch commits together, making it easy to revert entire features (`git revert -m 1 <merge>`), understand history (`git log --first-parent`), and track when changes were integrated.

---

## 2. Versioning Strategy

We follow Semantic Versioning (SemVer). Group changes together rather than releasing every commit.

*   **Patch Release (v0.1.x)**: Bug fixes, documentation updates, or minor tweaks.
*   **Minor Release (v0.x.0)**: New features or functionality (backward-compatible).
*   **Major Release (vx.0.0)**: Breaking changes or "feature complete" milestones.

## 3. Release Process

We use a **Release Candidate (RC)** workflow to ensure stability before the final release.

### Phase 1: Release Candidate (RC)

1.  **Update Changelog**:
    Add a new section `[X.Y.Z-rc1] - YYYY-MM-DD` in `CHANGELOG.md`.

2.  **Bump Version (Pre-release)**:
    *   `pyproject.toml`: `version = "X.Y.Z-rc1"`
    *   `src/rangeplotter/cli/main.py`: `__version__ = "X.Y.Z-rc1"`

3.  **Tag & Push**:
    ```bash
    git commit -am "Bump version to vX.Y.Z-rc1"
    git tag -a vX.Y.Z-rc1 -m "Release Candidate vX.Y.Z-rc1"
    git push origin vX.Y.Z-rc1
    ```

4.  **Verify CI/CD**:
    GitHub Actions will automatically:
    *   Build the **Linux Binary** (zip).
    *   Build the **Python Wheel** (.whl) and Source Dist (.tar.gz).
    *   Create a **Pre-release** on GitHub with these assets.

5.  **Test**:
    *   Download the artifacts.
    *   Test the binary upgrade using `install_or_upgrade.sh`.
    *   Test the wheel installation: `pip install rangeplotter-X.Y.Zrc1-py3-none-any.whl`.

### Phase 2: Final Release

Once the RC is verified:

1.  **Finalize Changelog**:
    Rename `[X.Y.Z-rc1]` to `[X.Y.Z]`.

2.  **Bump Version (Final)**:
    *   `pyproject.toml`: `version = "X.Y.Z"`
    *   `src/rangeplotter/cli/main.py`: `__version__ = "X.Y.Z"`

3.  **Tag & Push**:
    ```bash
    git commit -am "Bump version to vX.Y.Z"
    git tag -a vX.Y.Z -m "Release vX.Y.Z"
    git push origin vX.Y.Z
    ```

4.  **Publish**:
    GitHub Actions will build the final artifacts and create a standard (non-pre-release) GitHub Release.

---

## Appendix: Manual Build & Release

If the automated pipeline fails or you need to build locally:

### 1. Build Binary (PyInstaller)
```bash
pyinstaller rangeplotter.spec --clean --noconfirm
```

### 2. Build Wheel (Python Build)
```bash
python3 -m build
# Artifacts will be in dist/ (e.g., rangeplotter-X.Y.Z-py3-none-any.whl)
```

### 3. Create Release Archive (Binary)
```bash
VERSION="vX.Y.Z"
RELEASE_DIR="release/rangeplotter_${VERSION}_linux"

# Clean up
rm -rf "$RELEASE_DIR"

# Create directories
mkdir -p "$RELEASE_DIR/config"
mkdir -p "$RELEASE_DIR/working_files/sensor_locations"
mkdir -p "$RELEASE_DIR/data_cache"

# Copy Files
cp dist/rangeplotter "$RELEASE_DIR/"
cp config/config.yaml "$RELEASE_DIR/config/"
cp README.md LICENSE "$RELEASE_DIR/"
cp scripts/install_or_upgrade.sh "$RELEASE_DIR/"
cp example.env "$RELEASE_DIR/"
cp "working_files/sensor_locations/radars_sample.kml" "$RELEASE_DIR/working_files/sensor_locations/"

# Zip
cd release
zip -r "rangeplotter_${VERSION}_linux.zip" "rangeplotter_${VERSION}_linux"
cd ..
```

### 3. Publish
```bash
gh release create ${VERSION} release/rangeplotter_${VERSION}_linux.zip --repo renwell-studio/rangeplotter --title "${VERSION}" --generate-notes
```

---

## Appendix: Pre-Release Local Testing

Before pushing a release tag, it is critical to verify that the packaged artifacts (Wheel and Binary) function correctly. This process ensures that packaging-specific issues (e.g., missing dependencies, subprocess errors in frozen binaries) are caught early.

**Goal:** Test the release candidate in a completely isolated environment without affecting your development setup or existing system installations.

### 1. Build Artifacts Locally
Generate the artifacts that CI/CD would normally build.

```bash
# Install build tools if needed
pip install build pyinstaller

# Clean previous builds
rm -rf dist/ build/

# Build Python Wheel
python3 -m build

# Build Linux Binary
pyinstaller rangeplotter.spec --clean --noconfirm
```

### 2. Test the Python Wheel (Pip Install)
Use a temporary virtual environment to simulate a fresh user installation.

```bash
# 1. Create a throwaway environment in /tmp (outside your project)
python3 -m venv /tmp/test_wheel_env
source /tmp/test_wheel_env/bin/activate

# 2. Install the newly built wheel
# (Adjust filename to match version)
pip install dist/rangeplotter-*-py3-none-any.whl

# 3. Create a clean workspace for data
mkdir -p /tmp/test_wheel_workspace
cd /tmp/test_wheel_workspace

# 4. Run Verification
# Verify version matches
rangeplotter --version

# Verify help text
rangeplotter --help

# Verify complex commands (e.g., network run wizard)
# Note: You may need to copy a config.yaml and .env here if the tool expects them
rangeplotter network run --help

# 5. Cleanup
deactivate
rm -rf /tmp/test_wheel_env
rm -rf /tmp/test_wheel_workspace
```

### 3. Test the Linux Binary (Standalone)
Verify the frozen binary works, especially for commands that spawn subprocesses (like `network run`).

```bash
# 1. Create a clean workspace
mkdir -p /tmp/test_binary_workspace
cd /tmp/test_binary_workspace

# 2. Run the binary directly from your dist folder
# (Assuming you are still in the project root in another terminal, or copy it here)
PROJECT_DIST=~/Documents/Computing/rangeplotter/dist

# Verify Version
$PROJECT_DIST/rangeplotter --version

# Verify Subprocess Execution
# This is critical for PyInstaller builds to ensure sys.executable is handled correctly
$PROJECT_DIST/rangeplotter network run --help

# 3. Cleanup
rm -rf /tmp/test_binary_workspace
```

### 4. Test the Install Script
Verify the upgrade logic without overwriting your actual installation.

```bash
# 1. Create a fake "existing install"
mkdir -p /tmp/fake_install_location
touch /tmp/fake_install_location/rangeplotter  # Dummy existing binary

# 2. Create a fake release package folder
mkdir -p /tmp/fake_release_pkg
cp dist/rangeplotter /tmp/fake_release_pkg/
cp scripts/install_or_upgrade.sh /tmp/fake_release_pkg/

# 3. Run the script
cd /tmp/fake_release_pkg
chmod +x install_or_upgrade.sh
./install_or_upgrade.sh
# -> When prompted, enter: /tmp/fake_install_location

# 4. Verify
# Check if /tmp/fake_install_location/rangeplotter was updated
ls -l /tmp/fake_install_location/rangeplotter

# 5. Cleanup
rm -rf /tmp/fake_install_location
rm -rf /tmp/fake_release_pkg
```

---

## Appendix: Testing Release Artifacts (Post-Release)

To test artifacts *downloaded* from GitHub (after release) without breaking your main environment:

