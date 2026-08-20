# myconfig

備份與同步個人常用工具設定檔的倉庫。

## 結構

| 目錄 | 說明 |
|------|------|
| `commands/`  | 自訂 CLI 命令（Python + typer，透過 mise PATH 注入） |
| `opencode/` | [OpenCode](https://opencode.ai) AI 編碼助手設定（共用 base，`~/.config/opencode` symlink） |
| `opencode-local/` | OpenCode 個人 overlay（`agents/` 等），僅互動式使用時透過 `OPENCODE_CONFIG_DIR` 疊加；非 symlink，避免污染 multica 等直接叫用 opencode 的工具 |
| `zsh/` | Zsh shell 設定（基於 [Oh My Zsh](https://ohmyz.sh)） |
| `ssh/` | OpenSSH 用戶端設定（`~/.ssh/config` symlink，統一使用 `xterm-256color`） |
| `mise/` | [mise](https://mise.jdx.dev) 開發工具版本管理器設定 |
| `starship/` | [Starship](https://starship.rs) 跨 shell 提示字元設定 |
| `tmux/` | [tmux](https://github.com/tmux/tmux) 終端多工器設定 |
| `zellij/` | [Zellij](https://zellij.dev) 終端多工器設定 |
| `kitty/` | [kitty](https://sw.kovidgoyal.net/kitty/) GPU 加速終端機設定（Catppuccin Mocha 主題） |
| `biome/` | [Biome](https://biomejs.dev) 全局 formatter 配置（TS/JS/JSON/CSS） |
| `prettier/` | [Prettier](https://prettier.io) 全局 formatter 配置 + plugins（Vue/Astro/Svelte/MD/YAML） |
| `backup/` | 每日自動備份腳本（cron 排程，自動 commit + push） |
| `systemd/` | systemd user service 設定（opencode-web、portless-proxy 等） |
| `environment.d/` | systemd user 環境變數（`~/.config/environment.d/`） |
| `fcitx5/` | [Fcitx5](https://fcitx-im.org) 輸入法 XDG autostart 設定 |
| `worktrunk/` | [Worktrunk](https://worktrunk.dev) git worktree 管理工具設定 |
| `agents/` | [npm:skills](https://www.npmjs.com/package/skills) 的 lock 檔備份（非 symlink；`~/.agents` 為本機執行期資料，僅用 `sync-skills` 備份 `.skill-lock.json`） |
| `curl/` | [curl](https://curl.se) 全局設定（預設啟用 `.netrc` 認證） |
| `omp/` | [Oh My Pi](https://github.com/) AI agent 設定備份（非 symlink；`~/.omp` 為本機執行期資料，僅用 `sync-omp` 備份 `agent/config.yml` + `agent/models.yml`） |
| `searxng/` | [SearXNG](https://searxng.org) meta-search instance docker-compose（僅綁 127.0.0.1，供 omp `web_search` 使用） |


## mise 自訂插件

此倉庫包含自訂 mise 插件，用於管理未收錄在官方 registry 的工具。

### cursor-agent

Cursor Agent CLI 插件，從 [cursor.com](https://cursor.com) 官方下載安裝。

首次設定需手動連結插件：

```bash
mise plugins link cursor-agent ~/myconfig/mise/plugins/cursor-agent
```

之後 `mise install` 會自動安裝 `mise/config.toml` 中宣告的 `cursor-agent`。

## 新增工具設定

建立以工具名稱命名的新子目錄，將設定檔放入其中。若有需要排除的檔案，在子目錄內建立 `.gitignore`。


## Oh My Pi 備份策略

`~/.omp` 是 omp 的執行期目錄，包含大量會持續變動的 runtime 資料
（sessions、SQLite db、blobs、logs、cache 等），**不適合整個 symlink 進倉庫**。
因此採用「腳本備份」策略：

- 執行期資料全部留在 `~/.omp`（本機專屬，不進 git）
- 純設定檔（`agent/config.yml`、`agent/models.yml`）用 `sync-omp` 備份回倉庫 `omp/`

omp 用完後執行：

```bash
sync-omp              # 複製設定檔並自動 commit + push
sync-omp --dry-run    # 預覽模式
```

## Skills 備份策略

`~/.agents` 是 [npm:skills](https://www.npmjs.com/package/skills) 的執行期目錄，包含
安裝的 skill 本體（`skills/`）與安裝清單（`.skill-lock.json`），**不適合整個 symlink 進倉庫**。
因此採用「腳本備份」策略：

- 執行期資料（skill 本體）留在 `~/.agents`（可重建，不進 git）
- 安裝清單（`.skill-lock.json`）用 `sync-skills` 備份回倉庫 `agents/`

skill 安裝/更新後執行：

```bash
sync-skills           # 複製 lock 檔並自動 commit + push
sync-skills --dry-run # 預覽模式
```

還原流程：將 `agents/.skill-lock.json` 複製回 `~/.agents/`，再執行
`skills experimental_install` 重建所有 skill。

## Oh My Pi 自訂模型提供者

`omp/agent/models.yml` 新增 user-defined provider，以 OpenAI 相容介面接入任意 `baseUrl`。
目前包含 [NeuralWatt](https://neuralwatt.com) 11 個模型（GLM-5.2 / Qwen3.5-397B / Qwen3.6-35B / Kimi K2.6-K2.7 family）。

Credential 走 `resolveConfigValue()`：欄位值會先查 `process.env[<apiKey>]`，查不到才當字面常數。
所以 `models.yml` 內只放變數名（見下），secret 仍由環境變數提供。

首次在新機器使用前：

```bash
export NEURALWATT_API_KEY=sk-...   # 從 https://neuralwatt.com 取得
omp --model neuralwatt/qwen3.6-35b-fast -p 'hi'
```

要把 key 放進 keychain（或 prompt-time 動態詢問），把 `models.yml` 內 `apiKey: NEURALWATT_API_KEY` 改為 `apiKey: '!op read op://Personal/neuralwatt/api-key'`（以 `!` 開頭會當 shell 命令執行，stdout 當 key，結果會快取）。

要更新定價或 context window 限制，從 API 重新拉即可：

```bash
curl -s https://api.neuralwatt.com/v1/models | jq '.data[] | {id, ctx: .metadata.limits.max_context_length, pricing: .metadata.pricing}'
```
## SSH TERM 策略

`ssh/config` 會透過 `link.py` 連結到 `~/.ssh/config`，使用 OpenSSH 的 `SetEnv TERM=xterm-256color`，避免每台遠端主機額外安裝 Kitty terminfo。

- Ubuntu 22.04/24.04 的 `ncurses-base` 已提供 `xterm-256color`
- `ssh` 與 `gcloud compute ssh` 都使用同一份 OpenSSH config
- 需要 Kitty shell integration / keyboard protocol 時，使用 `kssh host`
