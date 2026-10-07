#!/usr/bin/env bash

# ============================================================
# dotfiles 自動備份腳本
#
# 偵測倉庫內的變更，自動 commit 並 push 到 remote。
# 若無變更則跳過，不產生空 commit。
#
# 用法：
#     ./backup.sh          執行備份（搭配 cron 自動排程）
#     ./backup.sh --dry-run 預覽模式，不實際執行
# ============================================================

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="${REPO_DIR}/backup/backup.log"
DRY_RUN=false
GIT="/usr/bin/git"

# 解析參數
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
    esac
done

# 記錄日誌（同時輸出到 stdout 與日誌檔）
log() {
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[${timestamp}] $1" | tee -a "$LOG_FILE"
}

log "開始備份 (repo: ${REPO_DIR})"

cd "$REPO_DIR"

# 確認是 git 倉庫
if [[ ! -d .git ]]; then
    log "錯誤：${REPO_DIR} 不是 git 倉庫"
    exit 1
fi

# 檢查是否有變更（含未追蹤檔案）
if $GIT diff --quiet && $GIT diff --cached --quiet && [[ -z "$($GIT ls-files --others --exclude-standard)" ]]; then
    log "無變更，跳過備份"
    exit 0
fi

log "偵測到變更："
$GIT status --short | while IFS= read -r line; do
    log "  ${line}"
done

if $DRY_RUN; then
    log "預覽模式，不實際執行"
    exit 0
fi

# 提交變更
COMMIT_MSG="backup: $(date '+%Y-%m-%d %H:%M:%S') 自動備份"

$GIT add -A
$GIT commit -m "$COMMIT_MSG"
log "已提交: ${COMMIT_MSG}"

# 推送到 remote
if $GIT push 2>&1 | tee -a "$LOG_FILE"; then
    log "已推送到 remote"
else
    log "錯誤：推送失敗"
    exit 1
fi

log "備份完成"
