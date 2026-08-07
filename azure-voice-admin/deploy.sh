#!/bin/bash
set -e

echo "=============================="
echo "  Azure Voice Admin Deploy"
echo "=============================="
echo ""

# Check if .env.production exists
if [ ! -f .env.production ]; then
    echo "⚠ .env.production not found!"
    echo "  Creating from template..."
    cat > .env.production << 'EOF'
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
SITE_DOMAIN=:80
RTC_DOMAIN=
EOF
    echo "  ✓ Created .env.production (HTTP mode, no HTTPS)"
    echo "  Edit .env.production to set domain names for HTTPS"
    echo ""
fi

# Load env vars
source .env.production 2>/dev/null || true

echo "Configuration:"
echo "  SITE_DOMAIN: ${SITE_DOMAIN:-:80}"
echo "  RTC_DOMAIN: ${RTC_DOMAIN:-disabled}"
echo ""

# Build
echo "→ Building images..."
docker compose build
echo "  ✓ Build complete"
echo ""

# Start
echo "→ Starting services..."
docker compose up -d
echo ""

# Status
echo "→ Service status:"
docker compose ps
echo ""

echo "=============================="
if [ "${SITE_DOMAIN}" = ":80" ] || [ -z "${SITE_DOMAIN}" ]; then
    echo "  Access: http://localhost"
else
    echo "  Access: https://${SITE_DOMAIN}"
fi
echo "=============================="
