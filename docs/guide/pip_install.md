# Getting Started with Pip

This guide explains how to install and run RangePlotter using the Python package manager (`pip`). This method is recommended for developers, cross-platform users (Windows/Mac), or anyone who prefers managing tools via Python.

## Prerequisites

*   **Python 3.11 or newer**: Check with `python --version`.
*   **Pip**: Usually included with Python.

## 1. Installation

We recommend installing RangePlotter in a virtual environment to keep your system clean.

### Option A: Install from PyPI (Future)
*Once released, you can install directly:*
```bash
pip install rangeplotter
```

### Option B: Install from Wheel (.whl)
If you have downloaded a release artifact (e.g., `rangeplotter-0.1.5rc1-py3-none-any.whl`):

1.  Create a folder for your project (optional but recommended):
    ```bash
    mkdir my_radar_project
    cd my_radar_project
    ```

2.  Create a virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  Install the wheel:
    ```bash
    pip install /path/to/downloaded/rangeplotter-0.1.5rc1-py3-none-any.whl
    ```

## 2. Setup

Unlike the standalone binary, the pip package does not come with configuration files pre-installed in your folder. You need to set them up.

1.  **Download Default Config**:
    Get the `config.yaml` and `.env` template from the repository.
    ```bash
    mkdir config
    # Download config.yaml
    curl -o config/config.yaml https://raw.githubusercontent.com/renwell-studio/rangeplotter/main/config/config.yaml
    
    # Download .env template
    curl -o .env https://raw.githubusercontent.com/renwell-studio/rangeplotter/main/example.env
    ```

2.  **Configure Credentials**:
    Open `.env` in a text editor and add your Copernicus Data Space Ecosystem credentials.
    ```env
    COPERNICUS_USERNAME=your_email@example.com
    COPERNICUS_PASSWORD=your_password
    ```

## 3. Running

Once installed and configured, you can run RangePlotter using the command `rangeplotter`.

```bash
# Check version
rangeplotter --version

# Run the network wizard
rangeplotter network run
```

### Troubleshooting

**"Command not found: rangeplotter"**
*   Ensure your virtual environment is activated (`source venv/bin/activate`).
*   Alternatively, run it as a module: `python -m rangeplotter ...`

**"Authentication Failed"**
*   Double-check your `.env` file is in the current directory.
*   Ensure you have registered for a free account at [dataspace.copernicus.eu](https://dataspace.copernicus.eu/).
