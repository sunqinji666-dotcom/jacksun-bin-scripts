#!/bin/bash
# UU 远程控制（网易 UURemote）连接状态监测
# 采样：进程存活 + 网络连接（信令长连接 / P2P 会话 / 本地监听）
# 用法: ./monitor-uuremote.sh [间隔秒]  (默认 5 秒)
# 日志: /tmp/uuremote-monitor.log

INTERVAL="${1:-5}"
LOG="/tmp/uuremote-monitor.log"
PIDFILE="/tmp/uuremote-monitor.pid"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "监测已在运行 (PID $(cat "$PIDFILE"))，日志: $LOG"
    exit 0
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"; exit' INT TERM

log "===== UURemote 监测启动 (间隔 ${INTERVAL}s) ====="
while true; do
    # 进程状态
    PROCS=$(ps aux | grep -i -E "UURemote(app|Server|Service|Daemon|Agent)" | grep -v grep | awk '{print $2":"$11}' | sed 's|.*/||' | tr '\n' ' ')
    if [ -z "$PROCS" ]; then
        log "!! 进程全部退出，监测结束"
        rm -f "$PIDFILE"
        exit 1
    fi

    # 网络连接：只统计 UURemote 相关进程
    CONN=$(lsof -nP -i -a -c UURemote 2>/dev/null; lsof -nP -i -a -c UURemoteS 2>/dev/null; lsof -nP -i -a -c UURemoteD 2>/dev/null; lsof -nP -i -a -c UURemoteA 2>/dev/null)

    # 与网易服务器的 TLS 长连接（信令/待命）
    SIGNAL=$(echo "$CONN" | grep -E "TCP .*->[0-9.]+:(443|80) \(ESTABLISHED\)" | sed -E 's/ \(ESTABLISHED\)$//' | awk '{print $NF}' | awk -F'->' '{print $2}' | sort -u | tr '\n' ' ')
    # UDP：有对端 => 活跃 P2P 会话；无对端 => 待命打洞
    UDP_ACTIVE=$(echo "$CONN" | grep -E "UDP .*->" | grep -vE "->\*|\(LISTEN\)" | sed -E 's/ \(ESTABLISHED\)$//' | awk '{print $NF}' | grep -vE '^\*' | sort -u | tr '\n' ' ')
    UDP_LISTEN=$(echo "$CONN" | grep -E "UDP " | grep -vE "->[0-9.]+" | awk '{print $(NF-1)}' | sort -u | tr '\n' ' ')
    # 本地监听端口
    LISTEN=$(echo "$CONN" | grep -E "TCP .*\(LISTEN\)" | awk '{print $(NF-1)}' | sort -u | tr '\n' ' ')
    # 非 443 的 TCP 出站（可能是中继/其他）
    OTHER=$(echo "$CONN" | grep -E "TCP .*->[0-9.]+:[0-9]+ \(ESTABLISHED\)" | grep -vE ":443 |:80 " | sed -E 's/ \(ESTABLISHED\)$//' | awk '{print $NF}' | awk -F'->' '{print $2}' | sort -u | tr '\n' ' ')

    STATUS="在线"
    if [ -n "$UDP_ACTIVE" ]; then STATUS=">> 活跃 P2P 会话 <<"; fi

    log "[$STATUS] 进程[$PROCS]"
    [ -n "$SIGNAL" ]   && log "   信令(网易443): $SIGNAL"
    [ -n "$UDP_ACTIVE" ] && log "   P2P对端: $UDP_ACTIVE"
    [ -n "$UDP_LISTEN" ] && log "   UDP打洞口: $UDP_LISTEN"
    [ -n "$LISTEN" ]    && log "   本地监听: $LISTEN"
    [ -n "$OTHER" ]     && log "   其他TCP: $OTHER"
    sleep "$INTERVAL"
done
