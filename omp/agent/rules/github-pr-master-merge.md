---
description: 直接合併 PR 前改用 pr_merge 完成完整檢查
condition: "\\bgh\\s+pr\\s+merge\\b"
scope: "tool:bash"
interruptMode: always
---

即將直接執行 `gh pr merge`。不要直接合併。

先讀取 `skill://github-pr-master`，使用全域 `pr_merge`：

1. 先執行 `pr_merge`，等待 CI / kilo，確認沒有未解決 review threads。
2. 只有檢查成功後，使用輸出的短 hash 執行 `pr_merge --apply <hash>`。
3. 不要以記憶中的舊 hash 或直接 `gh pr merge` 取代這個流程。
