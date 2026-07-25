# 使用 `pr_merge` 檢查與處理 review

## AI reviewer

組織內主要 AI reviewer 為 `kilo-code-bot`。

- kilo 每次推送都會自動 review；修復並 push 後需用 `pr_merge` 重新等待 kilo 完成再檢查 comments
- `gemini-code-assist` 可能仍開啟作為第二視角補充，**不主動等待**；出現的評論按下方「回應原則」一併處理

## 檢查工具：`pr_merge`

使用全局命令 `pr_merge`（位於 `commands/`）檢查當前 PR。

- 預設為 check-only：使用目前 cwd 與 branch 的 PR（省略 `--pr`），等待 CI 與 kilo review 完成，確認沒有未解決 threads，並執行最終 mergeability check
- 每 30 秒輪詢一次，15 分鐘 timeout；依賴 `gh`；完成後輸出四碼 confirmation hash
- 選項 `--kilo/--no-kilo`（預設等待 kilo；GitHub repo 未裝 kilo 時用 `--no-kilo`）；另有 `--timeout`、`--interval`、`--pr`
- `--list`：thread-only 輔助模式，不等待，直接列出當前未解決的 review threads（含 thread ID、路徑、作者、摘要）
- `--resolve <ID>`：thread-only 輔助模式，解決 review thread，接受完整 thread ID 或 `#N` 索引（以未解決 threads 的顯示順序為準），可重複或逗號分隔批次解決
- 退出碼：`0`=檢查通過且可合併；`1`=CI 失敗、kilo 結論為 FAILURE、存在未解決 threads 或不可合併；`2`=超時；`3`=gh 錯誤
- gemini 不在等待範圍
- **不要**用 `sleep` 猜等待時間

## 處理 review comments

取得 kilo（與 gemini）的 review 內容後據此回應。`pr_merge` 預設會在檢查完成後列出未解決 threads；亦可隨時用 `pr_merge --list` 重新列出。解決 thread 可用以下任一方式：

- `pr_merge --resolve <ID>` — 全局命令，支援完整 thread ID 或 `#N` 索引，可批次（逗號分隔或重複 `--resolve`）
- MCP 工具（agent 環境可用）：`pr-review-thread_list` / `pr-review-thread_resolve` / `pr-review-thread_unresolve`

## 合併

先執行預設 check-only 流程取得最新四碼 hash，再確認輸出後執行：

```text
pr_merge
# 確認輸出中的四碼 hash 後
pr_merge --apply <hash> --squash   # 或 --merge / --rebase
```

`--apply` 會先重跑完整檢查（含 CI、kilo、threads 與 mergeability），確認 hash 仍符合後才呼叫 GitHub。禁止直接呼叫 `gh pr merge`；全域 ExtensionAPI guard 會阻擋此操作。策略旗標只在需要時指定，且三者不可同時使用。

### 回應原則

- **不應盲信** AI review 評論，由於缺少任務的完整上下文，應拒絕不合實際情況的評論
- 明確的 bug 與設計問題 → 修復
- 簡單的改良建議 → 直接採用
- 複雜的改良建議 → 建立 issue 追蹤
- 需要決策的取捨 → 向用戶確認
- 已處理的 thread → resolve；AI 誤判則附說明後 resolve
