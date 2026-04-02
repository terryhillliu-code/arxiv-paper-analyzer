#!/bin/bash
# ArXiv 平台健康检查脚本
# 用法: ./health_check.sh [--notify]

BACKEND_URL="http://localhost:8000/health"
FRONTEND_URL="http://localhost:5173"
LOG_FILE="$HOME/logs/arxiv-health.log"

# 钉钉 Webhook（来自 push_config.md）
DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=6a671d42464224cfe0b40a2183ea94fd433274e5054d1aa1db84490012d1a772"
DINGTALK_SECRET="SECxxxx"  # 如有签名密钥填入

# 日志函数
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

# 检查 Backend
check_backend() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL" --connect-timeout 5)
    if [ "$response" = "200" ]; then
        log "✅ Backend 健康"
        return 0
    else
        log "❌ Backend 异常 (HTTP $response)"
        return 1
    fi
}

# 检查 Frontend
check_frontend() {
    response=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" --connect-timeout 5)
    if [ "$response" = "200" ]; then
        log "✅ Frontend 健康"
        return 0
    else
        log "❌ Frontend 异常 (HTTP $response)"
        return 1
    fi
}

# 检查 launchd 服务
check_launchd() {
    backend_loaded=$(launchctl list 2>/dev/null | grep -c "com.arxiv.backend")
    frontend_loaded=$(launchctl list 2>/dev/null | grep -c "com.arxiv.frontend")

    if [ "$backend_loaded" -eq 0 ]; then
        log "⚠️ Backend 未加载到 launchd"
    fi
    if [ "$frontend_loaded" -eq 0 ]; then
        log "⚠️ Frontend 未加载到 launchd"
    fi
}

# 发送钉钉通知
send_dingtalk() {
    local title="$1"
    local content="$2"

    # 简单推送（无签名）
    curl -s "$DINGTALK_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{\"msgtype\":\"markdown\",\"markdown\":{\"title\":\"$title\",\"text\":\"$content\"}}" \
        > /dev/null 2>&1

    log "📤 已发送钉钉告警: $title"
}

# 发送通知
send_notify() {
    local message="# ArXiv 平台告警\n\n"
    message+="**时间**: $(date '+%Y-%m-%d %H:%M:%S')\n\n"

    if [ "$backend_ok" = false ]; then
        message+="❌ **Backend**: 异常\n"
    else
        message+="✅ **Backend**: 正常\n"
    fi

    if [ "$frontend_ok" = false ]; then
        message+="❌ **Frontend**: 异常\n"
    else
        message+="✅ **Frontend**: 正常\n"
    fi

    message+="\n---\n查看日志: \`tail -50 ~/logs/arxiv-health.log\`"

    send_dingtalk "ArXiv 服务告警" "$message"
}

# 主流程
main() {
    backend_ok=true
    frontend_ok=true

    check_launchd

    if ! check_backend; then
        backend_ok=false
        # 尝试重启
        log "尝试重启 Backend..."
        launchctl unload "$HOME/Library/LaunchAgents/com.arxiv.backend.plist" 2>/dev/null
        sleep 2
        launchctl load "$HOME/Library/LaunchAgents/com.arxiv.backend.plist" 2>/dev/null
        sleep 5
        if check_backend; then
            log "✅ Backend 已自动恢复"
        else
            log "❌ Backend 自动恢复失败"
        fi
    fi

    check_frontend || frontend_ok=false

    if [ "$1" = "--notify" ] && { [ "$backend_ok" = false ] || [ "$frontend_ok" = false ]; }; then
        send_notify
    fi
}

main "$@"