# 專案概述

此倉庫用於備份與同步個人常用工具的設定檔。每個工具的設定以獨立子目錄管理。

## 專案結構

```
dotfiles/
├── commands/    # 自訂 CLI 命令（Python + typer，透過 mise PATH 注入）
├── link.py      # Symlink 管理腳本
├── mise/        # mise 開發工具版本管理器設定
├── opencode/    # OpenCode（AI 編碼助手）完整設定
├── starship/    # Starship 跨 shell 提示字元設定
└── zsh/         # Zsh shell 設定
```

## 慣例

- **目錄組織**：每個工具一個子目錄，目錄名即工具名稱

## 注意事項

- `opencode/` 內的 `node_modules/`、`package.json`、`bun.lock` 已被 `.gitignore` 排除，不應追蹤
- 新增工具設定時，必須完成以下三步：
  1. 建立以工具名稱命名的子目錄，將設定檔放入
  2. 在 `link.py` 的 `LINKS` 清單新增 `LinkEntry`，映射倉庫路徑到系統路徑
  3. 在 `README.md` 的結構表格新增對應項目

## commands/ — 自訂 CLI 命令

- **技術棧**：Python + [typer](https://typer.tiangolo.com/)（透過 PEP 723 inline script metadata + `uv run` 自動管理依賴）
- **PATH 注入**：`zsh/.zshrc` 中 `export PATH="$HOME/dotfiles/commands:$PATH"`
- **新增命令**：在 `commands/` 中建立可執行檔（`chmod +x`），shebang 使用 `#!/usr/bin/env python3`，即可直接作為系統命令使用
- **慣例**：
  - 每個命令一個檔案，檔名即命令名（無副檔名）
  - shebang 使用 `#!/usr/bin/env -S uv run --script`，搭配 PEP 723 metadata 宣告依賴
  - 使用 `typer.Typer()` + `@app.command()` 定義子命令
  - docstring 作為 `--help` 說明文字
  - 不需手動 pip install，uv 自動快取管理
