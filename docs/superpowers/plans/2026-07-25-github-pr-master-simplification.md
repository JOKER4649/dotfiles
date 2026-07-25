# github-pr-master 指導縮減 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 GitHub PR skill 收斂成以 `pr_merge` 為唯一檢查與受保護合併入口，移除 agent 不需要自行維護的 PR 完成細節。

**Architecture:** 保留 `reference/create.md` 作為建立 PR 文案規範；縮短 `SKILL.md` 的主流程與 `reference/review.md` 的操作參考。所有檢查、review thread 與合併結果均由既有 `commands/pr_merge` 提供，文件只描述最短使用循環與 direct `gh pr merge` 邊界。

**Tech Stack:** Markdown、既有 PEP 723 Python/Typer 命令 `commands/pr_merge`、標準庫 `unittest`。

## Global Constraints

- 不修改 `commands/pr_merge` 的 CLI、檢查順序、hash 規則、退出碼或 GitHub API 行為。
- 不修改 `agents/skills/github-pr-master/reference/create.md`。
- 不修改 `omp/agent/rules/github-pr-master-merge.md` 或 `omp/agent/extensions/github-pr-master-reminder.ts`。
- 不觸碰主工作樹中與本任務無關的 `omp/wt/`、`omp/agent/blobs/` 或其他未追蹤資料。
- Agent-facing 合併流程只允許 `pr_merge` 與 `pr_merge --apply <hash>`；`gh pr merge` 的 guard 與 `pr_merge` 內部必要引用必須保留。

---

### Task 1: 收斂主 skill 的 PR 流程

**Files:**
- Modify: `agents/skills/github-pr-master/SKILL.md`

**Interfaces:**
- Consumes: `reference/create.md` 的既有 PR 文案規範與 `commands/pr_merge` 的既有 CLI 契約。
- Produces: 主 skill 只要求 agent 使用 `pr_merge` 完成檢查、thread 處理與合併。

- [ ] **Step 1: 保留 frontmatter 與建立 PR 入口**

保留 `name`，將 description 改為只描述建立 PR 與使用 `pr_merge` 完成受保護合併；保留 GitHub-only 適用範圍、非預設分支、繁體中文 PR 文案與 `reference/create.md` 連結。

- [ ] **Step 2: 移除重複的合併完成細節**

刪除現有「PR 完成的定義」、AI reviewer 分工、TODO 管理、`act` 與 MCP thread 工具清單。以以下流程取代：

```markdown
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
```

- [ ] **Step 3: 不改動建立 PR 規範**

確認本任務只修改 `SKILL.md`；`reference/create.md` 不加入新的完成條件或合併細節。

- [ ] **Step 4: 提交主 skill 變更**

```bash
git add agents/skills/github-pr-master/SKILL.md
git commit -m "refactor: 精簡 github pr skill"
```

---

### Task 2: 收斂 review reference 的操作說明

**Files:**
- Modify: `agents/skills/github-pr-master/reference/review.md`

**Interfaces:**
- Consumes: Task 1 的「`pr_merge` 是唯一入口」規則與既有 `pr_merge --list`、`pr_merge --resolve`、`pr_merge --apply <hash>` CLI。
- Produces: 一份只描述必要操作循環與禁止 direct merge 的短 reference。

- [ ] **Step 1: 改寫成單一 `pr_merge` 操作循環**

將文件內容收斂為以下結構：

```markdown
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
```

- [ ] **Step 2: 移除 agent 不需要的細節**

確認新文件不再列出 AI reviewer 名稱、輪詢秒數、timeout、退出碼、完整完成清單、通用 AI review 回應原則或替代的 MCP 合併入口。

- [ ] **Step 3: 提交 review reference 變更**

```bash
git add agents/skills/github-pr-master/reference/review.md
git commit -m "refactor: 簡化 pr merge review 指引"
```

---

### Task 3: 驗證文件邊界與既有命令

**Files:**
- Verify: `agents/skills/github-pr-master/SKILL.md`
- Verify: `agents/skills/github-pr-master/reference/review.md`
- Verify: `agents/skills/github-pr-master/reference/create.md`
- Verify: `commands/pr_merge`
- Verify: `commands/tests/test_pr_merge.py`

**Interfaces:**
- Consumes: Task 1–2 的文件內容與既有命令契約。
- Produces: 可證明文件已收斂且 `pr_merge` 行為未受影響的檢查結果。

- [ ] **Step 1: 確認 active guidance 只保留必要入口**

```bash
grep -nE 'pr_merge|gh pr merge' agents/skills/github-pr-master/SKILL.md agents/skills/github-pr-master/reference/review.md
grep -nE 'AI reviewer|gemini|kilo|退出碼|15 分鐘|30 秒|TODO 管理|PR 完成的定義' agents/skills/github-pr-master/SKILL.md agents/skills/github-pr-master/reference/review.md
```

Expected: 第一個命令只找到 `pr_merge` 操作與禁止 direct `gh pr merge` 的必要引用；第二個命令沒有匹配。

- [ ] **Step 2: 執行既有命令契約測試**

```bash
python3 -m unittest commands.tests.test_pr_merge -v
```

Expected: 所有既有測試通過，且沒有真實 GitHub merge。

- [ ] **Step 3: 確認 CLI 仍可載入**

```bash
commands/pr_merge --help
```

Expected: exit code `0`，並保留 `--apply`、`--list`、`--resolve`、timeout/interval、Kilo 選擇與 merge strategy 相關選項。

- [ ] **Step 4: 提交驗證完成的文件變更**

```bash
git status --short
```

Expected: 本任務只留下已提交的 skill/reference/spec/plan 變更；既有未追蹤工作樹與 blob 資料不被加入或修改。
