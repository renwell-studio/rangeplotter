#!/bin/bash
set -e

# RangePlotter Install/Upgrade Script
# -----------------------------------
# This script installs or upgrades the RangePlotter binary while preserving
# your existing configuration and data.

echo "========================================"
echo "   RangePlotter Installer / Upgrader    "
echo "========================================"

# Detect current directory (where the script is running from)
# Use a more portable way to find the script directory
SOURCE_DIR="$( cd "$( dirname "$0" )" && pwd )"
BINARY_NAME="rangeplotter"

echo "Source directory: $SOURCE_DIR"

# Safety Check: We explicitly do NOT touch any user backup files (*.bac, *.backup)
# throughout this process.

# Default install location
DEFAULT_INSTALL_DIR="$HOME/rangeplotter"

# Use -e for readline support (tab completion for paths)
read -e -p "Enter installation directory [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}

echo "Installing to: $INSTALL_DIR"

# Create directory if it doesn't exist
if [ ! -d "$INSTALL_DIR" ]; then
    echo "Creating directory..."
    mkdir -p "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/config"
    mkdir -p "$INSTALL_DIR/working_files"
    mkdir -p "$INSTALL_DIR/data_cache"
fi

# 1. Copy Binary (Always overwrite)
echo "Copying binary..."
if [ -f "$SOURCE_DIR/$BINARY_NAME" ]; then
    cp -f "$SOURCE_DIR/$BINARY_NAME" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/$BINARY_NAME"
else
    echo "Warning: Binary '$BINARY_NAME' not found in source directory. Skipping binary copy."
fi

# 2. Handle Config
CONFIG_FILE="$INSTALL_DIR/config/config.yaml"

if [ -f "$CONFIG_FILE" ]; then
    echo "Existing config found. Checking for updates..."
    
    # Check for missing keys and append them if necessary
    # Example: union_outputs (Added in 0.1.6)
    if ! grep -q "union_outputs:" "$CONFIG_FILE"; then
        echo "Adding missing 'union_outputs' setting..."
        cat >> "$CONFIG_FILE" <<EOL

# Union Outputs (Added in 0.1.6)
# If true, detection ranges are merged into a single coverage map.
# If false, individual files are generated for each sensor.
union_outputs: true
EOL
    fi

    # Example: kml_export_altitude_mode (Added in 0.1.5)
    if ! grep -q "kml_export_altitude_mode:" "$CONFIG_FILE"; then
        echo "Adding missing 'kml_export_altitude_mode' setting..."
        cat >> "$CONFIG_FILE" <<EOL

# KML Export Altitude Mode (Added in 0.1.5)
# "clamped" (clampToGround) or "absolute" (absolute)
kml_export_altitude_mode: "clamped"
EOL
    fi

    echo "A default config has been saved as config.yaml.new for reference."
    cp "$SOURCE_DIR/config/config.yaml" "$INSTALL_DIR/config/config.yaml.new"
else
    echo "Installing default config..."
    mkdir -p "$INSTALL_DIR/config"
    cp "$SOURCE_DIR/config/config.yaml" "$CONFIG_FILE"
    
    # Auto-Configuration for First Run
    echo "Auto-configuring performance settings..."
    
    # Detect CPU cores
    if command -v nproc >/dev/null 2>&1; then
        TOTAL_CORES=$(nproc)
        # Strategy: Reserve 2 cores, or use 80% of cores, whichever is more conservative (min 1)
        
        # Option A: Reserve 2
        WORKERS_RESERVE=$((TOTAL_CORES - 2))
        
        # Option B: 80%
        WORKERS_PERCENT=$((TOTAL_CORES * 80 / 100))
        
        # Pick the smaller of the two, but at least 1
        if [ $WORKERS_RESERVE -lt $WORKERS_PERCENT ]; then
            MAX_WORKERS=$WORKERS_RESERVE
        else
            MAX_WORKERS=$WORKERS_PERCENT
        fi
        
        if [ $MAX_WORKERS -lt 1 ]; then
            MAX_WORKERS=1
        fi
        
        echo "Detected $TOTAL_CORES cores. Setting max_workers to $MAX_WORKERS."
        
        # Update config.yaml using sed
        # We look for 'max_workers: 8' (default) and replace it
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS sed requires empty string for -i
            sed -i '' "s/max_workers: [0-9]*/max_workers: $MAX_WORKERS/" "$CONFIG_FILE"
        else
            sed -i "s/max_workers: [0-9]*/max_workers: $MAX_WORKERS/" "$CONFIG_FILE"
        fi
    else
        echo "Could not detect CPU cores. Using default settings."
    fi
fi

# 2.5. Migration: input -> sensor_locations
# Move directory if needed
if [ -d "$INSTALL_DIR/working_files/input" ] && [ ! -d "$INSTALL_DIR/working_files/sensor_locations" ]; then
    echo "Migrating legacy 'input' directory to 'sensor_locations'..."
    mv "$INSTALL_DIR/working_files/input" "$INSTALL_DIR/working_files/sensor_locations"
fi

# Update config if it points to the old location (regardless of whether we moved the dir)
if [ -f "$CONFIG_FILE" ]; then
    if grep -q "working_files/input" "$CONFIG_FILE"; then
        echo "Updating config.yaml to reflect directory rename..."
        cp "$CONFIG_FILE" "$CONFIG_FILE.bak_migration"
        
        # Replace variations of the setting
        if [[ "$OSTYPE" == "darwin"* ]]; then
             sed -i '' 's|input_dir: "working_files/input"|input_dir: "working_files/sensor_locations"|g' "$CONFIG_FILE"
             sed -i '' "s|input_dir: 'working_files/input'|input_dir: 'working_files/sensor_locations'|g" "$CONFIG_FILE"
             sed -i '' 's|input_dir: working_files/input|input_dir: "working_files/sensor_locations"|g' "$CONFIG_FILE"
        else
             sed -i 's|input_dir: "working_files/input"|input_dir: "working_files/sensor_locations"|g' "$CONFIG_FILE"
             sed -i "s|input_dir: 'working_files/input'|input_dir: 'working_files/sensor_locations'|g" "$CONFIG_FILE"
             sed -i 's|input_dir: working_files/input|input_dir: "working_files/sensor_locations"|g' "$CONFIG_FILE"
        fi
    fi
fi

# 3. Handle Example Env
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ -f "$SOURCE_DIR/example.env" ]; then
        echo "Copying example.env to .env (please edit it with your credentials)..."
        cp "$SOURCE_DIR/example.env" "$INSTALL_DIR/.env"
    fi
else
    echo "Existing .env found. Preserving it."
fi

# 4. Copy Documentation
cp "$SOURCE_DIR/README.md" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SOURCE_DIR/LICENSE" "$INSTALL_DIR/" 2>/dev/null || true

# 5. Copy Sample Data (Overwrite existing samples to ensure they are up to date)
# We only overwrite files in sensor_locations that match the names of our samples.
# We do NOT delete user files.
echo "Updating sample data..."
mkdir -p "$INSTALL_DIR/working_files/sensor_locations"
if [ -d "$SOURCE_DIR/working_files/sensor_locations" ]; then
    cp -r "$SOURCE_DIR/working_files/sensor_locations/"* "$INSTALL_DIR/working_files/sensor_locations/" 2>/dev/null || true
fi

echo ""
echo "========================================"
echo "Success! RangePlotter is installed."
echo "Location: $INSTALL_DIR/$BINARY_NAME"
