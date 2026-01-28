#!/bin/bash
# Migrate existing data/ and output/ directories to storage/
# Run this once after updating to the new storage structure

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

STORAGE_DIR="$PROJECT_ROOT/storage"

echo "Migrating to new storage structure..."
echo "Project root: $PROJECT_ROOT"
echo "Storage dir: $STORAGE_DIR"

# Create storage directories
mkdir -p "$STORAGE_DIR/data"
mkdir -p "$STORAGE_DIR/output"
mkdir -p "$STORAGE_DIR/config"

# Migrate data directory (prompts, media, etc.)
if [ -d "$PROJECT_ROOT/data" ]; then
    echo "Migrating data/..."

    # Copy prompts
    if [ -d "$PROJECT_ROOT/data/dialogue-prompt" ]; then
        cp -r "$PROJECT_ROOT/data/dialogue-prompt" "$STORAGE_DIR/data/"
        echo "  - Copied dialogue-prompt/"
    fi

    # Copy media
    if [ -d "$PROJECT_ROOT/data/media" ]; then
        cp -r "$PROJECT_ROOT/data/media" "$STORAGE_DIR/data/"
        echo "  - Copied media/"
    fi

    # Copy prompt files
    for file in "$PROJECT_ROOT/data"/*.md; do
        if [ -f "$file" ]; then
            cp "$file" "$STORAGE_DIR/data/"
            echo "  - Copied $(basename "$file")"
        fi
    done

    # Copy news-seeds if exists
    if [ -d "$PROJECT_ROOT/data/news-seeds" ]; then
        cp -r "$PROJECT_ROOT/data/news-seeds" "$STORAGE_DIR/data/"
        echo "  - Copied news-seeds/"
    fi
fi

# Migrate output directory (run results)
if [ -d "$PROJECT_ROOT/output" ]; then
    echo "Migrating output/..."

    # Copy all run directories
    for run_dir in "$PROJECT_ROOT/output"/run_*; do
        if [ -d "$run_dir" ]; then
            cp -r "$run_dir" "$STORAGE_DIR/output/"
            echo "  - Copied $(basename "$run_dir")"
        fi
    done
fi

# Migrate settings.json from webapp
if [ -f "$PROJECT_ROOT/webapp/settings.json" ]; then
    echo "Migrating settings.json..."
    cp "$PROJECT_ROOT/webapp/settings.json" "$STORAGE_DIR/config/"
    echo "  - Copied settings.json to config/"
fi

echo ""
echo "Migration complete!"
echo ""
echo "New storage structure:"
echo "  $STORAGE_DIR/"
echo "  ├── data/          # Prompts, media, seeds"
echo "  ├── output/        # Generated runs"
echo "  └── config/        # Settings"
echo ""
echo "You can now safely remove the old directories:"
echo "  rm -rf $PROJECT_ROOT/output"
echo "  rm -rf $PROJECT_ROOT/data/news-seeds"
echo ""
echo "Note: Keep $PROJECT_ROOT/data/ for version-controlled prompts"
