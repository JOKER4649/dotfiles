# pr_merge 清理與文件一致性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除舊的 PR 檢查命令，讓 `pr_merge` 的頂層說明與所有 tracked 流程文件一致反映現行的檢查、確認碼與受保護合併設計。

**Architecture:** 保留 `commands/pr_merge` 作為唯一執行入口，僅縮短其 module docstring，不改變任何 CLI 或檢查邏輯。將未受 Git 保護的舊命令移入 `.delete/`，並同步改寫 active skill、review reference、既有 plan/spec 與本次設計文件；獨立未追蹤工作樹不納入變更。

**Tech Stack:** Python 3.11、PEP 723 `uv run --script`、Typer、標準庫 `unittest`、Markdown。

## Global Constraints

- 不改變 `commands/pr_merge` 的 CLI、檢查順序、hash 規則、退出碼或 GitHub API 行為。
- 預設只檢查並輸出四碼 confirmation hash；只有 `pr_merge --apply <hash>` 重新檢查並通過 hash 驗證後才執行 merge。
- `--list` / `--resolve` 只處理 review threads，不等待也不合併。
- 直接 `gh pr merge` 的 guard 說明與 `pr_merge` 內部必要實作引用保留。
- 不修改主工作樹既有的非本任務變更，也不修改 `omp/wt/` 等獨立未追蹤工作樹。
- 移除未受 Git 保護的檔案時使用 `mv` 至 `.delete/`，不使用 `rm`。

---

## File Map

| 檔案 | 責任 | 變更 |
|---|---|---|
| `commands/pr_merge` | 唯一 PR 檢查與受保護合併命令 | 縮短 module docstring，保持執行邏輯不變 |
| `.delete/commands/pr_check` | 舊命令的暫存歸檔 | 從 `commands/` 移入，未受 Git 追蹤 |
| `agents/skills/github-pr-master/SKILL.md` | GitHub PR 主流程 | 確認只描述現行 `pr_merge` |
| `agents/skills/github-pr-master/reference/review.md` | 檢查、thread 與 apply 指引 | 確認只描述現行 `pr_merge` |
| `docs/superpowers/plans/2026-07-25-github-pr-ttsr-guard.md` | 原始實作計畫 | 將遷移時措辭改成現行狀態 |
| `docs/superpowers/specs/2026-07-25-github-pr-ttsr-guard-design.md` | 原始設計規格 | 將遷移時措辭改成現行狀態 |
| `docs/superpowers/specs/2026-07-25-pr-merge-cleanup-design.md` | 本次清理規格 | 移除過時命令名稱，保留清理決策 |
| `docs/superpowers/plans/2026-07-25-pr-merge-cleanup.md` | 本實作計畫 | 記錄本次清理步驟與驗證 |

---

### Task 1: Archive the obsolete checker and clarify `pr_merge`

**Files:**
- Move: `commands/pr_check` → `.delete/commands/pr_check`
- Modify: `commands/pr_merge:6-21`

**Interfaces:**
- Consumes: existing executable command and its current PEP 723 metadata.
- Produces: the same executable `commands/pr_merge`, with a concise top-level contract.

- [ ] **Step 1: Confirm the source and destination are safe**

Run from the repository root:

```bash
test -x commands/pr_merge
test -f commands/pr_check
mkdir -p .delete/commands
```

Expected: all commands exit `0`; no existing `.delete/commands/pr_check` is overwritten.

- [ ] **Step 2: Archive the untracked command**

```bash
mv commands/pr_check .delete/commands/pr_check
```

Expected: `commands/pr_check` is absent and `.delete/commands/pr_check` contains the original file.

- [ ] **Step 3: Replace only the `pr_merge` module docstring**

Keep the shebang and PEP 723 metadata unchanged. Replace the current docstring with:

```python
"""GitHub PR 的檢查與受保護合併命令。

預設只執行完整檢查並輸出四碼 confirmation hash；只有
`--apply <hash>` 在重新檢查並驗證 hash 通過後才執行 merge。
`--list` / `--resolve` 僅處理 review threads，不等待也不合併。
"""
```

- [ ] **Step 4: Verify the command interface**

```bash
commands/pr_merge --help
```

Expected: exit `0`; help still lists `--apply`, `--list`, `--resolve`, timeout/interval, Kilo selection, merge strategy, and branch deletion options.

- [ ] **Step 5: Commit the command cleanup**

```bash
git add commands/pr_merge
git commit -m "refactor: 清理舊 pr 檢查命令"
```

Do not stage `.delete/` or any pre-existing user files.

---

### Task 2: Rewrite all tracked workflow descriptions

**Files:**
- Modify: `agents/skills/github-pr-master/SKILL.md`
- Modify: `agents/skills/github-pr-master/reference/review.md`
- Modify: `docs/superpowers/plans/2026-07-25-github-pr-ttsr-guard.md`
- Modify: `docs/superpowers/specs/2026-07-25-github-pr-ttsr-guard-design.md`
- Modify: `docs/superpowers/specs/2026-07-25-pr-merge-cleanup-design.md`
- Modify: `docs/superpowers/plans/2026-07-25-pr-merge-cleanup.md`

**Interfaces:**
- Consumes: the existing `pr_merge` behavior and current TTSR/ExtensionAPI guard wording.
- Produces: tracked documentation that names only the current command and accurately distinguishes check-only, apply, and thread-only modes.

- [ ] **Step 1: Update the original plan and design spec**

Rewrite migration-history sentences as current-state sentences. Use these exact semantic replacements:

```text
原有檢查命令改名並重構為 commands/pr_merge
→ commands/pr_merge 提供完整的 PR 檢查與受保護合併流程

不恢復已刪除的等待腳本
→ 維持 pr_merge 作為唯一的 PR 等待與合併入口

Move: 舊檢查命令 → commands/pr_merge
→ Modify: commands/pr_merge

git mv 舊檢查命令 commands/pr_merge
→ commands/pr_merge --help
```

Also change task outputs from “never call the removed command” to “use `pr_merge` for every PR check and merge operation”. Preserve the direct `gh pr merge` guard explanation, PR copy requirements, GitLab behavior, and validation evidence.

- [ ] **Step 2: Update the cleanup spec and plan wording**

Remove legacy command names from the two new cleanup documents after implementation. Keep the decisions intact by referring to “舊檢查命令” or “舊等待腳本” where historical context is needed, and keep `.delete/commands/` as the archive destination.

- [ ] **Step 3: Verify the active documentation contract**

Read the final `SKILL.md` and `reference/review.md` sections covering command usage. Confirm they state:

```text
pr_merge                  # check-only, emits a four-character hash
pr_merge --apply <hash>   # reruns checks, then may merge
pr_merge --list           # thread-only, no wait or merge
pr_merge --resolve <ID>   # thread-only, no wait or merge
```

- [ ] **Step 4: Commit documentation changes**

```bash
git add agents/skills/github-pr-master/SKILL.md \
  agents/skills/github-pr-master/reference/review.md \
  docs/superpowers/plans/2026-07-25-github-pr-ttsr-guard.md \
  docs/superpowers/specs/2026-07-25-github-pr-ttsr-guard-design.md \
  docs/superpowers/specs/2026-07-25-pr-merge-cleanup-design.md \
  docs/superpowers/plans/2026-07-25-pr-merge-cleanup.md
git commit -m "docs: 統一 pr merge 流程說明"
```

Only the six listed documentation files may be staged.

---

### Task 3: Verify references and behavior

**Files:**
- Test: `commands/tests/test_pr_merge.py`
- Verify: `commands/pr_merge`, active skill/reference, tracked plan/spec files

**Interfaces:**
- Consumes: the archived command, updated module docstring, and rewritten documentation.
- Produces: evidence that no active tracked workflow points at the retired command or waiting script, and that `pr_merge` behavior is unchanged.

- [ ] **Step 1: Search active tracked paths for stale operational references**

Search these paths with the repository search tool: `agents/skills`, `commands/pr_merge`, `commands/tests`, `docs/superpowers/plans`, `docs/superpowers/specs`, `omp/agent/extensions`, and `omp/agent/rules`. The legacy command name and waiting-script filename must return no matches. References to direct `gh pr merge` may remain only in guard explanations, tests, and the protected implementation path.

- [ ] **Step 2: Run the focused contract tests**

```bash
python3 -m unittest commands.tests.test_pr_merge -v
```

Expected: 34 tests, all `OK`.

- [ ] **Step 3: Smoke-test the executable help**

```bash
commands/pr_merge --help
```

Expected: exit `0` and the complete current option set is printed.

- [ ] **Step 4: Confirm the archive boundary and user changes**

```bash
test ! -e commands/pr_check
test -f .delete/commands/pr_check
git status --short --branch
```

Expected: archive checks pass; no unrelated pre-existing files are staged; `omp/wt/` remains untouched.

- [ ] **Step 5: Final review**

Review the diff for only the docstring, active/tracked documentation, new cleanup plan/spec records, and the archived untracked command. Do not reset or stage unrelated user changes.
