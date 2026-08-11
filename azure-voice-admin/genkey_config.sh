#!/bin/bash
set -e

echo "=============================="
echo "  生成 .env.production 配置"
echo "=============================="
echo ""

# Check if .env.production already exists
if [ -f .env.production ]; then
    echo "⚠️  .env.production 已存在。"
    read -p "是否覆盖？(y/N): " overwrite
    if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
        echo "已取消。"
        exit 0
    fi
    echo ""
fi

# Generate random API key and secret
LIVEKIT_API_KEY=$(openssl rand -base64 18 | tr -d '/+=' | head -c 24)
LIVEKIT_API_SECRET=$(openssl rand -hex 32)

echo "📋 LiveKit 凭据（自动生成）："
echo "   API Key:    $LIVEKIT_API_KEY"
echo "   API Secret: $LIVEKIT_API_SECRET"
echo ""

# Ask for deployment mode
echo "选择部署模式："
echo "  1) 本地开发（HTTP，localhost）"
echo "  2) 公网生产（HTTPS，自定义域名）"
read -p "请选择 [1/2]: " mode
echo ""

if [ "$mode" = "2" ]; then
    # Loop until valid site domain
    SITE_DOMAIN=""
    while [ -z "$SITE_DOMAIN" ]; do
        read -p "主站域名（如 livekit.verycloud.cn）: " SITE_DOMAIN
        if [ -z "$SITE_DOMAIN" ]; then
            echo "❌ 主站域名不能为空，请重新输入"
        fi
    done

    # Loop until valid RTC domain
    RTC_DOMAIN=""
    while [ -z "$RTC_DOMAIN" ]; do
        read -p "RTC 域名（如 rtc.verycloud.cn）: " RTC_DOMAIN
        if [ -z "$RTC_DOMAIN" ]; then
            echo "❌ RTC 域名不能为空，请重新输入"
        fi
    done

    LIVEKIT_PUBLIC_URL="wss://${RTC_DOMAIN}"

    # Get node IP (auto-detect or manual)
    echo ""
    echo "正在检测服务器公网 IP..."
    AUTO_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || curl -s --max-time 5 ip.sb 2>/dev/null || echo "")
    if [ -n "$AUTO_IP" ]; then
        echo "检测到公网 IP: $AUTO_IP"
        read -p "使用此 IP？(Y/n): " use_auto
        if [ "$use_auto" = "n" ] || [ "$use_auto" = "N" ]; then
            read -p "请输入服务器公网 IP: " LIVEKIT_NODE_IP
        else
            LIVEKIT_NODE_IP="$AUTO_IP"
        fi
    else
        read -p "无法自动检测，请输入服务器公网 IP: " LIVEKIT_NODE_IP
    fi

    echo ""
    echo "🌐 域名配置："
    echo "   主站: https://${SITE_DOMAIN}"
    echo "   RTC:  ${LIVEKIT_PUBLIC_URL}"
else
    SITE_DOMAIN=":80"
    RTC_DOMAIN=""
    LIVEKIT_PUBLIC_URL="ws://localhost:7880"

    echo "🏠 本地模式：http://localhost"
fi

echo ""

# Write .env.production
cat > .env.production << EOF
# ============================================================
# Azure Voice Testing Admin - 环境变量配置
# 由 genkey_config.sh 自动生成于 $(date '+%Y-%m-%d %H:%M:%S')
# ============================================================

# ----------------------------------------------------------
# LiveKit 凭据（backend 和 livekit 服务共享）
# ----------------------------------------------------------
LIVEKIT_API_KEY=${LIVEKIT_API_KEY}
LIVEKIT_API_SECRET=${LIVEKIT_API_SECRET}

# ----------------------------------------------------------
# 域名配置
# ----------------------------------------------------------
SITE_DOMAIN=${SITE_DOMAIN}
LIVEKIT_PUBLIC_URL=${LIVEKIT_PUBLIC_URL}
EOF

# Add RTC_DOMAIN only for production mode
if [ -n "$RTC_DOMAIN" ]; then
    echo "RTC_DOMAIN=${RTC_DOMAIN}" >> .env.production
fi

if [ -n "$LIVEKIT_NODE_IP" ]; then
    echo "LIVEKIT_NODE_IP=${LIVEKIT_NODE_IP}" >> .env.production
fi

echo ""
echo "✅ 已生成 .env.production"
echo ""
echo "启动服务："
echo "  ./build.sh"
echo "  docker compose --env-file .env.production up -d --force-recreate"
echo ""
