#!/usr/bin/env bash
# Download S3 data to local storage/ directory for local development.
#
# Usage:
#   ./scripts/dump-s3.sh              # Sync data only (prompts, media, settings)
#   ./scripts/dump-s3.sh --with-runs  # Also sync output runs (can be large)
#
# Requires: AWS CLI configured with credentials that can read the bucket.

set -euo pipefail

BUCKET="${S3_BUCKET:-yt-news-generator}"
REGION="${S3_REGION:-us-east-1}"
LOCAL_STORAGE="storage"

WITH_RUNS=false
for arg in "$@"; do
  case "$arg" in
    --with-runs) WITH_RUNS=true ;;
    *) echo "Unknown option: $arg"; echo "Usage: $0 [--with-runs]"; exit 1 ;;
  esac
done

echo "=== Syncing S3 data for local development ==="
echo "Bucket: s3://${BUCKET}"
echo ""

# --- Data (prompts, media, settings) ---
echo "Syncing data/ (prompts, media, settings)..."
mkdir -p "${LOCAL_STORAGE}/data"
aws s3 sync \
  "s3://${BUCKET}/data/" \
  "${LOCAL_STORAGE}/data/" \
  --region "${REGION}"

data_count=$(find "${LOCAL_STORAGE}/data" -type f | wc -l | tr -d ' ')
echo "  ${data_count} files in ${LOCAL_STORAGE}/data/"
echo ""

# --- Output runs (optional) ---
if [ "$WITH_RUNS" = true ]; then
  echo "Syncing output/ (run directories)..."
  mkdir -p "${LOCAL_STORAGE}/output"
  aws s3 sync \
    "s3://${BUCKET}/output/" \
    "${LOCAL_STORAGE}/output/" \
    --region "${REGION}"

  run_count=$(find "${LOCAL_STORAGE}/output" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
  echo "  ${run_count} runs in ${LOCAL_STORAGE}/output/"
  echo ""
fi

echo "=== Done ==="
echo "Local storage ready at: ${LOCAL_STORAGE}/"
echo "Run the app with: ./scripts/dev.sh"
