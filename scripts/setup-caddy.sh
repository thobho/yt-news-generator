#!/bin/bash
set -e

DOMAIN="yt-generator.duckdns.org"

echo "=== Installing Caddy ==="
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl

curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg

curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list

sudo apt update && sudo apt install -y caddy

echo "=== Writing Caddyfile ==="
sudo tee /etc/caddy/Caddyfile > /dev/null <<EOF
${DOMAIN} {
    reverse_proxy localhost:8000
}
EOF

echo "=== Starting Caddy ==="
sudo systemctl enable caddy
sudo systemctl reload caddy
sudo systemctl status caddy --no-pager

echo ""
echo "=== Done! ==="
echo "Your app should be accessible at: https://${DOMAIN}"
