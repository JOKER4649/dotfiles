// 為 PR 建立/編輯提供流程提醒，並在直接合併前阻止 bash 工具呼叫。

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

/** 匹配 PR 建立或編輯命令，避免 gh preview 等其他命令誤觸發。 */
export const GH_PR_CREATE_EDIT_RE = /\bgh\s+pr\s+(?:create|edit)\b/;

/** 匹配正規化後的直接 gh pr merge 命令。 */
export const GH_PR_MERGE_RE = /\bgh\s+pr\s+merge\b/;

const ANSI_C_SIMPLE_ESCAPES: Record<string, string> = {
  a: "\u0007",
  b: "\b",
  e: "\u001b",
  E: "\u001b",
  f: "\f",
  n: "\n",
  r: "\r",
  t: "\t",
  v: "\v",
  "\\": "\\",
  "'": "'",
  '"': '"',
};

function hexDigitValue(char: string | undefined): number | undefined {
  if (char === undefined) return undefined;
  if (char >= "0" && char <= "9") return char.charCodeAt(0) - 48;
  if (char >= "a" && char <= "f") return char.charCodeAt(0) - 87;
  if (char >= "A" && char <= "F") return char.charCodeAt(0) - 55;
  return undefined;
}

function decodeAnsiCQuote(
  command: string,
  start: number,
): { value: string; end: number } | undefined {
  let value = "";

  for (let i = start + 2; i < command.length; i += 1) {
    const char = command[i];
    if (char === "'") return { value, end: i };
    if (char !== "\\") {
      value += char;
      continue;
    }

    const next = command[i + 1];
    if (next === undefined) {
      value += "\\";
      continue;
    }
    if (next === "\n") {
      i += 1;
      continue;
    }

    const simpleEscape = ANSI_C_SIMPLE_ESCAPES[next];
    if (simpleEscape !== undefined) {
      value += simpleEscape;
      i += 1;
      continue;
    }

    if (next === "x") {
      let code = 0;
      let digits = 0;
      for (let offset = 0; offset < 2; offset += 1) {
        const digit = hexDigitValue(command[i + 2 + offset]);
        if (digit === undefined) break;
        code = code * 16 + digit;
        digits += 1;
      }
      if (digits > 0) {
        value += String.fromCodePoint(code);
        i += digits + 1;
        continue;
      }
    }

    if (next === "u" || next === "U") {
      const width = next === "u" ? 4 : 8;
      let code = 0;
      let valid = true;
      for (let offset = 0; offset < width; offset += 1) {
        const digit = hexDigitValue(command[i + 2 + offset]);
        if (digit === undefined) {
          valid = false;
          break;
        }
        code = code * 16 + digit;
      }
      if (valid && code <= 0x10ffff) {
        value += String.fromCodePoint(code);
        i += width + 1;
        continue;
      }
    }

    if (next >= "0" && next <= "7") {
      let code = 0;
      let digits = 0;
      for (; digits < 3; digits += 1) {
        const digit = command[i + 1 + digits];
        if (digit < "0" || digit > "7") break;
        code = code * 8 + Number(digit);
      }
      value += String.fromCodePoint(code);
      i += digits;
      continue;
    }

    // Bash removes the backslash for an unrecognised ANSI-C escape.
    value += next;
    i += 1;
  }

  return undefined;
}

/**
 * 將 bash 常見的等價寫法化為可供 guard 比對的最小形式。
 *
 * 這不是完整 shell parser: 只移除引號、保留其內容，並解開反斜線
 * escape；反斜線接換行則移除，對應 shell 的續行語意。ANSI-C 引號的
 * 常見數值 escape 也在此解碼，避免可執行的 `\x65` 等形式繞過 guard。
 */
function normalizeShellCommand(command: string): string {
  let normalized = "";

  for (let i = 0; i < command.length; i += 1) {
    const char = command[i];
    if (char === "$" && command[i + 1] === "'") {
      const decoded = decodeAnsiCQuote(command, i);
      if (decoded !== undefined) {
        normalized += decoded.value;
        i = decoded.end;
        continue;
      }
    }
    // Locale quoted token: `$"merge"` has a sigil before the quote.
    if (
      char === "$" &&
      (command[i + 1] === "'" || command[i + 1] === '"')
    ) {
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
