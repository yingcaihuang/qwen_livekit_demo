#!/bin/sh
# Generate livekit.yaml from environment variables at startup.
# This ensures keys are always in sync with .env.production.

LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-APIKeyForVoiceAdmin}"
LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-ThisIsASecretThatIsAtLeast32CharsLong!}"

cat > /etc/livekit.yaml << EOF
port: 7880
rtc:
  port_range_start: 7882
  port_range_end: 7882
  tcp_port: 7881

keys:
  ${LIVEKIT_API_KEY}: ${LIVEKIT_API_SECRET}

room:
  auto_create: true

logging:
  level: info
EOF

exec /livekit-server --config /etc/livekit.yaml
