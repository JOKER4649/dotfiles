---
name: github-pr-master
description: 建立 GitHub PR，並一律使用 `pr_merge` 完成檢查與受保護合併。當需要「建立 PR」「推送 review」「確認可合併」或「合併 PR」時觸發。
---

## 適用範圍

涵蓋 GitHub PR 的建立與受保護合併流程。

- 僅支援 **GitHub**（依賴 `gh`）。
- GitLab PR 不使用此 skill。

## 流程

### 1. 建立 PR → 詳見 `reference/create.md`

- 不要在預設分支上建立 PR。
- PR title / body 使用繁體中文，表達問題、結果或行為變化。
- 建立與編輯 PR 的文案規範見 `reference/create.md`。

### 2. 檢查、處理 review 與合併 → 詳見 `reference/review.md`

`pr_merge` 是唯一的 agent-facing PR 檢查與受保護合併入口。

- 先執行 `pr_merge`；若命令輸出需要修正或處理 review threads，完成後重新執行。
- 檢查成功後，只使用最新輸出的 hash 執行 `pr_merge --apply <hash>`。
- 需要指定合併策略時，將策略旗標傳給 `pr_merge --apply`。
- 絕不直接執行 `gh pr merge`。
