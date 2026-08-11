#!/bin/sh
# Generate livekit.yaml from environment variables at startup.
# This ensures keys are always in sync with .env.production.

LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-APIKeyForVoiceAdmin}"
LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-ThisIsASecretThatIsAtLeast32CharsLong!}"
LIVEKIT_NODE_IP="${LIVEKIT_NODE_IP:-}"

# Build node_ip line only if set (for WebRTC ICE candidates)
RTC_EXTRA=""
if [ -n "$LIVEKIT_NODE_IP" ]; then
    RTC_EXTRA="  node_ip: ${LIVEKIT_NODE_IP}
  use_external_ip: true"
fi

cat > /etc/livekit.yaml << EOF
port: 7880
rtc:
  port_range_start: 50000
  port_range_end: 50020
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
