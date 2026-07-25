# pr_merge 清理與文件一致性設計

日期：2026-07-25

## 目標

`pr_merge` 已成為 GitHub PR 的唯一檢查與受保護合併入口。移除殘留的 `commands/pr_check`，讓命令頂層說明直接表達其設計，並將專案內仍描述舊命令或 `wait.py` 的 tracked 文件改成現行流程。

## 決策

1. `commands/pr_check` 是未受 Git 保護的檔案，依專案規則移至 `.delete/commands/pr_check`，而不是直接刪除。
2. `commands/pr_merge` 的 module docstring 只保留三項核心契約：
   - 預設只執行完整檢查並輸出四碼 confirmation hash。
   - `--apply <hash>` 會重新檢查並驗證 hash，全部通過後才執行 merge。
   - `--list` / `--resolve` 是不等待、不合併的 review-thread 輔助模式。
3. `agents/skills/github-pr-master/`、`commands/`、`omp/agent/`、tracked plan/spec 中的過時 `pr_check` / `wait.py` 描述，改寫為 `pr_merge` 的現行語意。直接 `gh pr merge` 在 guard 說明與命令實作中的必要引用保留。
4. `omp/wt/` 等其他未追蹤工作樹不屬於本次清理範圍，避免改動使用者的獨立工作內容。

## 不變條件

- 不改變 `pr_merge` 的 CLI、檢查順序、hash 規則、退出碼或 GitHub API 行為。
- 不改動 TTSR rule、ExtensionAPI guard 或既有 skill 的 PR 文案與 GitLab 規範。
- 不觸碰主工作樹既有的 `README.md`、`mise/config.toml`、`omp/agent/config.yml`、`services/hindsight/docker-compose.yml`、`worktrunk/config.toml` 及其他未追蹤變更。

## 驗證

- 限定專案相關 tracked 路徑搜尋 `pr_check`、`wait.py` 與 `pr_merge`，確認沒有舊的 operational instruction；歷史文件也不得再使用舊命令名稱。
- `python3 -m unittest commands.tests.test_pr_merge -v` 全部通過。
- `commands/pr_merge --help` 成功載入並顯示 check/apply、thread 與 strategy 介面。
- 確認 `commands/pr_check` 不再位於 `commands/`，且 `.delete/commands/pr_check` 保留可恢復內容。
