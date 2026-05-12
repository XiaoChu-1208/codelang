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
            print(f"[skip] PATH 里没找到 {target_dir}，无需清理")
            return False

        new_value = ";".join(kept)
        if new_value:
            winreg.SetValueEx(key, "Path", 0, kind or winreg.REG_EXPAND_SZ, new_value)
        else:
            winreg.DeleteValue(key, "Path")
        print(f"[ok]   从用户 PATH 移除: {target_dir}")

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
        print(f"[skip] 桌面快捷方式不存在 ({lnk.name})，无需删除")
        return False
    try:
        lnk.unlink()
        print(f"[ok]   删除桌面快捷方式: {lnk}")
        return True
    except Exception as e:
        print(f"[err]  删除快捷方式失败: {e}")
        return False


def purge_user_config(config_dir: Path) -> bool:
    """Remove ~/.codelang/ entirely. Only called when --purge-config is passed."""
    if not config_dir.exists():
        print(f"[skip] 配置目录不存在 ({config_dir})")
        return False
    try:
        shutil.rmtree(config_dir)
        print(f"[ok]   删除配置目录: {config_dir}")
        return True
    except Exception as e:
        print(f"[err]  删除配置失败: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--purge-config",
        action="store_true",
        help="同时删除 ~/.codelang/ (含 LLM 缓存、missing log、配置文件)",
    )
    args = parser.parse_args()

    print("=== codelang 卸载 ===")
    print(f"项目路径: {ROOT}")
    print()

    print("1) 从用户 PATH 移除 bin/ ...")
    remove_from_user_path(BIN)

    print("2) 删除桌面快捷方式 ...")
    delete_desktop_shortcut(DESKTOP_LNK)

    if args.purge_config:
        print("3) 删除用户配置目录 (--purge-config) ...")
        purge_user_config(USER_CONFIG_DIR)
    else:
        print("3) 配置目录保留 (~/.codelang/)")
        print("   如需一并清理，请用: py tools/uninstall_shortcuts.py --purge-config")

    print()
    print("=" * 48)
    print("卸载完成！")
    print()
    print("- 项目代码、词库、托盘程序仍在原地（你 git clone 的那个目录）")
    print("  想完全清掉直接删整个项目文件夹即可")
    print("- 如果 codelang 还在跑：托盘右键 → 退出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
