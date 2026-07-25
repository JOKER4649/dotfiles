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
import shlex
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

    def test_kilo_status_aggregates_pending_after_success(self) -> None:
        checks = [
            {
                "__typename": "CheckRun",
                "name": "Kilo Code Review",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "name": "Kilo Code Review (rerun)",
                "status": "IN_PROGRESS",
                "conclusion": None,
            },
        ]

        exists, done, failed, label = pr_merge._kilo_status(checks)

        self.assertTrue(exists)
        self.assertFalse(done)
        self.assertFalse(failed)
        self.assertIn("1/2", label)

    def test_kilo_status_reports_failure_after_success(self) -> None:
        checks = [
            {
                "__typename": "CheckRun",
                "name": "Kilo Code Review",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "name": "Kilo Code Review (rerun)",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
            },
        ]

        exists, done, failed, label = pr_merge._kilo_status(checks)

        self.assertTrue(exists)
        self.assertTrue(done)
        self.assertTrue(failed)
        self.assertIn("FAILURE", label)


    def test_print_threads_quotes_index_hint_for_shell(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            shown = pr_merge._print_threads([_unresolved_thread()])

        self.assertEqual(len(shown), 1)
        self.assertIn("pr_merge --resolve '#1'", output.getvalue())
        self.assertNotIn("pr_merge --resolve #1", output.getvalue())
    def test_print_threads_includes_explicit_target_in_index_hint(self) -> None:
        output = io.StringIO()
        target = "https://github.com/o/r/pull/7"
        with redirect_stdout(output):
            shown = pr_merge._print_threads([_unresolved_thread()], pr=target)

        self.assertEqual(len(shown), 1)
        self.assertIn(
            "pr_merge --pr https://github.com/o/r/pull/7 --resolve '#1'",
            output.getvalue(),
        )



class ReviewThreadTests(unittest.TestCase):
    def test_fetch_threads_paginates_and_aggregates_all_pages(self) -> None:
        pages = [
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [{"id": "thread-1", "isResolved": False}],
                                "pageInfo": {
                                    "hasNextPage": True,
                                    "endCursor": "cursor-1",
                                },
                            }
                        }
                    }
                }
            },
            {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "reviewThreads": {
                                "nodes": [{"id": "thread-2", "isResolved": True}],
                                "pageInfo": {
                                    "hasNextPage": False,
                                    "endCursor": None,
                                },
                            }
                        }
                    }
                }
            },
        ]
        calls: list[dict[str, Any]] = []

        def fake_graphql(query: str, **variables: Any) -> dict[str, Any]:
            calls.append({"query": query, **variables})
            return pages[len(calls) - 1]

        with mock.patch.object(pr_merge, "_gh_graphql", side_effect=fake_graphql):
            threads = pr_merge._fetch_threads("o", "r", 7)

        self.assertEqual([thread["id"] for thread in threads], ["thread-1", "thread-2"])
        self.assertEqual([call["cursor"] for call in calls], [None, "cursor-1"])
        self.assertIn("pageInfo", calls[0]["query"])
        self.assertIn("after: $cursor", calls[0]["query"])

    def test_fetch_threads_rejects_missing_graphql_shape(self) -> None:
        malformed = [
            (None, "response"),
            ({}, "data"),
            ({"data": {}}, "repository"),
            ({"data": {"repository": None}}, "repository"),
            ({"data": {"repository": {"pullRequest": None}}}, "pullRequest"),
            (
                {"data": {"repository": {"pullRequest": {"reviewThreads": None}}}},
                "reviewThreads",
            ),
            (
                {
                    "data": {
                        "repository": {
                            "pullRequest": {"reviewThreads": {"pageInfo": {}}}
                        }
                    }
                },
                "nodes",
            ),
            (
                {
                    "data": {
                        "repository": {
                            "pullRequest": {"reviewThreads": {"nodes": []}}
                        }
                    }
                },
                "pageInfo",
            ),
        ]

        for payload, missing_part in malformed:
            with self.subTest(missing_part=missing_part):
                output = io.StringIO()
                with mock.patch.object(
                    pr_merge, "_gh_graphql", return_value=payload
                ), redirect_stderr(output):
                    with self.assertRaises(typer.Exit) as raised:
                        pr_merge._fetch_threads("o", "r", 7)
                self.assertEqual(raised.exception.exit_code, 3)
                self.assertIn(missing_part, output.getvalue())



class GhBoundaryTests(unittest.TestCase):
    def test_pr_view_missing_gh_exits_three_without_traceback(self) -> None:
        output = io.StringIO()
        with mock.patch.object(
            pr_merge, "_run_gh", side_effect=FileNotFoundError(2, "gh not found")
        ), redirect_stderr(output):
            with self.assertRaises(typer.Exit) as raised:
                pr_merge._gh_pr_view(None, "number")

        self.assertEqual(raised.exception.exit_code, 3)
        self.assertIn("gh pr view 失敗", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_graphql_missing_gh_exits_three_without_traceback(self) -> None:
        output = io.StringIO()
        with mock.patch.object(
            pr_merge, "_run_gh", side_effect=OSError("gh unavailable")
        ), redirect_stderr(output):
            with self.assertRaises(typer.Exit) as raised:
                pr_merge._gh_graphql("query { viewer { login } }")

        self.assertEqual(raised.exception.exit_code, 3)
        self.assertIn("gh api graphql 失敗", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_graphql_top_level_errors_exit_three(self) -> None:
        output = io.StringIO()
        response = _completed(
            ["gh", "api", "graphql"],
            stdout=json.dumps({"errors": [{"message": "rate limit"}]}),
        )
        with mock.patch.object(pr_merge, "_run_gh", return_value=response), redirect_stderr(
            output
        ):
            with self.assertRaises(typer.Exit) as raised:
                pr_merge._gh_graphql("query { viewer { login } }")

        self.assertEqual(raised.exception.exit_code, 3)
        self.assertIn("rate limit", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_resolve_graphql_exit_three_is_not_downgraded(self) -> None:
        with mock.patch.object(
            pr_merge, "_gh_graphql", side_effect=typer.Exit(3)
        ):
            with self.assertRaises(typer.Exit) as raised:
                pr_merge._resolve_thread("PRRT_abc")

        self.assertEqual(raised.exception.exit_code, 3)



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
        gh_merge_error: BaseException | None = None,
        gh_merge_stdout: str = "",
        gh_merge_stderr: str | None = None,
        real_fetch_threads: bool = False,
    ) -> None:
        self.pr_view_payloads = list(pr_view_payloads)
        self.threads_payloads = list(threads_payloads or [])
        self.graphql_payloads = list(graphql_payloads or [])
        self.gh_merge_returncode = gh_merge_returncode
        self.gh_merge_error = gh_merge_error
        self.gh_merge_stdout = gh_merge_stdout
        self.gh_merge_stderr = gh_merge_stderr
        self.real_fetch_threads = real_fetch_threads
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
                if self.gh_merge_error is not None:
                    raise self.gh_merge_error
                stderr = (
                    self.gh_merge_stderr
                    if self.gh_merge_stderr is not None
                    else ("" if self.gh_merge_returncode == 0 else "merge failed")
                )
                return _completed(
                    args,
                    self.gh_merge_returncode,
                    self.gh_merge_stdout,
                    stderr,
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
            fetch_threads_patch = (
                mock.patch.object(
                    pr_merge, "_fetch_threads", wraps=pr_merge._fetch_threads
                )
                if self.real_fetch_threads
                else mock.patch.object(
                    pr_merge, "_fetch_threads", side_effect=fake_fetch_threads
                )
            )
            with mock.patch.object(pr_merge, "_run_gh", side_effect=fake_run_gh), \
                 mock.patch.object(pr_merge, "_gh_graphql", side_effect=fake_gh_graphql), \
                 fetch_threads_patch, \
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
    status_check_rollup: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """fast screening 用的 view: 包含狀態 / draft / mergeStateStatus / mergeable / updatedAt。"""
    view = {
        **_resolved_view(),
        "headRefName": "feat",
        "baseRefName": "main",
        "state": state,
        "isDraft": is_draft,
        "mergeStateStatus": merge_state_status,
        "mergeable": mergeable,
        "updatedAt": updated_at,
    }
    if status_check_rollup is not None:
        view["statusCheckRollup"] = status_check_rollup
    return view


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
        failed_rollup = [
            {
                "__typename": "CheckRun",
                "name": "unit",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
            }
        ]
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(status_check_rollup=failed_rollup),
            ]
        )
        code, stdout, _ = runner(argv=[])
        self.assertEqual(code, 1)
        # 初始 fast view 已含失敗 rollup, 不應再額外輪詢或進入 threads 階段。
        self.assertNotIn("未解決 review threads", stdout)
        self.assertEqual(len(runner.pr_view_calls), 2)

    def test_multiple_kilo_pending_after_success_does_not_ready(self) -> None:
        rollup = [
            {
                "__typename": "CheckRun",
                "name": "unit",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "name": "Kilo Code Review",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "name": "Kilo Code Review (rerun)",
                "status": "IN_PROGRESS",
                "conclusion": None,
            },
        ]
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(status_check_rollup=rollup),
            ]
        )

        code, stdout, _ = runner(argv=["--timeout", "0"])

        self.assertEqual(code, 2)
        self.assertIn("kilo:", stdout)
        self.assertNotIn("未解決 review threads", stdout)
        self.assertEqual(len(runner.pr_view_calls), 2)

    def test_multiple_kilo_failure_after_success_exits_immediately(self) -> None:
        rollup = [
            {
                "__typename": "CheckRun",
                "name": "unit",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "name": "Kilo Code Review",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "CheckRun",
                "name": "Kilo Code Review (rerun)",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
            },
        ]
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(status_check_rollup=rollup),
            ]
        )

        code, stdout, stderr = runner(argv=[])

        self.assertEqual(code, 1)
        self.assertIn("kilo:", stdout)
        self.assertIn("Kilo", stderr)
        self.assertNotIn("未解決 review threads", stdout)
        self.assertEqual(len(runner.pr_view_calls), 2)

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

    def test_thread_hint_includes_explicit_pr_in_default_flow(self) -> None:
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(),
            ],
            threads_payloads=[[_unresolved_thread()]],
        )
        code, stdout, _ = runner(argv=["--pr", "431"])

        self.assertEqual(code, 1)
        self.assertIn("pr_merge --pr 431 --resolve '#1'", stdout)
        self.assertEqual(runner.gh_merge_calls, [])

    def test_malformed_threads_exit_three_without_merge(self) -> None:
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(status_check_rollup=_ci_view()["statusCheckRollup"]),
                _final_view(),
            ],
            graphql_payloads=[{}],
            real_fetch_threads=True,
        )
        code, _, stderr = runner(argv=["--pr", "431", "--apply", "b08e"])

        self.assertEqual(code, 3)
        self.assertIn("gh api graphql", stderr)
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

    def test_apply_with_padded_hash_is_rejected(self) -> None:
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(updated_at="2026-07-25T00:00:00Z"),
            ],
            threads_payloads=[[]],
        )
        code, _, _ = runner(argv=["--apply", " b08e "])
        self.assertEqual(code, 1)
        self.assertEqual(runner.gh_merge_calls, [])

    def test_empty_apply_is_mutually_exclusive_with_resolve(self) -> None:
        runner = _FlowRunner(pr_view_payloads=[_resolved_view()])
        code, _, _ = runner(argv=["--apply", "", "--resolve", "PRRT_abc"])
        self.assertEqual(code, 3)
        self.assertEqual(runner.gh_merge_calls, [])

    def test_apply_hint_uses_declared_pr_option_and_is_typer_parseable(self) -> None:
        check_runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(updated_at="2026-07-25T00:00:00Z"),
            ],
            threads_payloads=[[]],
        )
        code, stdout, _ = check_runner(argv=[])
        self.assertEqual(code, 0)
        command_line = next(
            line.removeprefix("執行: ")
            for line in stdout.splitlines()
            if line.startswith("執行: ")
        )
        command_argv = shlex.split(command_line)
        self.assertEqual(command_argv[0], "pr_merge")
        self.assertIn("--pr", command_argv)
        self.assertEqual(
            command_argv[command_argv.index("--pr") + 1],
            "https://github.com/o/r/pull/7",
        )

        apply_runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(updated_at="2026-07-25T00:00:00Z"),
            ],
            threads_payloads=[[]],
        )
        parsed_code, _, _ = apply_runner(argv=command_argv[1:])
        self.assertEqual(parsed_code, 0)
        self.assertEqual(len(apply_runner.gh_merge_calls), 1)

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

    def test_merge_failure_preserves_stderr_stdout_and_returncode(self) -> None:
        merge_error = subprocess.CalledProcessError(
            7,
            ["gh", "pr", "merge"],
            output="stdout diagnostic",
            stderr="stderr diagnostic",
        )
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(updated_at="2026-07-25T00:00:00Z"),
            ],
            threads_payloads=[[]],
            gh_merge_error=merge_error,
        )
        code, stdout, stderr = runner(argv=["--apply", "b08e"])

        self.assertEqual(code, 7)
        self.assertIn("stderr diagnostic", stderr)
        self.assertIn("stdout diagnostic", stderr)
        self.assertIn("returncode=7", stderr)
        self.assertNotIn("✓ 已送出 merge", stdout)

    def test_missing_gh_during_merge_exits_three(self) -> None:
        runner = _FlowRunner(
            pr_view_payloads=[
                _resolved_view(),
                _fast_view(),
                _ci_view(),
                _final_view(updated_at="2026-07-25T00:00:00Z"),
            ],
            threads_payloads=[[]],
            gh_merge_error=FileNotFoundError(2, "gh not found"),
        )
        code, stdout, stderr = runner(argv=["--apply", "b08e"])

        self.assertEqual(code, 3)
        self.assertNotIn("✓ 已送出 merge", stdout)
        self.assertIn("gh pr merge 失敗", stderr)
        self.assertNotIn("Traceback", stderr)

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



class WaitTests(unittest.TestCase):
    def test_wait_clamps_sleep_to_remaining_deadline(self) -> None:
        now = [0.0]
        sleeps: list[float] = []
        pending = {
            "number": 7,
            "url": "https://github.com/o/r/pull/7",
            "headRefName": "feat",
            "baseRefName": "main",
            "statusCheckRollup": [
                {
                    "__typename": "CheckRun",
                    "name": "unit",
                    "status": "IN_PROGRESS",
                    "conclusion": None,
                }
            ],
        }

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        output = io.StringIO()
        with mock.patch.object(pr_merge, "_gh_pr_view", return_value=pending), \
             mock.patch.object(pr_merge.time, "time", side_effect=lambda: now[0]), \
             mock.patch.object(pr_merge.time, "sleep", side_effect=fake_sleep), \
             redirect_stdout(output), redirect_stderr(io.StringIO()):
            with self.assertRaises(typer.Exit) as raised:
                pr_merge._wait(
                    "431",
                    timeout=1,
                    interval=30,
                    kilo=False,
                    initial_view=pending,
                )

        self.assertEqual(raised.exception.exit_code, 2)
        self.assertEqual(sleeps, [1])

if __name__ == "__main__":
    unittest.main()
