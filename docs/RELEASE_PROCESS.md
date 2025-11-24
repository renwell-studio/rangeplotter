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

## 2. Versioning Strategy

We follow Semantic Versioning (SemVer). Group changes together rather than releasing every commit.

*   **Patch Release (v0.1.x)**: Bug fixes, documentation updates, or minor tweaks.
*   **Minor Release (v0.x.0)**: New features or functionality (backward-compatible).
*   **Major Release (vx.0.0)**: Breaking changes or "feature complete" milestones.

## 3. Release Process

When ready to release a new version (e.g., `v0.1.0`):

### 1. Update Changelog
Review `CHANGELOG.md`. Move the content from `[Unreleased]` to a new section `[X.Y.Z] - YYYY-MM-DD`. Ensure all notable changes are captured.

### 2. Update Version Number
Update the version string in the following files:
*   `pyproject.toml`: `version = "X.Y.Z"`
*   `src/rangeplotter/cli/main.py`: `__version__ = "X.Y.Z"`

### 3. Commit Version Bump
```bash
git add CHANGELOG.md pyproject.toml src/rangeplotter/cli/main.py
git commit -m "Bump version to vX.Y.Z"
git push origin main
```

### 4. Tag the Release
Create an annotated git tag and push it to GitHub.
```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

### 5. Build & Release (Automated)

The project uses GitHub Actions to automatically build, package, and publish the release when a new tag is pushed.

1.  **Push the Tag**:
    (As done in Step 4)
    ```bash
    git push origin vX.Y.Z
    ```

2.  **Monitor Action**:
    *   Go to the **Actions** tab in the GitHub repository.
    *   Watch the **Build and Release** workflow.

3.  **Verify Release**:
    *   Once the workflow completes, go to the **Releases** page.
    *   Verify that `vX.Y.Z` exists and contains the `rangeplotter_vX.Y.Z_linux.zip` asset.

---

## Appendix: Manual Build & Release

If the automated pipeline fails or you need to build locally:

### 1. Build Binary
```bash
pyinstaller rangeplotter.spec --clean --noconfirm
```

### 2. Create Archive
```bash
VERSION="vX.Y.Z"
RELEASE_DIR="release/rangeplotter_${VERSION}_linux"

# Clean up
rm -rf "$RELEASE_DIR"

# Create directories
mkdir -p "$RELEASE_DIR/config"
mkdir -p "$RELEASE_DIR/working_files/input"
mkdir -p "$RELEASE_DIR/data_cache"

# Copy Files
cp dist/rangeplotter "$RELEASE_DIR/"
cp config/config.yaml "$RELEASE_DIR/config/"
cp README.md LICENSE "$RELEASE_DIR/"
cp example.env "$RELEASE_DIR/"
cp "working_files/input/radars_sample.kml" "$RELEASE_DIR/working_files/input/"

# Zip
cd release
zip -r "rangeplotter_${VERSION}_linux.zip" "rangeplotter_${VERSION}_linux"
cd ..
```

### 3. Publish
```bash
gh release create ${VERSION} release/rangeplotter_${VERSION}_linux.zip --repo renwell-studio/rangeplotter --title "${VERSION}" --generate-notes
```

