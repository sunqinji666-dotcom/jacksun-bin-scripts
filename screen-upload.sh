#!/bin/bash
# 每分钟截图上传到 kodbox "来图" 分享
# 日志: /tmp/screen-upload.log  停止: pkill -f screen-upload.sh
LOG="/tmp/screen-upload.log"
WORK="/tmp/screen-capture"
mkdir -p "$WORK"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

log "===== 屏幕定时上传启动 (每 10 分钟) ====="
while true; do
    TS=$(date '+%Y%m%d_%H%M%S')
    PNG="$WORK/screen_${TS}.png"
    JPG="$WORK/screen_${TS}.jpg"

    # 1. 截图
    screencapture -x "$PNG" 2>/dev/null
    if [ ! -s "$PNG" ]; then
        log "[警告] 截图失败，跳过本轮"
        sleep 60; continue
    fi

    # 2. 压缩: 宽1600, JPEG质量60
    sips -Z 1600 -s format jpeg -s formatOptions 60 "$PNG" --out "$JPG" >/dev/null 2>&1
    rm -f "$PNG"
    if [ ! -s "$JPG" ]; then
        log "[警告] 压缩失败，跳过本轮"
        sleep 60; continue
    fi
    SIZE=$(stat -f%z "$JPG")

    # 3. 上传
    if python3 /Users/jacksun/bin/upload_kodbox.py "$JPG" "screen_${TS}.jpg" >> "$LOG" 2>&1; then
        log "[OK] 已上传 screen_${TS}.jpg (${SIZE}B)"
    else
        log "[失败] screen_${TS}.jpg 上传出错"
    fi
    rm -f "$JPG"
    sleep 600
done
