#!/usr/bin/env bash
# codelang — macOS installer.
#
# Does three things:
#   1. Verifies Python 3.10+ is on PATH (otherwise points the user at python.org).
#   2. Installs the Python deps from requirements.txt (pip --user).
#   3. Symlinks bin/codelang and bin/dongwang into a directory that's
#      already on PATH (preferring /usr/local/bin, then /opt/homebrew/bin,
#      then ~/.local/bin which we create if needed).
#
# This script is deliberately conservative — it never touches system
# Python, never asks for sudo. If a target directory isn't writable we
# fall back to ~/.local/bin and tell the user how to add it to PATH.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "==> codelang macOS installer"
echo "    repo: $REPO_ROOT"
echo

# ---- 1. find a Python ----
PYBIN="${CODELANG_PYTHON:-}"
if [ -z "$PYBIN" ]; then
    if command -v python3 >/dev/null 2>&1; then
        PYBIN=python3
    elif command -v python >/dev/null 2>&1; then
        PYBIN=python
    else
        cat <<EOF >&2
codelang: 没找到 python 解释器。

请先装 Python 3.10+：
  - 官网：https://www.python.org/downloads/
  - 或用 Homebrew：brew install python@3.12

装完后重新跑这个脚本。
EOF
        exit 1
    fi
fi

PYVER="$("$PYBIN" -c 'import sys;print(".".join(map(str,sys.version_info[:2])))')"
PYMAJ="$("$PYBIN" -c 'import sys;print(sys.version_info[0])')"
PYMIN="$("$PYBIN" -c 'import sys;print(sys.version_info[1])')"
if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 10 ]; }; then
    echo "codelang: Python 版本太老（$PYVER），需要 3.10+。" >&2
    exit 1
fi
echo "==> 使用 Python $PYVER ($PYBIN)"

# ---- 2. install deps ----
echo "==> 装 Python 依赖（pip --user）..."
"$PYBIN" -m pip install --user --upgrade pip setuptools wheel >/dev/null
"$PYBIN" -m pip install --user -r requirements.txt
echo

# ---- 3. choose a link directory ----
LINK_DIR=""
for candidate in /usr/local/bin /opt/homebrew/bin "$HOME/.local/bin"; do
    if [ -d "$candidate" ] && [ -w "$candidate" ]; then
        LINK_DIR="$candidate"
        break
    fi
done
if [ -z "$LINK_DIR" ]; then
    LINK_DIR="$HOME/.local/bin"
    mkdir -p "$LINK_DIR"
fi

chmod +x "$REPO_ROOT/bin/codelang" "$REPO_ROOT/bin/dongwang"
ln -sf "$REPO_ROOT/bin/codelang" "$LINK_DIR/codelang"
ln -sf "$REPO_ROOT/bin/dongwang" "$LINK_DIR/dongwang"
echo "==> 已建立软链 → $LINK_DIR/codelang (+ dongwang)"

# Warn if the chosen dir isn't on PATH.
case ":$PATH:" in
    *":$LINK_DIR:"*)
        ;;
    *)
        cat <<EOF

⚠️  $LINK_DIR 不在 PATH 上。请把下面这一行加到 ~/.zshrc 或 ~/.bash_profile：

    export PATH="$LINK_DIR:\$PATH"

加完之后开个新终端，或者跑：source ~/.zshrc
EOF
        ;;
esac

cat <<'EOF'

==> 装完啦！

接下来 3 步：

  1. 第一次启动：
       codelang

  2. macOS 会弹「codelang 想接收键盘输入」之类的提示，前往：
       系统设置 → 隐私与安全性 → 辅助功能
     把 *正在跑 codelang 的 Python（或 Terminal.app）* 勾上。
     （没勾的话，Option + 划词 完全没反应。）

  3. 在任意 App 里 按住 ⌥ Option + 鼠标划词 —— 鼠标旁边立刻弹解释卡片。

排查：日志在 ~/.codelang/codelang.log
卸载：./uninstall_mac.sh
EOF
