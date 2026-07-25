"""針對 commands/pr_merge 的契約測試。

pr_merge 是 PEP 723 uv-run script (沒有副檔名, 不在套件中), 因此測試
自行以 importlib 把 commands/pr_merge 動態掛進來。我們只替換 I/O 邊界
(_run_gh / _gh_pr_view / _gh_graphql / _fetch_threads / time.sleep),
並對純函式直接 assert。
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import subprocess
import typer
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable
from unittest import mock

# 解析 commands/pr_merge (無副檔名 PEP 723 script) 的路徑並掛入 sys.modules。
# 一般 spec_from_file_location 拒絕沒有 .py 副檔名的檔案, 因此改用
# SourceFileLoader 直掛; module 的 shebang 行不會被執行。
_COMMANDS_DIR = Path(__file__).resolve().parents[1]
_PR_MERGE_PATH = _COMMANDS_DIR / "pr_merge"
_LOADER = importlib.machinery.SourceFileLoader(
    "pr_merge_under_test", str(_PR_MERGE_PATH)
)
_SPEC = importlib.util.spec_from_loader("pr_merge_under_test", _LOADER)
if _SPEC is None:  # pragma: no cover - 防禦性
    raise RuntimeError(f"無法載入 {_PR_MERGE_PATH}")
pr_merge = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = pr_merge
_LOADER.exec_module(pr_merge)


def _completed(
    args: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=args, returncode=returncode, stdout=stdout, stderr=stderr
    )


class PureHelperTests(unittest.TestCase):
    def test_confirmation_hash_is_stable(self) -> None:
        self.assertEqual(
            pr_merge.confirmation_hash("2026-07-25T00:00:00Z"),
            "b08e",
        )

    def test_fast_screening_allows_pending_ci_states(self) -> None:
        for state in ("BLOCKED", "UNSTABLE", "UNKNOWN", "BEHIND"):
            with self.subTest(state=state):
                view = {
                    "state": "OPEN",
                    "isDraft": False,
                    "mergeStateStatus": state,
                    "mergeable": "UNKNOWN",
                }
                self.assertIsNone(pr_merge.fast_mergeability_error(view))

    def test_fast_screening_rejects_confirmed_conflicts(self) -> None:
        dirty = {
            "state": "OPEN",
            "isDraft": False,
            "mergeStateStatus": "DIRTY",
            "mergeable": "CONFLICTING",
        }
        self.assertIn("衝突", pr_merge.fast_mergeability_error(dirty))

    def test_final_screening_requires_mergeable_clean_state(self) -> None:
        view = {
            "state": "OPEN",
            "isDraft": False,
            "mergeStateStatus": "BLOCKED",
            "mergeable": "MERGEABLE",
        }
        self.assertIsNotNone(pr_merge.final_mergeability_error(view))


class _FlowRunner:
    """執行 pr_merge.main 並把外部 I/O 換成可預期佇列。

    返回 (exit_code, stdout, stderr, gh_merge_calls)。
    """

    def __init__(
        self,
        pr_view_payloads: list[dict[str, Any]],
        threads_payloads: list[list[dict[str, Any]]] | None = None,
        graphql_payloads: list[dict[str, Any]] | None = None,
        gh_merge_returncode: int = 0,
    ) -> None:
        self.pr_view_payloads = list(pr_view_payloads)
        self.threads_payloads = list(threads_payloads or [])
        self.graphql_payloads = list(graphql_payloads or [])
        self.gh_merge_returncode = gh_merge_returncode
        self.pr_view_calls: list[list[str]] = []
        self.gh_merge_calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> tuple[int, str, str]:
        pr_iter: Any = iter(self.pr_view_payloads)
        threads_iter: Any = iter(self.threads_payloads)
        graphql_iter: Any = iter(self.graphql_payloads)
        gh_merge_calls = self.gh_merge_calls

        def fake_run_gh(args: list[str], *, check: bool = True):
            if args[:3] == ["gh", "pr", "view"]:
                self.pr_view_calls.append(args)
                try:
                    payload = next(pr_iter)
                except StopIteration:
                    raise AssertionError(
                        f"gh pr view called more times than expected: {args}"
                    )
                return _completed(args, 0, json.dumps(payload))
            if args[:3] == ["gh", "pr", "merge"]:
                gh_merge_calls.append(args)
                return _completed(
                    args,
                    self.gh_merge_returncode,
                    "",
                    "" if self.gh_merge_returncode == 0 else "merge failed",
                )
            # 其他一律回傳空 JSON 防止下游 NoneType 爆炸
            return _completed(args, 0, "{}")

        def fake_gh_graphql(query: str, **variables):
            try:
                return next(graphql_iter)
            except StopIteration:
                raise AssertionError(
                    f"gh api graphql called more times than expected: vars={variables}"
                )

        def fake_fetch_threads(owner: str, name: str, number: int):
            try:
                return next(threads_iter)
            except StopIteration:
                raise AssertionError("fetch_threads called more times than expected")

        stdout = io.StringIO()
        stderr = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["pr_merge", *argv]
        try:
            with mock.patch.object(pr_merge, "_run_gh", side_effect=fake_run_gh), \
                 mock.patch.object(pr_merge, "_gh_graphql", side_effect=fake_gh_graphql), \
                 mock.patch.object(pr_merge, "_fetch_threads", side_effect=fake_fetch_threads), \
                 mock.patch.object(pr_merge.time, "sleep", side_effect=lambda s: None), \
                 redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    typer.run(pr_merge.main)
                    code = 0
                except (SystemExit, RuntimeError) as exc:
                    # typer.Exit extends click.exceptions.Exit (RuntimeError);
                    # exit_code 在 .exit_code 而非 .code
                    raw_code = getattr(exc, "exit_code", None) or getattr(exc, "code", None)
                    code = raw_code if isinstance(raw_code, int) else 1
        finally:
            sys.argv = old_argv
        return code, stdout.getvalue(), stderr.getvalue()


# ---- 通用構造 helper ----

def _resolved_view() -> dict[str, Any]:
    """只含 number/url 的「解析目標」view。"""
    return {"number": 7, "url": "https://github.com/o/r/pull/7"}


def _ci_view(
    *,
    ci_conclusion: str = "SUCCESS",
    include_kilo: bool = True,
    kilo_conclusion: str = "SUCCESS",
) -> dict[str, Any]:
    rollup: list[dict[str, Any]] = [
        {
            "__typename": "CheckRun",
            "name": "unit",
            "status": "COMPLETED",
            "conclusion": ci_conclusion,
        }
    ]
    if include_kilo:
        rollup.append(
            {
                "__typename": "CheckRun",
                "name": "Kilo Code Review",
                "status": "COMPLETED",
                "conclusion": kilo_conclusion,
            }
        )
    return {
        **_resolved_view(),
        "headRefName": "feat",
        "baseRefName": "main",
        "statusCheckRollup": rollup,
    }


def _fast_view(
    *,
    state: str = "OPEN",
    is_draft: bool = False,
    merge_state_status: str = "BLOCKED",
    mergeable: str = "UNKNOWN",
    updated_at: str = "2026-07-25T00:00:00Z",
) -> dict[str, Any]:
    """fast screening 用的 view: 包含狀態 / draft / mergeStateStatus / mergeable / updatedAt。"""
    return {
        **_resolved_view(),
        "headRefName": "feat",
        "baseRefName": "main",
        "state": state,
        "isDraft": is_draft,
        "mergeStateStatus": merge_state_status,
        "mergeable": mergeable,
        "updatedAt": updated_at,
    }


def _final_view(
    *,
    state: str = "OPEN",
    is_draft: bool = False,
    merge_state_status: str = "CLEAN",
    mergeable: str = "MERGEABLE",
    updated_at: str = "2026-07-25T00:00:00Z",
) -> dict[str, Any]:
    return {
        **_resolved_view(),
        "state": state,
        "isDraft": is_draft,
        "mergeStateStatus": merge_state_status,
        "mergeable": mergeable,
        "updatedAt": updated_at,
    }


def _unresolved_thread() -> dict[str, Any]:
    return {
        "id": "PRRT_abc",
        "isResolved": False,
        "isOutdated": False,
        "path": "src/x.py",
        "line": 10,
        "comments": {
            "nodes": [{"author": {"login": "kilo"}, "body": "fix"}]
        },
    }


def _fast_view_dirty() -> dict[str, Any]:
    return {
        **_resolved_view(),
        "state": "OPEN",
        "isDraft": False,
        "headRefName": "feat",
        "baseRefName": "main",
        "mergeStateStatus": "DIRTY",
        "mergeable": "CONFLICTING",
        "updatedAt": "2026-07-25T00:00:00Z",
    }


class CommandFlowTests(unittest.TestCase):
    """命令流程測試: 模擬 gh / GraphQL / threads, 驗證退出碼與執行序。"""

    def test_initial_dirty_view_skips_polling(self) -> None:
        # fast screening (DIRTY + CONFLICTING) 直接 reject, 不應進入 _wait。
        runner = _FlowRunner(
            pr_view_payloads=[_resolved_view(), _fast_view_dirty()]
        )
        code, _, _ = runner(argv=[])
        self.assertEqual(code, 1)
        self.assertEqual(runner.gh_merge_calls, [])
        self.assertEqual(len(runner.pr_view_calls), 2)

    # ---- Scenario tests from brief Step 7 ----


    def test_rollup_with_failed_check_exits_one_no_further_polls(self) -> None:
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(ci_conclusion="FAILURE", include_kilo=False),
            ]
        )
        code, stdout, _ = runner(argv=[])
        self.assertEqual(code, 1)
        # 不應出現 threads 列印 (因為 fail-fast 在 _wait 內退出, 不進入 threads 階段)
        self.assertNotIn("未解決 review threads", stdout)
        self.assertEqual(len(runner.pr_view_calls), 3)

    def test_unresolved_thread_blocks_merge(self) -> None:
        # CI/kilo 綠, threads 未解 → exit 1, 不呼叫 gh pr merge。
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(),
            ],
            threads_payloads=[[_unresolved_thread()]],
        )
        code, _, _ = runner(argv=[])
        self.assertEqual(code, 1)
        self.assertEqual(runner.gh_merge_calls, [])

    def test_final_blocked_state_does_not_emit_apply_command(self) -> None:
        # threads 已解, final mergeStateStatus=BLOCKED → exit 1, 不應印 apply。
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(merge_state_status="BLOCKED", mergeable="MERGEABLE"),
            ],
            threads_payloads=[[]],
        )
        code, stdout, _ = runner(argv=[])
        self.assertEqual(code, 1)
        self.assertNotIn("--apply", stdout)
        self.assertNotIn("PR 可合併", stdout)
        self.assertEqual(runner.gh_merge_calls, [])

    def test_apply_with_invalid_hash_does_not_call_merge(self) -> None:
        # --apply dead → exit 1, 不觸發 gh pr merge。
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(),
            ],
            threads_payloads=[[]],
        )
        code, _, _ = runner(argv=["--apply", "dead"])
        self.assertEqual(code, 1)
        self.assertEqual(runner.gh_merge_calls, [])

    def test_successful_apply_calls_merge_exactly_once(self) -> None:
        # happy path: 所有檢查綠, threads 已解, final CLEAN+MERGEABLE, hash b08e。
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(updated_at="2026-07-25T00:00:00Z"),
            ],
            threads_payloads=[[]],
        )
        code, _, _ = runner(argv=["--apply", "b08e"])
        self.assertEqual(code, 0)
        self.assertEqual(len(runner.gh_merge_calls), 1)
        merge_cmd = runner.gh_merge_calls[0]
        # 預設有 --merge (策略之一, 雖然這裡 apply 不帶策略時應該 default 不帶)
        # 規格只要求: 不帶 --admin/--auto, 帶目標
        self.assertNotIn("--admin", merge_cmd)
        self.assertNotIn("--auto", merge_cmd)
        self.assertIn("https://github.com/o/r/pull/7", merge_cmd)

    def test_apply_with_squash_strategy_passes_flag(self) -> None:
        # --squash 應該傳給 gh pr merge。
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(updated_at="2026-07-25T00:00:00Z"),
            ],
            threads_payloads=[[]],
        )
        code, _, _ = runner(argv=["--apply", "b08e", "--squash"])
        self.assertEqual(code, 0)
        self.assertEqual(len(runner.gh_merge_calls), 1)
        merge_cmd = runner.gh_merge_calls[0]
        self.assertIn("--squash", merge_cmd)
        self.assertNotIn("--merge", merge_cmd)
        self.assertNotIn("--rebase", merge_cmd)

    def test_apply_with_rebase_and_delete_branch(self) -> None:
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(updated_at="2026-07-25T00:00:00Z"),
            ],
            threads_payloads=[[]],
        )
        code, _, _ = runner(
            argv=["--apply", "b08e", "--rebase", "--delete-branch"]
        )
        self.assertEqual(code, 0)
        merge_cmd = runner.gh_merge_calls[0]
        self.assertIn("--rebase", merge_cmd)
        self.assertIn("--delete-branch", merge_cmd)

    def test_apply_with_conflicting_strategy_flags_exits_error(self) -> None:
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(updated_at="2026-07-25T00:00:00Z"),
            ],
            threads_payloads=[[]],
        )
        # --merge 與 --squash 同時: 應在解析階段拒絕 (exit != 0, 不呼叫 gh pr merge)
        code, _, _ = runner(argv=["--apply", "b08e", "--merge", "--squash"])
        self.assertNotEqual(code, 0)
        self.assertEqual(runner.gh_merge_calls, [])


if __name__ == "__main__":
    unittest.main()
