#!/bin/sh
# Generate livekit.yaml from environment variables at startup.
# This ensures keys are always in sync with .env.production.

LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-APIKeyForVoiceAdmin}"
LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-ThisIsASecretThatIsAtLeast32CharsLong!}"
LIVEKIT_NODE_IP="${LIVEKIT_NODE_IP:-}"

# Build RTC config lines based on whether node_ip is provided
RTC_EXTRA=""
if [ -n "$LIVEKIT_NODE_IP" ]; then
    RTC_EXTRA="  node_ip: ${LIVEKIT_NODE_IP}
  use_external_ip: true"
fi

cat > /etc/livekit.yaml << EOF
port: 7880
rtc:
  port_range_start: 7882
  port_range_end: 7882
  tcp_port: 7881
${RTC_EXTRA}

keys:
  ${LIVEKIT_API_KEY}: ${LIVEKIT_API_SECRET}

room:
  auto_create: true

logging:
  level: info
EOF

echo "=== Generated livekit.yaml ==="
cat /etc/livekit.yaml
echo "==============================="

exec /livekit-server --config /etc/livekit.yaml
