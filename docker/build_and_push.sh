#!/bin/bash
# Build and push Chatterbox TTS Docker image to Docker Hub
#
# Prerequisites:
#   1. Docker installed and running
#   2. Docker Hub account: https://hub.docker.com
#   3. Login: docker login
#
# Usage:
#   ./docker/build_and_push.sh <dockerhub_username>
#
# Example:
#   ./docker/build_and_push.sh myusername
#   # Creates: myusername/chatterbox-tts:latest

set -e

# Check arguments
if [ -z "$1" ]; then
    echo "Usage: $0 <dockerhub_username>"
    echo "Example: $0 myusername"
    exit 1
fi

DOCKER_USER="$1"
IMAGE_NAME="chatterbox-tts"
TAG="latest"
FULL_IMAGE="${DOCKER_USER}/${IMAGE_NAME}:${TAG}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "Building Chatterbox TTS Docker Image"
echo "============================================"
echo "Image: ${FULL_IMAGE}"
echo ""

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker first."
    exit 1
fi

# Check if logged in to Docker Hub
if ! docker info 2>/dev/null | grep -q "Username"; then
    echo "Not logged in to Docker Hub. Running 'docker login'..."
    docker login
fi

# Build the image
echo ""
echo "Building image (this may take 5-10 minutes on first build)..."
docker build -t "${FULL_IMAGE}" -f "${SCRIPT_DIR}/Dockerfile" "${SCRIPT_DIR}"

echo ""
echo "============================================"
echo "Pushing to Docker Hub"
echo "============================================"
docker push "${FULL_IMAGE}"

echo ""
echo "============================================"
echo "Done!"
echo "============================================"
echo ""
echo "Image pushed: ${FULL_IMAGE}"
echo ""
echo "To use in RunPod, update RUNPOD_IMAGE in generate_audio_runpod.py:"
echo "  RUNPOD_IMAGE = \"${FULL_IMAGE}\""
echo ""
echo "Or set environment variable:"
echo "  export RUNPOD_IMAGE=\"${FULL_IMAGE}\""
