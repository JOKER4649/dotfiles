// 為 PR 建立/編輯提供流程提醒，並在直接合併前阻止 bash 工具呼叫。

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

/** 匹配 PR 建立或編輯命令，避免 gh preview 等其他命令誤觸發。 */
export const GH_PR_CREATE_EDIT_RE = /\bgh\s+pr\s+(?:create|edit)\b/;

/** 匹配正規化後的直接 gh pr merge 命令。 */
export const GH_PR_MERGE_RE = /\bgh\s+pr\s+merge\b/;

/**
 * 將 bash 常見的等價寫法化為可供 guard 比對的最小形式。
 *
 * 這不是完整 shell parser: 只移除引號、保留其內容，並解開反斜線
 * escape；反斜線接換行則移除，對應 shell 的續行語意。
 */
function normalizeShellCommand(command: string): string {
  let normalized = "";

  for (let i = 0; i < command.length; i += 1) {
    const char = command[i];
    // ANSI-C quoted token: `$'merge'` has a sigil before the quote.
    // Drop both delimiters so its content remains a comparable command token.
    if (char === "$" && command[i + 1] === "'") {
      i += 1;
      continue;
    }
    if (char === "\\") {
      const next = command[i + 1];
      if (next === "\n") {
        i += 1;
        continue;
      }
      if (next === "\r") {
        i += command[i + 2] === "\n" ? 2 : 1;
        continue;
      }
      if (next !== undefined) {
        normalized += next;
        i += 1;
        continue;
      }
    }

    if (char !== "'" && char !== '"') {
      normalized += char;
    }
  }

  return normalized;
}

export const GH_PR_CREATE_EDIT_REMINDER =
  "提醒：PR 建立或編輯完成，請重新讀取 `skill://github-pr-master`，確認標題、內文與驗證方式符合流程。";

export const GH_PR_MERGE_BLOCK_REASON =
  "禁止直接執行 `gh pr merge`；請先使用 `pr_merge` 完成檢查，再使用輸出的短 hash 執行 `pr_merge --apply <hash>`。";

interface TextChunk {
  type: string;
  text?: string;
  [key: string]: unknown;
}

export default function (pi: ExtensionAPI): void {
  pi.on("tool_call", async (event) => {
    if (
      event.toolName === "bash" &&
      GH_PR_MERGE_RE.test(
        normalizeShellCommand(String(event.input?.command ?? "")),
      )
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
}
