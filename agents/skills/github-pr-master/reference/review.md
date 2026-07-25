# 使用 `pr_merge` 完成 PR 檢查與合併

`pr_merge` 是唯一的 agent-facing PR 檢查與受保護合併入口。不要自行重建 CI、review、mergeability 或 PR 完成條件。

## 操作流程

先執行完整檢查：

```text
pr_merge
```

若命令輸出需要修正或處理 review threads，完成後重新執行 `pr_merge`。需要單獨查看或處理 threads 時，使用命令提供的 `pr_merge --list` 或 `pr_merge --resolve <ID>`。

檢查成功後，使用同一次檢查輸出的最新 hash：

```text
pr_merge --apply <hash>
```

`--apply` 會再次檢查；hash 不符合最新結果時不會合併。需要指定合併策略時，將 `--merge`、`--squash` 或 `--rebase` 其中一個旗標附加到 `--apply` 命令。

## 邊界

禁止直接執行 `gh pr merge`。它會被全域 guard 阻擋；不要繞過 `pr_merge` 的檢查流程。
