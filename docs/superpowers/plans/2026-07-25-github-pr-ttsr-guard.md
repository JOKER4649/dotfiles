# GitHub PR TTSR 與 pr_merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 `github-pr-master` 的 PR 流程改成 create/edit 提醒、direct merge 硬阻擋，並以 `pr_merge --apply <hash>` 作為完成所有檢查後的唯一 agent merge 入口。

**Architecture:** 全域 TTSR 在模型生成 direct `gh pr merge` 時提供前置提醒；全域 ExtensionAPI `tool_call` 在工具執行前永久阻止 direct merge，`tool_result` 只對 create/edit 追加品質提醒。`commands/pr_merge` 提供完整的 PR 定位、快速 mergeability 篩選、CI/kilo fail-fast 等待、review threads 檢查、最終 mergeability 重查與短 hash 輸出；只有 `--apply <hash>` 通過同一套重驗證後才呼叫 `gh pr merge`。

**Tech Stack:** Python 3.11、PEP 723 `uv run --script`、Typer、GitHub CLI (`gh`)、GitHub GraphQL review threads、TypeScript、Bun、omp TTSR Markdown rules。

## Global Constraints

- 維持 `pr_merge` 作為唯一的 PR 等待與合併入口。
- `pr_merge` 預設只檢查；只有 `--apply <hash>` 能進入真正 merge。
- 第二步只拒絕已確認的 `mergeable == CONFLICTING` 或 `mergeStateStatus == DIRTY`；CI 尚未完成的 `BLOCKED`、`UNSTABLE`、`UNKNOWN`、`BEHIND` 先進入等待。
- CI、kilo 或 review threads 可確定失敗時立即退出；不能因等待其他項目而延遲已知失敗。
- CI/kilo/threads 完成後必須再次確認 `mergeStateStatus` 是 `CLEAN` / `HAS_HOOKS` 且 `mergeable` 是 `MERGEABLE`。
- 短 hash 是 `md5(updatedAt, usedforsecurity=False).hexdigest()[:4]`，只作防止 agent 憑印象執行的確認碼，不是安全憑證。
- 直接 `gh pr merge` 必須由 ExtensionAPI block；`pr_merge` 內部的 `gh pr merge` 只在自身檢查通過後執行。
- 不執行真實 PR merge 作為驗證；所有 apply 測試使用 mock / fake `gh`。
- 每個任務完成後建立獨立 commit；不要把其他工作區變更加入 commit。

---

## File Map

| 檔案 | 責任 | 變更 |
|---|---|---|
| `commands/pr_merge` | 全域 PR 檢查與 merge 命令 | 提供完整主流程、介面與退出碼 |
| `commands/tests/test_pr_merge.py` | `pr_merge` 純邏輯契約測試 | 新增標準庫 `unittest` 測試 |
| `omp/agent/rules/github-pr-master-merge.md` | 全域 TTSR 前置提醒 | 新增規則 |
| `omp/agent/extensions/github-pr-master-reminder.ts` | agent tool-call guard 與 create/edit reminder | 修改事件與 regex 分工 |
| `agents/skills/github-pr-master/SKILL.md` | PR skill 主流程 | 將檢查／合併指令改成 `pr_merge` |
| `agents/skills/github-pr-master/reference/review.md` | review 等待、thread 操作說明 | 改名、補充 hash/apply 流程 |

---

### Task 1: Rename and refactor the PR command

**Files:**
- Modify: `commands/pr_merge`
- Create: `commands/tests/test_pr_merge.py`

**Interfaces:**
- Consumes: existing `_gh_pr_view`, `_gh_graphql`, `_wait`, `_fetch_threads`, `_expand_resolve_ids`, and current `gh pr view --json statusCheckRollup,number,url,headRefName,baseRefName` flow.
- Produces: executable `commands/pr_merge`; importable pure helpers `confirmation_hash(updated_at: str) -> str`, `fast_mergeability_error(view: Mapping[str, Any]) -> str | None`, `final_mergeability_error(view: Mapping[str, Any]) -> str | None`, and a check result carrying the target view plus confirmation hash.

- [ ] **Step 1: Move the executable without changing behavior**

Run:

```bash
commands/pr_merge --help
```

Keep the existing PEP 723 metadata, shebang, executable bit, and Typer dependency. Confirm the module docstring and all self-references describe the current `pr_merge` contract; do not modify skill files in this task.

- [ ] **Step 2: Add deterministic pure helpers and tests first**

In `commands/pr_merge`, add:

```python
def confirmation_hash(updated_at: str) -> str:
    return hashlib.md5(
        updated_at.encode(), usedforsecurity=False
    ).hexdigest()[:4]


def fast_mergeability_error(view: Mapping[str, Any]) -> str | None:
    if (view.get("state") or "").upper() != "OPEN":
        return f"PR 不是 OPEN 狀態: {view.get('state') or 'unknown'}"
    if view.get("isDraft"):
        return "PR 仍是 draft，不能合併"
    if (view.get("mergeable") or "").upper() == "CONFLICTING":
        return "PR 存在已確認的合併衝突"
    if (view.get("mergeStateStatus") or "").upper() == "DIRTY":
        return "PR 的 mergeStateStatus 為 DIRTY，存在合併衝突"
    return None


def final_mergeability_error(view: Mapping[str, Any]) -> str | None:
    if (error := fast_mergeability_error(view)) is not None:
        return error
    status = (view.get("mergeStateStatus") or "").upper()
    mergeable = (view.get("mergeable") or "").upper()
    if status not in {"CLEAN", "HAS_HOOKS"}:
        return f"PR 尚不可合併，mergeStateStatus={status or 'unknown'}"
    if mergeable != "MERGEABLE":
        return f"PR 尚不可合併，mergeable={mergeable or 'unknown'}"
    return None
```

The implementation may preserve project comments and existing naming style, but the acceptance contract is exact: fast screening allows pending statuses; final screening allows only `CLEAN` / `HAS_HOOKS` plus `MERGEABLE`.

Create `commands/tests/test_pr_merge.py` with standard-library `unittest` and an extensionless-module loader. Cover these observable cases:

```python
def test_confirmation_hash_is_stable(self):
    self.assertEqual(
        confirmation_hash("2026-07-25T00:00:00Z"),
        "b08e",
    )


def test_fast_screening_allows_pending_ci_states(self):
    for state in ("BLOCKED", "UNSTABLE", "UNKNOWN", "BEHIND"):
        with self.subTest(state=state):
            view = {"state": "OPEN", "isDraft": False,
                    "mergeStateStatus": state, "mergeable": "UNKNOWN"}
            self.assertIsNone(fast_mergeability_error(view))


def test_fast_screening_rejects_confirmed_conflicts(self):
    dirty = {"state": "OPEN", "isDraft": False,
             "mergeStateStatus": "DIRTY", "mergeable": "CONFLICTING"}
    self.assertIn("衝突", fast_mergeability_error(dirty))


def test_final_screening_requires_mergeable_clean_state(self):
    view = {"state": "OPEN", "isDraft": False,
            "mergeStateStatus": "BLOCKED", "mergeable": "MERGEABLE"}
    self.assertIsNotNone(final_mergeability_error(view))
```

- [ ] **Step 3: Expand the PR view query and implement fast screening**

Change the first `gh pr view` field set to include:

```text
number,url,state,isDraft,headRefName,baseRefName,mergeStateStatus,mergeable,updatedAt,statusCheckRollup
```

Run `fast_mergeability_error` immediately after resolving the PR. A pending CI state must proceed to `_wait`; only non-OPEN/draft/confirmed-conflict states exit before waiting.

- [ ] **Step 4: Make CI and kilo waiting fail fast**

Change the check summary helper to expose a failure boolean before all checks finish:

```python
def _summarise_checks(
    rollup: list[dict],
) -> tuple[str, bool, bool, bool]:
    """回傳 (摘要, 全部完成, 全部成功, 已知失敗)。"""
```

Inside `_wait`:

1. Split ordinary CI and kilo exactly as the current command does.
2. After each poll, if `ci_failed` is true, print the CI summary and raise `typer.Exit(1)` immediately.
3. If kilo is completed and failed, print its status and raise `typer.Exit(1)` immediately.
4. Only sleep when no failure is known and at least one required check is still pending.
5. Preserve timeout exit code `2` and `--no-kilo` behavior.

Do not inspect review threads after a known CI/kilo failure; the failure stage must be the only result of that invocation.

- [ ] **Step 5: Implement explicit thread modes and full check mode**

Keep `--list` and repeatable `--resolve` as auxiliary modes after the rename:

- `--list`: resolve the target and print unresolved threads only; no CI wait and no merge.
- `--resolve`: resolve full thread IDs or `#N` indexes; no CI wait and no merge.
- `--apply`, `--list`, and `--resolve` are mutually exclusive.

The default path must:

1. Resolve the target PR.
2. Run fast screening.
3. Wait for CI/kilo with fail-fast behavior.
4. Fetch unresolved threads; print them and exit `1` if any exist.
5. Re-fetch `mergeStateStatus`, `mergeable`, and `updatedAt`.
6. Run `final_mergeability_error`; exit `1` without a hash if it fails.
7. Print the URL, branch direction, `PR 可合併`, four-character hash, and the exact apply form.

- [ ] **Step 6: Implement `--apply <hash>` and merge strategy flags**

Add these Typer options:

```python
apply_hash: Annotated[
    str | None,
    typer.Option("--apply", help="重驗證後依四碼確認碼執行 merge"),
] = None
merge: Annotated[bool, typer.Option("--merge")] = False
squash: Annotated[bool, typer.Option("--squash")] = False
rebase: Annotated[bool, typer.Option("--rebase")] = False
delete_branch: Annotated[
    bool,
    typer.Option("--delete-branch", help="merge 後刪除本地與遠端 branch"),
] = False
```

Validate that at most one strategy flag is selected. In apply mode:

1. Run the exact default check path again, including final mergeability and fresh `updatedAt`.
2. Compare `apply_hash.lower()` with `confirmation_hash(updated_at)`. Reject non-four-hex input and mismatches with exit code `1`; print the current valid command but do not call `gh pr merge`.
3. Build `gh pr merge [target]` and append exactly one selected strategy, `--delete-branch` when requested, then run it through the existing `_run_gh` wrapper.
4. Propagate a failed `gh pr merge` as an error and never print success when the subprocess fails.
5. Do not pass `--admin` or `--auto`; the command’s own checks must not be bypassed by a merge flag.

- [ ] **Step 7: Add command-level regression tests**

Extend `commands/tests/test_pr_merge.py` with mocked subprocess scenarios:

- An initial view with `mergeStateStatus=DIRTY` must exit before any status polling.
- A rollup containing a completed failed check must exit `1` and make zero further polling calls.
- An unresolved review thread must exit `1` and never call `gh pr merge`.
- A final mergeability state of `BLOCKED` must exit `1` and never emit an apply command.
- `--apply dead` must not call `gh pr merge`.
- A successful mocked check plus matching `b08e` timestamp must call exactly one `gh pr merge` command; use a fake `gh` result rather than a real repository.

Use `unittest.mock.patch` around `_run_gh`, `_gh_graphql`, and `_fetch_threads`; assert commands and exit codes, not implementation-only line details.

- [ ] **Step 8: Run focused command verification and commit**

Run:

```bash
python3 -m unittest commands.tests.test_pr_merge -v
commands/pr_merge --help
```

Expected: all tests pass; help shows `--apply`, `--list`, `--resolve`, timeout/interval, kilo selection, and merge strategy flags. Commit only the moved command and its tests:

```bash
git add commands/pr_merge commands/tests/test_pr_merge.py
git commit -m "feat: 將 pr check 收斂為受確認碼保護的 pr merge"
```

---

### Task 2: Add TTSR and hard merge guard

**Files:**
- Create: `omp/agent/rules/github-pr-master-merge.md`
- Modify: `omp/agent/extensions/github-pr-master-reminder.ts`

**Interfaces:**
- Consumes: `gh pr` command strings from `tool:bash` and the existing `ExtensionAPI` event bus.
- Produces: one TTSR reminder rule and extension behavior that advises create/edit but blocks direct merge.

- [ ] **Step 1: Add the project-tracked global rule file**

Create `omp/agent/rules/github-pr-master-merge.md` with this frontmatter and body:

```markdown
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
```

The rule must not use `interruptMode: never`; the purpose is to interrupt the direct model-generated tool call before execution and send the model through the command flow.

- [ ] **Step 2: Split existing extension regexes and events**

Replace the broad `GH_PR_RE` / generic reminder behavior with explicit exports:

```typescript
export const GH_PR_CREATE_EDIT_RE = /\bgh\s+pr\s+(?:create|edit)\b/;
export const GH_PR_MERGE_RE = /\bgh\s+pr\s+merge\b/;

export const GH_PR_CREATE_EDIT_REMINDER =
  "提醒：PR 建立或編輯完成，請重新讀取 `skill://github-pr-master`，確認標題、內文與驗證方式符合流程。";

export const GH_PR_MERGE_BLOCK_REASON =
  "禁止直接執行 `gh pr merge`；請先使用 `pr_merge` 完成檢查，再使用輸出的短 hash 執行 `pr_merge --apply <hash>`。";
```

Register both handlers in the same default factory:

```typescript
pi.on("tool_call", async (event) => {
  if (
    event.toolName === "bash" &&
    GH_PR_MERGE_RE.test(String(event.input?.command ?? ""))
  ) {
    return { block: true, reason: GH_PR_MERGE_BLOCK_REASON };
  }
});

pi.on("tool_result", async (event) => {
  if (event.toolName !== "bash" || event.isError) return;
  if (!GH_PR_CREATE_EDIT_RE.test(String(event.input?.command ?? ""))) return;

  const content = event.content as TextChunk[];
  return {
    content: [
      ...content,
      { type: "text", text: GH_PR_CREATE_EDIT_REMINDER },
    ],
  };
});
```

Keep the existing `TextChunk` shape and do not add a second extension module.

- [ ] **Step 3: Add extension contract tests and commit**

Use a Bun mock registration harness to import the extension and capture both handlers. Assert:

- successful `bash` `gh pr create` gets one reminder;
- successful `bash` `gh pr edit` gets one reminder;
- failed `bash` results get no reminder;
- `gh pr merge` `tool_call` returns `{ block: true, reason }`;
- `pr_merge --apply b08e` `tool_call` returns no block;
- `gh preview` does not match either path.

Run the harness without executing a real GitHub mutation. Then commit only the rule and extension:

```bash
git add omp/agent/rules/github-pr-master-merge.md omp/agent/extensions/github-pr-master-reminder.ts
git commit -m "feat: 用 ttsr 與 extension 守住 pr merge"
```

---

### Task 3: Update github-pr-master instructions

**Files:**
- Modify: `agents/skills/github-pr-master/SKILL.md`
- Modify: `agents/skills/github-pr-master/reference/review.md`

**Interfaces:**
- Consumes: the command contract from Task 1 and the guard behavior from Task 2.
- Produces: skill instructions that use `pr_merge` for every PR check and merge operation, while keeping direct `gh pr merge` prohibited for the agent.

- [ ] **Step 1: Update the main skill flow**

In `SKILL.md`:

- Use `pr_merge` for every workflow reference.
- State that `pr_merge` defaults to check-only and prints a four-character confirmation hash.
- State that actual merge requires `pr_merge --apply <hash>` and an explicit merge strategy only when needed by `gh`.
- Add the direct-merge rule: never call `gh pr merge` from the agent; the global ExtensionAPI guard blocks it.
- Keep the existing GitLab behavior and all current PR title/body requirements unchanged.
- Keep the completion definition focused on CI, no conflicts, kilo result, resolved threads, Chinese intent, and no temporary files.

- [ ] **Step 2: Rewrite the review command reference**

In `reference/review.md`:

- Rename the waiting-tool heading and examples to `pr_merge`.
- Document default check mode: current cwd/branch, wait for CI/kilo, fail on unresolved threads, final mergeability check, hash output.
- Document `pr_merge --list` and `pr_merge --resolve <ID>` as thread-only auxiliary modes.
- Replace the old merge instruction with:

```text
pr_merge
# 確認輸出中的四碼 hash 後
pr_merge --apply <hash> --squash   # 或 --merge / --rebase
```

- Explicitly state that direct `gh pr merge` is prohibited and that `--apply` reruns the checks before invoking GitHub.
- Preserve the existing response principles for accepting, rejecting, tracking, and resolving AI review comments.

- [ ] **Step 3: Verify references and commit**

Search only the relevant tracked paths:

```text
pattern: pr_merge|gh pr merge
paths: agents/skills/github-pr-master; commands; omp/agent/extensions; omp/agent/rules
```

Expected: all operational PR instructions use `pr_merge`; direct `gh pr merge` appears only in the guard explanation and command implementation, never as an agent instruction. Commit only the two skill files:

```bash
git add agents/skills/github-pr-master/SKILL.md agents/skills/github-pr-master/reference/review.md
git commit -m "docs: 改用 pr merge 完成 GitHub PR 流程"
```

---

### Task 4: Integrated safe verification

**Files:**
- No new files.
- Read-only verification of the Task 1–3 changes.

**Interfaces:**
- Consumes: committed command, rule, extension, and skill contract.
- Produces: evidence that the runtime discovers the rule, hooks block the correct tool call, command check/apply gates behave as specified, and no real merge occurs.

- [ ] **Step 1: Run focused Python verification**

Run:

```bash
python3 -m unittest commands.tests.test_pr_merge -v
commands/pr_merge --help
```

Expected: all unit tests pass; help is non-interactive and includes check/apply, PR selection, timeout/interval, kilo, thread, and strategy options.

- [ ] **Step 2: Verify TTSR discovery through omp**

Run the omp extensions listing command from the TTSR documentation:

```bash
omp -p '/extensions'
```

Expected: `github-pr-master-merge` is listed with `tool:bash` scope and the global extension remains loadable. Do not invoke any real `--apply` command.

- [ ] **Step 3: Run extension mock smoke test**

Import `omp/agent/extensions/github-pr-master-reminder.ts` with Bun and register a mock `tool_call` / `tool_result` bus. Exercise `gh pr create`, `gh pr edit`, `gh pr merge`, `pr_merge --apply b08e`, `gh preview`, and an error result. Expected: create/edit reminders only on successful results; direct merge blocks; `pr_merge` passes.

- [ ] **Step 4: Run read-only GitHub query smoke test**

Against the read-only public PR `https://github.com/TaiwanTA/g6/pull/431`, run:

```bash
commands/pr_merge --list --pr https://github.com/TaiwanTA/g6/pull/431
```

Expected: it resolves the target and lists or reports zero unresolved threads without waiting or mutating anything. Do not use `--apply`.

- [ ] **Step 5: Review final diff boundaries**

Confirm only the following intended files are changed relative to the implementation commits:

```text
commands/pr_merge
commands/tests/test_pr_merge.py
omp/agent/rules/github-pr-master-merge.md
omp/agent/extensions/github-pr-master-reminder.ts
agents/skills/github-pr-master/SKILL.md
agents/skills/github-pr-master/reference/review.md
```

Do not reset or stage unrelated user changes. Report any pre-existing staged or unstaged work separately.
