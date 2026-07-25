---
name: github-pr-master
description: 建立 review-ready 的 GitHub PR 並在合併前完成所有檢查。涵蓋建立分支、撰寫 PR 標題與內文、等待 CI 與 kilo-code-bot review、處理 review comments、確認 PR 滿足合併條件。當需要「建立 PR」「推送 review」「等 CI」「等 kilo」「處理 AI review」「確認可合併」時觸發。
---

## 適用範圍

涵蓋 PR 從建立到合併的完整流程。

- 僅支援 **GitHub**（依賴 `gh`）
- 當 **專案位於 GitLab**：忽略 AI review 與 kilo 相關流程（GitLab 不支援 kilo-code-bot），其餘建立與 CI 流程比照辦理

## 流程

### 1. 建立 PR → 詳見 `reference/create.md`

- 當前分支不應在預設分支上（通常為 `main` / `master`）
- PR title / body 以繁體中文撰寫
- PR 應表達完成了什麼功能 / 解決了什麼問題，而非解釋做了什麼
- push 前在本地完成檢查，盡可能減少 GitHub Actions 負擔
- 標題格式、內文範本見 `reference/create.md`

### 2. 檢查與合併 → 詳見 `reference/review.md`

- 用全局命令 `pr_merge` 輪詢等待 CI 完成 + kilo review 完成；預設為 check-only，完成後輸出四碼 confirmation hash，**不要**用 `sleep` 猜等待時間
- 修復 review comments 後 push，kilo 會對新 commit 重跑；用 `pr_merge` 重新執行這一輪檢查
- 確認檢查通過後，使用 `pr_merge --apply <hash>` 合併；只有 `gh` 需要時才加上明確的 `--squash`、`--merge` 或 `--rebase` 策略旗標
- Agent 絕不直接呼叫 `gh pr merge`；全域 ExtensionAPI guard 會阻擋此操作

### 3. 處理 review → 詳見 `reference/review.md`

- 讀取 kilo（與 gemini）的 review comments
- 按回應原則修復 / 採納 / 建 issue / 拒絕
- 已處理的 thread 用 `pr-review-thread_resolve` 解決

## PR 完成的定義

以下**全部**滿足才視為 PR 完成（可合併）：

- CI 全部通過
- 沒有合併衝突
- kilo review 已完成且無 critical；所有 AI review 的 thread 已 `resolved`
- PR 以繁體中文撰寫，正確表達意圖（解決什麼問題 / 帶來什麼結果），而非解釋做了什麼
- PR 不包含看 diff 就能知道的技術細節；程式碼、註解、文檔本就該自我表達
- changes 沒有臨時檔案 / 測試 log 之類的垃圾

### TODO 管理

建立 TODO 確保所有工作完成。中途臨時任務不可覆蓋當前 TODO，應用 update 插入。所有 `[MVP]` TODO **必須**在所有其他 TODO 都完成的情況下，最後**一次性**完成。

## 工具

- `act` — 模擬 GitHub Actions，減少 GitHub Actions 負擔
- `pr_merge`（全局命令，位於 `commands/`）— 預設 check-only，等待 CI 與 kilo review、確認可合併性並列出未解決 review threads；用法見 `reference/review.md`。以輸出的四碼 hash 搭配 `pr_merge --apply <hash>` 合併，必要時加策略旗標
- `pr-review-thread_list` / `pr-review-thread_resolve` / `pr-review-thread_unresolve` — 操作 PR review threads（亦可直接用 `pr_merge --list` / `pr_merge --resolve`）
