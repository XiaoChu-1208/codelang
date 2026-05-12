"""One-time installer:

1. Adds <project>/bin to the user's PATH so `codelang` / `dongwang` work
   as commands in any CMD/PowerShell window.
2. Creates a desktop shortcut codelang.lnk with the project icon —
   double-click to start, drag anywhere (desktop / 任务栏).

Run via: double-click install.bat at the project root, or:
    py tools/install_shortcuts.py
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
ICON = ROOT / "assets" / "logo" / "icon.ico"

# Windows broadcasting constants (so opened cmd windows pick up new PATH)
HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002


def add_to_user_path(target_dir: Path) -> bool:
    """Append `target_dir` to the user's PATH env var (HKCU\\Environment).
    Returns True if a change was made.
    """
    bin_str = str(target_dir).rstrip("\\")
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
    ) as key:
        try:
            current, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, kind = "", winreg.REG_EXPAND_SZ

        # Case-insensitive presence check on individual path entries
        existing_entries = [p.strip().rstrip("\\") for p in current.split(";") if p.strip()]
        if any(e.lower() == bin_str.lower() for e in existing_entries):
            print(f"[skip] already in user PATH: {bin_str}")
            return False

        new_value = bin_str if not current else (current.rstrip(";") + ";" + bin_str)
        winreg.SetValueEx(key, "Path", 0, kind or winreg.REG_EXPAND_SZ, new_value)
        print(f"[ok]   added to user PATH: {bin_str}")

    # Broadcast the change so new shells see it without logout
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


def find_pythonw() -> str:
    """Locate pythonw.exe so the shortcut launches silently (no console)."""
    here = Path(sys.executable)
    candidate = here.with_name("pythonw.exe")
    if candidate.exists():
        return str(candidate)
    # Fallback: hope it's on PATH
    return "pythonw"


def create_desktop_shortcut() -> Path:
    """Create %USERPROFILE%\\Desktop\\codelang.lnk via a tiny VBScript helper.

    Uses VBScript (no third-party deps) so the install works on any Windows
    machine with just Python installed.
    """
    desktop = Path(os.path.expanduser("~")) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    lnk_path = desktop / "codelang.lnk"
    pythonw = find_pythonw()

    vbs = f"""\
Set objShell = CreateObject("WScript.Shell")
Set lnk = objShell.CreateShortcut("{lnk_path}")
lnk.TargetPath = "{pythonw}"
lnk.Arguments = "-m desktop.app"
lnk.WorkingDirectory = "{ROOT}"
lnk.IconLocation = "{ICON}"
lnk.Description = "codelang - 按住 Alt 划词解释代码黑话"
lnk.WindowStyle = 7
lnk.Save
"""
    vbs_path = ROOT / "_install_shortcut.vbs"
    vbs_path.write_text(vbs, encoding="utf-16")
    try:
        subprocess.run(["cscript", "//nologo", str(vbs_path)], check=True)
        print(f"[ok]   desktop shortcut created: {lnk_path}")
    finally:
        try:
            vbs_path.unlink()
        except Exception:
            pass
    return lnk_path


def main() -> int:
    print("=== codelang 一键安装 ===")
    print(f"项目路径: {ROOT}")
    print()

    if not ICON.exists():
        print(f"[warn] 找不到图标文件 {ICON}")
        print("       请先跑一次 py tools/render_icons.py 生成图标")
        print()

    print("1) 把 bin/ 加入 PATH（命令行能用 codelang / dongwang）...")
    changed = add_to_user_path(BIN)

    print("2) 桌面生成快捷方式（带图标，可拖到任务栏/开始菜单）...")
    lnk = create_desktop_shortcut()

    print()
    print("=" * 48)
    print("安装完成！")
    print()
    print("- CMD/PowerShell（请新开窗口，旧窗口看不到更新的 PATH）输入:")
    print("    codelang   ← 启动 codelang")
    print("    dongwang   ← 同上，方便拼音盲打")
    print()
    print(f"- 桌面已有快捷方式：{lnk.name}")
    print("  双击启动 / 拖到任务栏固定 / 拖到 shell:startup 实现开机自启")
    print()
    print("- 应用全程后台运行，托盘右下角能看到 codelang 蓝色小图标")
    print("- 想看日志：托盘右键 → 查看日志")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
