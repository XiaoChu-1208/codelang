#!/usr/bin/env bash
# codelang — macOS .app + .dmg builder.
#
# Produces a double-clickable codelang.app and wraps it in a drag-to-install
# DMG. Run this ON A MAC (it needs iconutil / hdiutil / codesign):
#
#     ./installer/build_mac.sh
#
# Output:
#     dist/codelang.app
#     dist/codelang-<version>.dmg
#
# The build happens inside a throwaway venv (.build-venv) so your everyday
# Python stays untouched. Override the interpreter with CODELANG_PYTHON.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VERSION="$(tr -d '[:space:]' < VERSION)"
PYBIN="${CODELANG_PYTHON:-python3}"

echo "==> codelang macOS app builder (v$VERSION)"
echo "    repo: $REPO_ROOT"
echo

if [ "$(uname -s)" != "Darwin" ]; then
    echo "build_mac.sh 只能在 macOS 上跑（需要 iconutil / hdiutil / codesign）。" >&2
    exit 1
fi

# ---- 1. clean build venv with runtime deps + py2app ----
BUILD_VENV=".build-venv"
echo "==> 建临时构建环境 $BUILD_VENV ..."
rm -rf "$BUILD_VENV"
"$PYBIN" -m venv "$BUILD_VENV"
VPY="$BUILD_VENV/bin/python"
"$VPY" -m pip install --upgrade pip wheel >/dev/null
# resvg-py is build-time-only for icon rendering and has flaky macOS wheels —
# skip it here; we generate the .icns from the committed PNGs instead.
grep -v -i 'resvg' requirements.txt > "$BUILD_VENV/req.txt"
"$VPY" -m pip install -r "$BUILD_VENV/req.txt" py2app

# ---- 2. generate codelang.icns from the committed PNG set ----
# The committed icon-*.png files are ~16:15 aspect (the mascot's natural
# bbox), not square. iconutil rejects non-square slices with a useless
# "Failed to generate ICNS" — so make_iconset.py pads each slot to a
# transparent square canvas first.
echo "==> 生成 .icns 图标 ..."
ICONSET="installer/codelang.iconset"
rm -rf "$ICONSET" installer/codelang.icns
"$VPY" installer/make_iconset.py "$ICONSET"
iconutil -c icns "$ICONSET" -o installer/codelang.icns
rm -rf "$ICONSET"

# ---- 3. run py2app ----
echo "==> 用 py2app 打包 codelang.app ..."
rm -rf build "dist/codelang.app"
"$VPY" installer/setup_mac.py py2app

# ---- 3b. bundle the Tcl/Tk script libraries ----
# py2app's tkinter recipe copies only the Tcl/Tk *dylibs* into
# Contents/Frameworks — it does NOT copy the script libraries (init.tcl,
# tk.tcl, encodings, …). Against a non-framework Tcl/Tk (e.g. Homebrew's
# tcl-tk, which ships plain .dylibs rather than .frameworks) the bundle then
# crashes at launch — but only when launched via Finder/`open` (a minimal
# launchd env), since a shell launch may inherit a usable TCL_LIBRARY:
#     _tkinter.TclError: Can't find a usable init.tcl ...
# Fix: drop the script libs at Contents/lib/{tcl8.6,tk8.6} — the default
# location Tcl/Tk search relative to the executable, so no env var is needed.
echo "==> 补全 Tcl/Tk 脚本库（py2app 只打了 dylib，漏了 init.tcl 等脚本）..."
# Ask Tcl/Tk themselves for their script dirs so this works for any layout
# (Homebrew's lib/{tcl,tk}8.6 siblings, the python.org framework, …). tcl_library
# needs no display; tk_library is read from a real Tk(), falling back to the
# tcl sibling dir if we're headless and Tk() can't open a connection.
read -r TCL_VER TCL_LIB <<EOF
$("$VPY" -c 'import tkinter; t=tkinter.Tcl(); print(t.eval("info tclversion"), t.eval("info library"))')
EOF
TK_LIB="$("$VPY" -c 'import tkinter
try:
    r = tkinter.Tk(); print(r.tk.eval("set tk_library"))
except Exception:
    pass' 2>/dev/null)"
[ -n "$TK_LIB" ] || TK_LIB="$(dirname "$TCL_LIB")/tk$TCL_VER"
[ -f "$TCL_LIB/init.tcl" ] || { echo "build_mac.sh: 找不到 Tcl 脚本库 $TCL_LIB/init.tcl" >&2; exit 1; }
[ -f "$TK_LIB/tk.tcl" ]    || { echo "build_mac.sh: 找不到 Tk 脚本库 $TK_LIB/tk.tcl" >&2; exit 1; }
APP_LIB="dist/codelang.app/Contents/lib"
mkdir -p "$APP_LIB"
rm -rf "$APP_LIB/tcl$TCL_VER" "$APP_LIB/tk$TCL_VER"
cp -R "$TCL_LIB" "$APP_LIB/tcl$TCL_VER"
cp -R "$TK_LIB"  "$APP_LIB/tk$TCL_VER"
echo "    tcl: $TCL_LIB -> $APP_LIB/tcl$TCL_VER"
echo "    tk:  $TK_LIB  -> $APP_LIB/tk$TCL_VER"

# ---- 4. ad-hoc code signing ----
# Without a signature, macOS drops the app's Accessibility grant on every
# rebuild and Gatekeeper is harsher. Ad-hoc (`-`) signing is free and makes
# the permission stick per-bundle. For distribution outside your own Mac you
# still want a Developer ID signature + notarization (see installer/README).
echo "==> ad-hoc 签名 ..."
# Strip extended attributes first. py2app copies the Tcl/Tk frameworks
# (pulled in by the tkinter package include) with resource forks / Finder
# info attached, which makes codesign bail with "resource fork, Finder
# information, or similar detritus not allowed".
xattr -cr "dist/codelang.app"
codesign --force --deep --sign - "dist/codelang.app"

# ---- 5. pack into a drag-to-install DMG ----
echo "==> 打 DMG ..."
DMG="dist/codelang-$VERSION.dmg"
rm -f "$DMG"
STAGING="$(mktemp -d)"
cp -R "dist/codelang.app" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
hdiutil create -volname "codelang $VERSION" \
    -srcfolder "$STAGING" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGING"

echo
echo "==> 完成！"
echo "    App: dist/codelang.app"
echo "    DMG: $DMG"
echo
echo "把 DMG 发给用户：双击挂载 → 把 codelang 拖进 Applications 即可。"
echo "首次打开未签名/ad-hoc 应用，用户需右键点 codelang → 打开（绕过 Gatekeeper）。"
