#!/bin/bash
# VPS 154.36.143.246（ssh 别名 jacksun-la2）配置自动备份
# 2026-10-02 建立（克隆自 backup-la-vps.sh，去掉直播相关项）
# 由 ~/Library/LaunchAgents/com.jacksun.backup-la2-vps.plist 每天调用
#
# 备份内容：x-ui 面板配置库、sshd_config、fail2ban 配置、网络调优、crontab

set -uo pipefail

SSH=/usr/bin/ssh
SCP=/usr/bin/scp
SQLITE=/usr/bin/sqlite3
DEST="/Users/jacksun/.claude/backups/vps-154.36.143.246"
HOST=jacksun-la2
KEEP=30
TS=$(date +%Y%m%d-%H%M)
LOG="$DEST/backup.log"

mkdir -p "$DEST"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

# ---------- 1) 远程生成一致性快照 ----------
# 用 sqlite VACUUM INTO 而不是直接拷 .db：面板在运行，直接拷可能拿到写了一半的库
if ! $SSH -o BatchMode=yes -o ConnectTimeout=25 $HOST 'bash -s' >/dev/null 2>&1 <<'REMOTE'
set -u
rm -f /tmp/bk-*
python3 -c "import sqlite3; c=sqlite3.connect('/etc/x-ui/x-ui.db'); c.execute(\"VACUUM INTO '/tmp/bk-xui.db'\")" 2>/dev/null || cp /etc/x-ui/x-ui.db /tmp/bk-xui.db
# 流量面板账本（2026-10-07 加）：同样 VACUUM INTO 拿一致性快照；WAL 模式下直接拷主文件会丢数据
python3 -c "import sqlite3; c=sqlite3.connect('/var/lib/traffic-panel/traffic.db'); c.execute(\"VACUUM INTO '/tmp/bk-traffic.db'\")" 2>/dev/null || cp /var/lib/traffic-panel/traffic.db /tmp/bk-traffic.db
cp /etc/ssh/sshd_config /tmp/bk-sshd_config
tar czf /tmp/bk-sshd_config.d.tar.gz -C /etc/ssh sshd_config.d 2>/dev/null || true
cp /etc/fail2ban/jail.local /tmp/bk-jail.local 2>/dev/null || true
cp /etc/sysctl.d/99-jacksun-net.conf /tmp/bk-net-tuning.conf 2>/dev/null || true
crontab -l > /tmp/bk-crontab 2>/dev/null || true
chmod 644 /tmp/bk-* 2>/dev/null || true
REMOTE
then
  log "✗ 远程快照失败（服务器不可达？），本次跳过"
  echo "$(date '+%Y-%m-%d %H:%M:%S')" >> "$DEST/.last-failure"
  exit 1
fi

# ---------- 2) 拉回本机 ----------
ok=1
$SCP -q -o BatchMode=yes $HOST:/tmp/bk-xui.db "$DEST/x-ui-$TS.db" \
  || { log "✗ 拉取 x-ui.db 失败"; ok=0; }
$SCP -q -o BatchMode=yes $HOST:/tmp/bk-traffic.db "$DEST/traffic-$TS.db" \
  || { log "✗ 拉取 traffic.db 失败"; ok=0; }
$SCP -q -o BatchMode=yes $HOST:/tmp/bk-sshd_config "$DEST/sshd_config-$TS" \
  || { log "✗ 拉取 sshd_config 失败"; ok=0; }
$SCP -q -o BatchMode=yes $HOST:/tmp/bk-jail.local "$DEST/fail2ban-jail.local-$TS" 2>/dev/null || true
$SCP -q -o BatchMode=yes $HOST:/tmp/bk-crontab "$DEST/crontab-$TS" 2>/dev/null || true
$SCP -q -o BatchMode=yes $HOST:/tmp/bk-sshd_config.d.tar.gz "$DEST/sshd_config.d-$TS.tar.gz" 2>/dev/null || true
$SCP -q -o BatchMode=yes $HOST:/tmp/bk-net-tuning.conf "$DEST/网络调优-$TS.conf" 2>/dev/null || true

# ---------- 3) 清理远程临时文件 ----------
$SSH -o BatchMode=yes $HOST 'rm -f /tmp/bk-*' >/dev/null 2>&1 || true

# ---------- 4) 轮转：只保留最近 KEEP 份 ----------
for pat in "x-ui-*.db" "traffic-*.db" "sshd_config-*" "sshd_config.d-*.tar.gz" "网络调优-*.conf" "fail2ban-jail.local-*" "crontab-*"; do
  ls -t "$DEST"/$pat 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r f; do
    rm -f "$f"
  done
done

# ---------- 4.5) 空库校验 ----------
if [ -f "$DEST/x-ui-$TS.db" ] && [ ! -s "$DEST/x-ui-$TS.db" ]; then
  rm -f "$DEST/x-ui-$TS.db"
  log "⚠️ 本次 x-ui.db 快照为空，已丢弃，保留上一份"
fi

# ---------- 5) 人可读现状快照 ----------
if [ -f "$DEST/x-ui-$TS.db" ]; then
  {
    echo "# VPS 154.36.143.246 节点快照（自动生成于 $(date '+%Y-%m-%d %H:%M')）"
    echo
    echo "## 入站节点"
    $SQLITE "$DEST/x-ui-$TS.db" \
      "select '  - '||remark||' | 端口 '||port||' | '||protocol||' | 启用='||enable from inbounds;" 2>/dev/null
    echo
    echo "## 客户端流量"
    $SQLITE "$DEST/x-ui-$TS.db" \
      "select '  - '||email||' | 上传 '||round(up/1073741824.0,2)||'GB | 下载 '||round(down/1073741824.0,2)||'GB | 启用='||enable from client_traffics;" 2>/dev/null
  } > "$DEST/节点快照.txt"
fi

# ---------- 6) 收尾 ----------
if [ "$ok" = "1" ]; then
  log "✓ 备份成功（保留最近 $KEEP 份）"
  rm -f "$DEST/.last-failure"
else
  log "△ 备份部分失败"
fi
