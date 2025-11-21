# RangePlotter Development & Release Process

This document outlines the standard workflow for developing features, managing git branches, and creating releases for RangePlotter.

## 1. Git Workflow

We follow a simple feature-branch workflow.

### Starting a New Feature
1.  **Update Main**: Ensure your local `main` branch is up to date.
    ```bash
    git checkout main
    git pull origin main
    ```
2.  **Create Branch**: Create a new branch for your feature or fix.
    ```bash
    git checkout -b feature-name
    ```

### Development
1.  **Make Changes**: Edit files as needed.
2.  **Test**: Run the application to verify your changes.
    ```bash
    python3 src/rangeplotter/cli/main.py [command] [flags]
    ```
3.  **Commit**: Stage and commit your changes with clear messages.
    ```bash
    git add .
    git commit -m "Description of changes"
    ```

### Merging
1.  **Switch to Main**:
    ```bash
    git checkout main
    ```
2.  **Merge Feature**:
    ```bash
    git merge feature-name
    ```
3.  **Push**:
    ```bash
    git push origin main
    ```
4.  **Cleanup**: Delete the feature branch if no longer needed.
    ```bash
    git branch -d feature-name
    ```

---

## 2. Release Process

When ready to release a new version (e.g., `v0.1.0`):

### 1. Update Version Number
Update the version string in the following files:
*   `pyproject.toml`: `version = "X.Y.Z"`
*   `src/rangeplotter/cli/main.py`: `__version__ = "X.Y.Z"`

### 2. Commit Version Bump
```bash
git add pyproject.toml src/rangeplotter/cli/main.py
git commit -m "Bump version to vX.Y.Z"
git push origin main
```

### 3. Tag the Release
Create an annotated git tag and push it to GitHub.
```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

### 4. Build the Binary
We use **PyInstaller** to build the standalone binary. Do not use `python -m build` (that creates a Python wheel/sdist).

1.  **Clean & Build**:
    ```bash
    pyinstaller rangeplotter.spec --clean --noconfirm
    ```
2.  **Verify**:
    Check the `dist/` directory for the new binary.
    ```bash
    ls -l dist/rangeplotter
    ```
3.  **Test Binary**:
    Run the binary directly to ensure it works.
    ```bash
    ./dist/rangeplotter --version
    ```

### 5. Create Release Archive
We distribute the application as a portable ZIP archive containing the binary, configuration, and necessary folders.

1.  **Create Directory Structure**:
    ```bash
    VERSION="vX.Y.Z"
    mkdir -p release/rangeplotter_${VERSION}_linux/config
    mkdir -p release/rangeplotter_${VERSION}_linux/working_files/input
    ```

2.  **Copy Files**:
    ```bash
    # Binary
    cp dist/rangeplotter release/rangeplotter_${VERSION}_linux/
    
    # Config (Default)
    cp config/config.yaml release/rangeplotter_${VERSION}_linux/config/
    
    # Documentation
    cp README.md LICENSE release/rangeplotter_${VERSION}_linux/
    
    # Sample Data (Optional)
    cp working_files/input/radars_sample.kml release/rangeplotter_${VERSION}_linux/working_files/input/
    ```

3.  **Create Zip**:
    ```bash
    cd release
    zip -r rangeplotter_${VERSION}_linux.zip rangeplotter_${VERSION}_linux/
    cd ..
    ```

### 6. Publish
Use the GitHub CLI to create the release and upload the archive:
```bash
gh release create ${VERSION} release/rangeplotter_${VERSION}_linux.zip --title "${VERSION}" --generate-notes
```
Alternatively, upload `release/rangeplotter_${VERSION}_linux.zip` manually via the GitHub website.

