#!/bin/bash
set -e

echo "=============================="
echo "  Building Docker Images"
echo "=============================="
echo ""

# Build all images
echo "→ Building Caddy + Frontend image..."
docker compose build caddy

echo ""
echo "→ Building Backend image..."
docker compose build backend

echo ""
echo "✓ All images built successfully!"
echo ""
echo "To start the system:"
echo "  docker compose up -d"
echo ""
echo "To start with production domains:"
echo "  SITE_DOMAIN=livekit.verycloud.cn RTC_DOMAIN=rtc.verycloud.cn docker compose up -d"
