# github-pr-master 指導縮減設計

日期：2026-07-25

## 背景

`commands/pr_merge` 已是 GitHub PR 的唯一 agent-facing 檢查與受保護合併入口。現行 `agents/skills/github-pr-master/` 仍在 skill 與 review reference 中重述 CI、AI reviewer、review thread、退出碼與 PR 完成條件，要求 agent 自行維護一套與命令重疊的判斷流程。

這些重複規則增加 agent 的決策分支，也可能讓文件與 `pr_merge` 的實際行為不一致。本次只收斂指導文字，不改變命令或 guard 行為。

## 目標

- 讓 agent 知道所有 PR 檢查、review thread 處理與合併都必須經過 `pr_merge`。
- 讓 agent 以 `pr_merge` 的輸出作為檢查結果，不自行重建 PR 完成條件。
- 保留建立 PR 文案的獨立規範。
- 保留直接 `gh pr merge` 的禁止說明，以及 `pr_merge --apply <hash>` 的確認碼流程。

## 決策

### 1. 縮短主 skill

修改 `agents/skills/github-pr-master/SKILL.md`：

- 保留 GitHub-only 適用範圍與 `reference/create.md` 入口。
- 移除 PR 完成條件清單、AI reviewer 分工、TODO 管理與重複工具細節。
- 將檢查與合併收斂成單一規則：先執行 `pr_merge`；若輸出要求修正或處理 threads，完成後重新執行；檢查成功後只以輸出的 hash 執行 `pr_merge --apply <hash>`。
- 明確禁止 agent 直接呼叫 `gh pr merge`。

### 2. 縮短 review reference

修改 `agents/skills/github-pr-master/reference/review.md`：

- 保留 `pr_merge` 的最短操作循環。
- 保留 `--list` 與 `--resolve` 作為命令提供的 thread 輔助模式提示，但不描述其完整參數、退出碼或內部輪詢細節。
- 移除 reviewer 名稱、等待策略、完整 PR 完成清單與通用 AI review 回應原則。
- 不讓文件要求 agent 自行判斷完整的合併條件；以 `pr_merge` 的結果為準。

### 3. 保留建立 PR 規範

`agents/skills/github-pr-master/reference/create.md` 不修改。PR 標題、內文與驗證描述仍是建立 PR 時需要的獨立品質規範，不屬於本次要移除的合併完成細節。

## 操作契約

```text
pr_merge
# 依命令輸出處理必要修正或 review threads，完成後重新執行
pr_merge --apply <hash>
```

`--apply` 的 hash 必須來自最新一次成功的 `pr_merge`。策略旗標只在需要時附加。agent 不得以直接 `gh pr merge` 取代上述流程；現有 TTSR、ExtensionAPI guard 與 `pr_merge` 內部必要的 GitHub CLI 引用不在本次修改範圍。

## 不變條件

- 不修改 `commands/pr_merge` 的 CLI、檢查順序、hash 規則、退出碼或 GitHub API 行為。
- 不修改 `reference/create.md`。
- 不修改 `omp/agent/rules/github-pr-master-merge.md` 或 `omp/agent/extensions/github-pr-master-reminder.ts`。
- 不觸碰主工作樹中與本任務無關的未追蹤工作樹或 blob 資料。

## 驗收

- `SKILL.md` 不再包含獨立的 PR 完成條件清單、AI reviewer 處理流程或 TODO 管理規則。
- `reference/review.md` 只描述 `pr_merge` 的必要操作與 direct merge 邊界。
- `reference/create.md` 的內容與檔案狀態不變。
- 相關文件不再引導 agent 使用其他 PR 檢查或合併入口。
- `commands/pr_merge --help` 與既有 `commands.tests.test_pr_merge` 契約測試仍可通過，證明本次文件修改未影響命令。
