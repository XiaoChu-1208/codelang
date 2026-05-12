"""Uninstaller — reverses what install_shortcuts.py did.

Removes <project>/bin from user PATH, deletes the desktop shortcut.

Optional --purge-config also removes ~/.codelang/ (config, LLM cache, missing
word log). Default leaves those alone so you don't lose your custom user dict.

Run via: double-click uninstall.bat at the project root, or:
    py tools/uninstall_shortcuts.py
    py tools/uninstall_shortcuts.py --purge-config
"""
from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import sys
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
DESKTOP_LNK = Path(os.path.expanduser("~")) / "Desktop" / "codelang.lnk"
USER_CONFIG_DIR = Path(os.path.expanduser("~")) / ".codelang"

HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002


def remove_from_user_path(target_dir: Path) -> bool:
    """Strip `target_dir` (and case-insensitive variants) out of user PATH.
    Returns True if a change was made.
    """
    bin_str = str(target_dir).rstrip("\\").lower()
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
    ) as key:
        try:
            current, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            print("[skip] user PATH 不存在，无需清理")
            return False

        entries = [p.strip() for p in current.split(";") if p.strip()]
        kept = [p for p in entries if p.rstrip("\\").lower() != bin_str]
        if len(kept) == len(entries):
            print("[1/2] 命令行入口本来就没装，跳过")
            return False

        new_value = ";".join(kept)
        if new_value:
            winreg.SetValueEx(key, "Path", 0, kind or winreg.REG_EXPAND_SZ, new_value)
        else:
            winreg.DeleteValue(key, "Path")
        print("[1/2] 命令行入口已移除")

    # Broadcast change so new shells pick it up
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        0,
        "Environment",
        SMTO_ABORTIFHUNG,
        5000,
        None,
    )
    return True


def delete_desktop_shortcut(lnk: Path) -> bool:
    if not lnk.exists():
        print("[2/2] 桌面快捷方式本来就没装，跳过")
        return False
    try:
        lnk.unlink()
        print("[2/2] 桌面快捷方式已删除")
        return True
    except Exception as e:
        print(f"[!] 删除桌面快捷方式失败: {e}")
        return False


def purge_user_config(config_dir: Path) -> bool:
    """Remove ~/.codelang/ entirely. Only called when --purge-config is passed."""
    if not config_dir.exists():
        print("[额外] 个人配置目录本来就没有，跳过")
        return False
    try:
        shutil.rmtree(config_dir)
        print(f"[额外] 已删除个人配置目录: {config_dir}")
        return True
    except Exception as e:
        print(f"[!] 删除个人配置失败: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--purge-config",
        action="store_true",
        help="同时删除 ~/.codelang/ (含 LLM 缓存、missing log、配置文件)",
    )
    args = parser.parse_args()

    print("正在卸载 codelang ...")
    print()

    remove_from_user_path(BIN)
    delete_desktop_shortcut(DESKTOP_LNK)

    if args.purge_config:
        purge_user_config(USER_CONFIG_DIR)

    print()
    print("=" * 48)
    print("卸载完了！")
    print()
    print("- 桌面图标和命令行入口都拆掉了")
    print("- 程序文件本体还在项目文件夹里，想彻底清掉直接删整个目录就行")
    print("- 如果 codelang 还在跑：右下角托盘右键 → 退出")
    if not args.purge_config:
        print()
        print("[小提示] 你自己录入的生词、个人配置还留着没动")
        print("        想一起清掉，运行: py tools/uninstall_shortcuts.py --purge-config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
