"""py2app build configuration for codelang.app (macOS).

Don't run this directly — use installer/build_mac.sh, which creates a clean
venv, generates the .icns icon, signs the result, and packs the DMG. If you
do want to invoke py2app alone, run it from the repo root so the `desktop`
package is importable:

    python3 installer/setup_mac.py py2app

Output: dist/codelang.app
"""
from pathlib import Path

from setuptools import setup

REPO = Path(__file__).resolve().parent.parent

VERSION = (REPO / "VERSION").read_text(encoding="utf-8").strip()

# Data trees copied verbatim into Contents/Resources/. desktop/paths.py
# resolves these at runtime via the RESOURCEPATH env var py2app exports, so
# the layout here (extension-browser/…, assets/logo/…) must mirror the repo.
DATA_FILES = [
    (
        "extension-browser",
        [
            str(REPO / "extension-browser" / "dict.json"),
            str(REPO / "extension-browser" / "ecdict.json"),
        ],
    ),
    (
        "assets/logo",
        [str(p) for p in sorted((REPO / "assets" / "logo").glob("icon-*.png"))],
    ),
]

OPTIONS = {
    # argv_emulation pulls in Carbon and misbehaves on modern macOS; codelang
    # never reads argv, so leave it off.
    "argv_emulation": False,
    # `desktop` is our package; the rest are libraries modulegraph sometimes
    # fails to trace fully (pyobjc frameworks, pynput, PIL). Listing them
    # explicitly is the reliable path.
    "packages": [
        "desktop",
        # tkinter must be a full package include: modulegraph only traces
        # statically-visible imports and misses submodules like tkinter.font
        # (imported in deps_error.py), which crashed the bundle at launch with
        # "cannot import name 'font' from 'tkinter'".
        #
        # NOTE: py2app's tkinter recipe bundles only the Tcl/Tk *dylibs*, not
        # the script libraries (init.tcl, tk.tcl, …). Those are copied into
        # Contents/lib/{tcl8.6,tk8.6} by installer/build_mac.sh (step 3b);
        # without them the .app crashes at launch with "Can't find init.tcl".
        "tkinter",
        "pynput",
        "pyperclip",
        "PIL",
        "requests",
        "yaml",
        "objc",
        "Quartz",
        "AppKit",
        "Foundation",
    ],
    "iconfile": str(REPO / "installer" / "codelang.icns"),
    "plist": {
        "CFBundleName": "codelang",
        "CFBundleDisplayName": "codelang",
        "CFBundleIdentifier": "com.codelang.app",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        # Menubar-only agent: no Dock icon, no app-switcher entry.
        "LSUIElement": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "codelang",
        # codelang shells out to `osascript`/`open` for the log + folder menu
        # items; declare it so macOS doesn't silently block the AppleEvents.
        "NSAppleEventsUsageDescription": (
            "codelang 用系统命令打开日志文件和配置目录。"
        ),
    },
}

setup(
    name="codelang",
    app=[str(REPO / "installer" / "codelang_app.py")],
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
