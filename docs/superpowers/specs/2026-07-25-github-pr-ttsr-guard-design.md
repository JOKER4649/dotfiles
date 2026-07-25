# GitHub PR TTSR 與合併閘門設計

日期：2026-07-25

## 問題

目前 `github-pr-master` 的全域 extension 只在成功執行 `gh pr` 後追加提醒。它能讓 agent 想起 skill，但不能在真正的合併前阻止直接執行 `gh pr merge`，也不能把「等待 CI、等待 kilo、確認未解決 review threads」收斂成一個可重複驗證的合併流程。

omp 的 TTSR 適合在模型串流中命中 `gh pr merge` 時注入前置提醒，但 TTSR 的中斷是「中止當次生成並重試」，不是永久的 tool policy。真正不可繞過的阻擋必須放在 `tool_call` extension。

## 目標

- create/edit 維持低干擾提醒，讓 agent 持續遵循 `github-pr-master` 的 PR 文案與流程規範。
- 直接由 agent 呼叫 `gh pr merge` 時必須被阻止。
- 將目前 `pr_check` 改成目的明確的完整 `pr_merge` 工具：先驗證，後以明確短 hash 授權實際合併。
- 預設行為不得執行 merge；只有 `pr_merge --apply <hash>` 且重驗證全部通過時才可執行 `gh pr merge`。
- 保留 cwd 自動推導與 `--pr` 明確指定兩種使用方式。
- 失敗應在能確定失敗時立即退出，不因等待無關的檢查而延遲。

## 非目標

- 不用 shell 字串 parser 嘗試自動判斷繁體中文、標題資訊量或 body 語意；create/edit 採提醒，不做脆弱的語意硬擋。
- 不把完整 `github-pr-master` skill 複製到 TTSR rule。
- 不把短 hash 當成安全憑證；它只防止 agent 憑舊上下文或印象直接執行 apply。
- 不允許 direct `gh pr merge` 透過另一個 agent-facing alias 繞過檢查；唯一 agent 入口是 `pr_merge`。

## 元件

### 1. 全域 TTSR rule

新增 `omp/agent/rules/github-pr-master-merge.md`：

- `scope: tool:bash`
- condition 匹配直接出現的 `gh pr merge`
- `interruptMode: always`
- reminder 指向 `skill://github-pr-master` 及 `pr_merge`

它負責在模型生成 direct merge tool call 時提早提醒。TTSR 不是最終安全邊界；即使 TTSR 被停用或模型忽略 reminder，下面的 extension 仍會阻止 tool call。

### 2. 全域 ExtensionAPI

修改 `omp/agent/extensions/github-pr-master-reminder.ts`：

- `tool_result`：只對成功的 `bash` 且命中 `gh pr create` 或 `gh pr edit` 追加提醒。這是低干擾品質提醒，不阻止合法的部分編輯。
- `tool_call`：命中 direct `gh pr merge` 時回傳 `{ block: true, reason }`，reason 明確要求使用 `pr_merge`，並說明需要先完成檢查再用 `--apply <hash>`。
- `pr_merge` 頂層命令本身不含 direct `gh pr merge`，因此不會被這個 agent-facing guard 擋住；`pr_merge` 內部執行的子程序由命令自身的檢查流程控制。

使用 `ExtensionAPI` 而不是 legacy `HookAPI`；omp 官方文件說明 ExtensionAPI 是新功能的首選，且 `tool_call` 回傳 block 會在工具執行前停止執行。

### 3. `commands/pr_merge`

將目前 `commands/pr_check` 重新命名為 `commands/pr_merge`，並把它改成完整工具。保留既有 `gh` / GraphQL 查詢基礎，但調整主流程與介面：

```text
pr_merge [--pr REF] [--timeout SECONDS] [--interval SECONDS]
         [--kilo/--no-kilo] [--apply HASH]
         [--list | --resolve THREAD_ID]
         [--merge | --squash | --rebase] [--delete-branch]
```

- 預設 `REF` 省略時，使用 cwd repository 與目前 branch。
- `--pr` 接受 PR number、URL 或 branch，沿用現有行為。
- `--list` 只定位 PR 並列出未解決 threads，不等待 CI，也不執行 merge。
- `--resolve` 只解決指定的完整 thread ID 或 `#N` 索引；可重複或逗號分隔，不等待 CI，也不執行 merge。
- `--list`、`--resolve`、`--apply` 互斥；`--resolve` 不可與另一個 thread 操作混用。
- merge strategy 使用互斥的 `--merge`、`--squash` 或 `--rebase`；未指定時不偷偷選擇策略，直接交給 `gh`。若非 merge queue 情境需要 strategy，讓 `gh` 以明確錯誤返回，不進入互動等待。
- `--delete-branch` 只在 apply 模式傳給 `gh pr merge`。
- 保留 `--timeout`、`--interval`、`--kilo/--no-kilo`，讓等待行為可調整。
- `--apply HASH` 是唯一會進入實際 merge 的旗標；它不是布林開關，必須帶四碼 hash。

## `pr_merge` 檢查順序

每次執行，包括 `--apply`，都跑同一套檢查；`--apply` 只是在檢查成功後多一個 hash 比對與 merge 動作。

### 1. 定位與基本狀態

呼叫 `gh pr view` 取得至少：

- `number`, `url`, `state`, `isDraft`
- `headRefName`, `baseRefName`
- `mergeStateStatus`, `mergeable`
- `updatedAt`
- `statusCheckRollup`

找不到 PR、PR 不是 `OPEN`、或 PR 是 draft，立即退出，不進入後續等待。

### 2. Mergeability 快速篩選

第二步只攔截已知的硬阻塞，避免把 CI 尚未完成誤判成 mergeability 失敗：

- `mergeable == CONFLICTING` 或 `mergeStateStatus == DIRTY`：立即報錯，這是已確認的合併衝突。
- `mergeStateStatus` 為 `BLOCKED`、`UNSTABLE`、`UNKNOWN` 或 `BEHIND` 時先放行到 CI/kilo 等待；這些狀態可能由尚未完成的檢查或 GitHub 重新計算造成，不能在第二步直接判定為最終失敗。
- `mergeable == UNKNOWN` 也先放行；第二步只做快速篩選，不等待 mergeability 本身。

這一步仍會先拒絕非 `OPEN` 或 draft PR。CI/kilo/threads 完成後，必須重新讀取 mergeability；只有最終 `mergeStateStatus` 為 `CLEAN` 或 `HAS_HOOKS` 且 `mergeable` 為 `MERGEABLE` 才能輸出可合併提示。

### 3. CI / kilo

沿用現有 status rollup 分流：kilo CheckRun 與一般 CI 分開判讀。

- 任一 `StatusContext` 已是 `FAILURE` / `ERROR`，立即退出。
- 任一 CheckRun 已 `COMPLETED` 且 conclusion 屬於既有 failure 集合，立即退出。
- kilo 已 `COMPLETED` 且結論失敗，立即退出。
- 未失敗但仍有未完成項目時，以 `interval` 輪詢，直到全部完成或 timeout。
- timeout 維持既有 exit code `2`。
- 未啟用 kilo 時，`--no-kilo` 明確跳過 kilo 等待。

### 4. Review threads

CI/kilo 全部成功後取得 review threads：

- 有任何 `isResolved == false` 的 thread，立即報錯並列出索引、位置、作者、摘要。
- 不再把「未解決 threads」當成 exit code `0` 的附帶資訊；完整檢查模式必須以非零退出。
- `--list` 與 `--resolve` 是明確的輔助模式：它們只處理 threads，不跑完整檢查，也不執行 merge。
- `--apply` 不可與 `--list` 或 `--resolve` 混用。

### 5. 最終 mergeability 與授權 hash

CI/kilo 與 review threads 通過後，重新讀取 `mergeStateStatus` 與 `mergeable`：

- 只有 `mergeStateStatus` 為 `CLEAN` 或 `HAS_HOOKS`，且 `mergeable` 為 `MERGEABLE` 才能繼續。
- 若此時仍為 `DIRTY`、`BLOCKED`、`UNSTABLE`、`BEHIND`、`UNKNOWN` 或非 `MERGEABLE`，立即報錯，不輸出可合併提示。

最終 mergeability 通過後，再重新讀取 PR 的 `updatedAt`，以原始 timestamp 字串計算：

```python
hashlib.md5(updated_at.encode(), usedforsecurity=False).hexdigest()[:4]
```

輸出至少包含：

```text
PR 可合併
PR #<number>: <url>
確認碼: <hash>
執行: pr_merge --apply <hash>
```

短 hash 只提供「這是剛才檢查結果」的低成本確認，不宣稱能防篡改或取代 GitHub 權限。

### 6. Apply

`pr_merge --apply <hash>`：

1. 重新執行第 1–5 步。
2. 對最新 `updatedAt` 重算 hash。
3. 輸入 hash 不完全相同時立即退出，顯示目前有效的確認碼；不執行 merge。
4. hash 相同且所有檢查通過後，才呼叫 `gh pr merge`。
5. 將 `gh pr merge` 的 exit code / stderr 原樣轉成命令錯誤；不把 GitHub merge 失敗報成成功。

## 錯誤與退出碼

維持目前命令的基本語意：

- `0`：檢查成功；`--apply` 時代表實際 merge 成功。
- `1`：CI、kilo、mergeability、未解決 threads 或 hash 不符合。
- `2`：等待 timeout。
- `3`：`gh`、GraphQL、參數或目前 repository/PR 定位錯誤。

錯誤訊息必須指出失敗階段，不只輸出 generic `gh` 例外。

## Skill 文件變更

同步修改：

- `agents/skills/github-pr-master/SKILL.md`
- `agents/skills/github-pr-master/reference/review.md`

文件需明確說明：

- `pr_merge` 是全域命令。
- 預設執行檢查並輸出確認碼，不會合併。
- 只有 `pr_merge --apply <hash>` 才會嘗試實際合併。
- 直接 `gh pr merge` 會被全域 guard 阻止。
- create/edit 仍遵循 skill 的 PR 文案品質規範，成功後會收到 reminder。

保留目前未提交的 `SKILL.md` / `reference/review.md` 內容方向；不要恢復已刪除的 `wait.py`。

## 驗證

不建立或執行會真正合併 PR 的 destructive smoke test。至少驗證：

1. `pr_merge --help` 能載入並顯示 check/apply 介面。
2. 使用 fake `gh` / fake check command 驗證：檢查失敗時不會執行 merge；hash 錯誤時不會執行 merge；全部通過且 hash 正確時才會呼叫一次 merge。
3. 以 mock `ExtensionAPI` 驗證：成功 `gh pr create` / `gh pr edit` 會追加 reminder；direct `gh pr merge` 的 `tool_call` 回傳 block；`pr_merge` 不會被誤擋。
4. 啟動 omp 後用 `/extensions` 檢查 global TTSR rule 已載入、scope 正確。
5. 以唯讀 PR 查詢驗證 `mergeStateStatus`、`updatedAt` 與 review thread 判讀；不執行 `--apply`。

## 官方依據

- omp TTSR：<https://omp.sh/docs/ttsr>
- omp TTSR lifecycle：`omp://ttsr-injection-lifecycle.md`
- omp extension / tool-call blocking：`omp://extensions.md`、`omp://skills/authoring-extensions.md`
- GitHub CLI `gh pr merge`：`gh pr merge --help`（本機 CLI 介面）
