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
SOURCE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BINARY_NAME="rangeplotter"

echo "Source directory: $SOURCE_DIR"

# Safety Check: We explicitly do NOT touch any user backup files (*.bac, *.backup)
# throughout this process.

# Default install location
DEFAULT_INSTALL_DIR="$HOME/rangeplotter"

read -p "Enter installation directory [$DEFAULT_INSTALL_DIR]: " INSTALL_DIR
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
cp "$SOURCE_DIR/$BINARY_NAME" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/$BINARY_NAME"

# 2. Handle Config
if [ -f "$INSTALL_DIR/config/config.yaml" ]; then
    echo "Existing config found. Preserving it."
    echo "A default config has been saved as config.yaml.new for reference."
    cp "$SOURCE_DIR/config/config.yaml" "$INSTALL_DIR/config/config.yaml.new"
else
    echo "Installing default config..."
    mkdir -p "$INSTALL_DIR/config"
    cp "$SOURCE_DIR/config/config.yaml" "$INSTALL_DIR/config/config.yaml"
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

# 5. Copy Sample Data (if input dir is empty)
if [ -z "$(ls -A "$INSTALL_DIR/working_files/sensor_locations" 2>/dev/null)" ]; then
    echo "Copying sample data..."
    mkdir -p "$INSTALL_DIR/working_files/sensor_locations"
    cp -r "$SOURCE_DIR/working_files/sensor_locations/"* "$INSTALL_DIR/working_files/sensor_locations/" 2>/dev/null || true
fi

echo ""
echo "========================================"
echo "Success! RangePlotter is installed."
echo "Location: $INSTALL_DIR/$BINARY_NAME"
echo ""
echo "To run:"
echo "  cd $INSTALL_DIR"
echo "  ./$BINARY_NAME --help"
echo "========================================"
