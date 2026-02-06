#!/usr/bin/env bash
# Download S3 data to local storage/ directory for local development.
#
# Usage:
#   ./scripts/dump-s3.sh           # Sync everything (data + output runs)
#   ./scripts/dump-s3.sh --no-runs # Sync data only (prompts, media, settings)
#
# Requires: AWS CLI configured with credentials that can read the bucket.

set -euo pipefail

BUCKET="${S3_BUCKET:-yt-news-generator}"
REGION="${S3_REGION:-us-east-1}"
LOCAL_STORAGE="storage"

WITH_RUNS=true
for arg in "$@"; do
  case "$arg" in
    --no-runs) WITH_RUNS=false ;;
    *) echo "Unknown option: $arg"; echo "Usage: $0 [--no-runs]"; exit 1 ;;
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

# --- Output runs (default, skip with --no-runs) ---
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
