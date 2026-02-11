#!/bin/bash
#
# Setup dependencies on VPS for YT News Generator
# Run this script ON the VPS server (not locally)
#
# Usage:
#   From local: ./scripts/vps-server.sh "bash -s" < ./scripts/setup-vps.sh
#   Or SSH in and run: bash /path/to/setup-vps.sh
#

set -e

echo "========================================"
echo "Setting up YT News Generator dependencies"
echo "========================================"

# Update and install base packages
echo ""
echo "Installing base packages..."
apt-get update
apt-get upgrade -y
apt-get install -y python3-pip python3-venv git curl ffmpeg

# Install Chrome dependencies for Remotion (headless Chrome/Chromium)
echo ""
echo "Installing Chrome dependencies for Remotion..."
apt-get install -y \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  libxrandr2 \
  libgbm1 \
  libasound2 \
  libpango-1.0-0 \
  libcairo2 \
  libnss3 \
  libnspr4 \
  libx11-xcb1 \
  fonts-liberation \
  libappindicator3-1 \
  libu2f-udev \
  libvulkan1 \
  xdg-utils

# Verify critical Chrome dependency
if ! ldconfig -p | grep -q libnss3; then
  echo "ERROR: libnss3 not found after installation!"
  exit 1
fi
echo "Chrome dependencies verified."

# Install Node.js 18
echo ""
echo "Installing Node.js 18..."
if ! command -v node &> /dev/null || [[ $(node --version | cut -d. -f1 | tr -d 'v') -lt 18 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
  apt-get purge -y nodejs libnode72 libnode-dev 2>/dev/null || true
  apt-get autoremove -y
  apt-get install -y nodejs
fi

echo "Node version: $(node --version)"
echo "npm version: $(npm --version)"

# Setup swap for instances with < 2GB RAM
echo ""
echo "Checking memory..."
TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
if [ "$TOTAL_MEM" -lt 2048 ]; then
  echo "Low memory detected (${TOTAL_MEM}MB). Setting up 2GB swap..."
  if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab
    echo "Swap added!"
  else
    swapon /swapfile 2>/dev/null || true
    echo "Swap already exists"
  fi
fi
echo "Memory: $(free -m | awk '/^Mem:/{print $2}')MB RAM, $(free -m | awk '/^Swap:/{print $2}')MB swap"

echo ""
echo "========================================"
echo "System dependencies installed!"
echo "========================================"
echo ""
echo "Now run these commands in the project directory:"
echo ""
echo "  # Install Remotion npm dependencies"
echo "  cd /path/to/yt-news-generator/remotion"
echo "  npm install"
echo ""
echo "  # Set NODE_OPTIONS for increased memory (add to .env or .bashrc)"
echo "  export NODE_OPTIONS=--max-old-space-size=2048"
echo ""
