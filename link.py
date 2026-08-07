#!/usr/bin/env python3

"""
Symlink 管理腳本

將倉庫中的設定檔軟連結到系統對應位置。

用法：
    python link.py           預覽操作（預設，不實際執行）
    python link.py --apply   建立所有軟連結
"""

import sys
from pathlib import Path
from typing import NamedTuple

# ============================================================
# 配置區 — 在此新增或修改連結映射
#
#   source: 倉庫內的相對路徑（相對於此腳本所在目錄）
#   target: 系統上的目標路徑（支援 ~ 代表家目錄）
# ============================================================


class LinkEntry(NamedTuple):
    source: str
    target: str


LINKS: list[LinkEntry] = [
    LinkEntry("zsh/.zshrc", "~/.zshrc"),
    LinkEntry("opencode", "~/.config/opencode"),
    LinkEntry("mise", "~/.config/mise"),
    LinkEntry("starship/starship.toml", "~/.config/starship.toml"),
    LinkEntry("tmux/tmux.conf", "~/.config/tmux/tmux.conf"),
    LinkEntry("zellij/config.kdl", "~/.config/zellij/config.kdl"),
    LinkEntry("kitty", "~/.config/kitty"),
    LinkEntry(
        "systemd/opencode-web.service", "~/.config/systemd/user/opencode-web.service"
    ),
    LinkEntry(
        "systemd/portless-proxy.service",
        "~/.config/systemd/user/portless-proxy.service",
    ),
    LinkEntry(
        "environment.d/portless.conf",
        "~/.config/environment.d/portless.conf",
    ),
    LinkEntry(
        "environment.d/fcitx5.conf",
        "~/.config/environment.d/fcitx5.conf",
    ),
    LinkEntry(
        "fcitx5/fcitx5.desktop",
        "~/.config/autostart/fcitx5.desktop",
    ),
    LinkEntry("worktrunk/config.toml", "~/.config/worktrunk/config.toml"),
    LinkEntry("curl/.curlrc", "~/.curlrc"),
]

# ============================================================
# 腳本邏輯 — 通常不需要修改以下內容
# ============================================================

REPO_ROOT = Path(__file__).parent.resolve()


# ANSI 顏色
def green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def dim(s: str) -> str:
    return f"\033[2m{s}\033[0m"


def expand_home(path: str) -> Path:
    """將 ~ 展開為家目錄的絕對路徑（不跟隨 symlink）"""
    p = Path(path).expanduser()
    return p if p.is_absolute() else (Path.cwd() / p)


def is_symlink(path: Path) -> bool:
    """檢查路徑是否為 symlink（不論目標是否存在）"""
    try:
        return path.is_symlink()
    except OSError:
        return False


def is_dead_link(path: Path) -> bool:
    """檢查 symlink 是否指向不存在的目標（死鏈）"""
    # is_symlink 不跟隨 symlink，exists 會跟隨 symlink
    return is_symlink(path) and not path.exists()


def get_backup_path(path: Path) -> Path:
    """產生備份路徑，例如 .zshrc → .zshrc.bak 或 .zshrc.bak.2"""
    base = path.with_name(path.name + ".bak")
    if not base.exists():
        return base
    i = 2
    while base.with_name(f"{base.name}.{i}").exists():
        i += 1
    return base.with_name(f"{base.name}.{i}")


# ---- 主要操作 ----


def remove_dead_links(entries: list[LinkEntry], dry_run: bool) -> None:
    """移除死鏈"""
    for entry in entries:
        target = expand_home(entry.target)
        if is_dead_link(target):
            dest = target.readlink()
            if not dry_run:
                target.unlink()
            print(f"{yellow('⟳ 移除死鏈')}  {target} → {dest}")


def link_one(entry: LinkEntry, dry_run: bool) -> None:
    """建立單一 symlink，處理各種衝突情況"""
    source = (REPO_ROOT / entry.source).resolve()
    target = expand_home(entry.target)

    # 來源不存在
    if not source.exists():
        print(f"{red('✗ 來源不存在')}  {entry.source}")
        return

    # 目標已是正確的 symlink
    if is_symlink(target):
        current = target.readlink()
        if (target.parent / current).resolve() == source:
            print(f"{dim('· 已連結')}     {target} → {entry.source}")
            return

    # 目標是死鏈 — 移除後重建
    if is_dead_link(target):
        if not dry_run:
            target.unlink()
        print(f"{yellow('⟳ 移除死鏈')}  {target}")

    # 目標已存在（一般檔案或目錄） — 備份
    if target.exists() or is_symlink(target):
        backup = get_backup_path(target)
        if dry_run:
            print(f"{yellow('⟳ 將備份')}    {target} → {backup}")
        else:
            target.rename(backup)
            print(f"{yellow('⟳ 已備份')}    {target} → {backup}")

    # 確保目標的父目錄存在
    if not target.parent.exists():
        if not dry_run:
            target.parent.mkdir(parents=True)
        print(f"{green('+ 建立目錄')}  {target.parent}")

    # 建立 symlink
    if dry_run:
        print(f"{green('+ 將連結')}    {target} → {entry.source}")
    else:
        target.symlink_to(source)
        print(f"{green('✓ 已連結')}    {target} → {entry.source}")


# ---- 入口 ----


def main() -> None:
    dry_run = "--apply" not in sys.argv[1:]

    if dry_run:
        print(yellow("=== 預覽模式（加上 --apply 實際執行）===\n"))
    else:
        print(dim("=== 建立軟連結 ===\n"))

    remove_dead_links(LINKS, dry_run)
    for entry in LINKS:
        link_one(entry, dry_run)

    if not dry_run:
        print(green("\n✓ 完成"))


if __name__ == "__main__":
    main()
