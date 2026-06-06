#!/usr/bin/env bash
# codelang —— 首次安装修复助手（macOS）
#
# 为什么需要它：codelang 是开源、未做 Apple 付费公证的 app。浏览器下载的
# app 会被打上「隔离属性」(com.apple.quarantine)，如果不抹掉，macOS 会启用
# 「应用易位」(App Translocation) —— 把 app 复制到一个每次都变的随机只读路径
# 下运行，导致「辅助功能 / 输入监控」权限永远存不住，⌥ + 划词 一直没反应。
#
# 这个脚本做三件事：
#   1. 抹掉 /Applications/codelang.app 的隔离属性（根治易位）。
#   2. 重新从 /Applications 正经启动 codelang。
#   3. 打开「辅助功能 / 输入监控 / 屏幕录制」设置面板，方便你手动勾选
#      （这一步 macOS 不允许脚本代劳，必须你亲手点一下）。
#
# 用法：把 codelang 拖进「应用程序」后，双击本文件即可。

APP="/Applications/codelang.app"

echo "========================================"
echo "  codelang 首次安装修复助手"
echo "========================================"
echo

# ---- 0. 确认 app 已经在 /Applications ----
if [ ! -d "$APP" ]; then
    echo "❌ 没在「应用程序」里找到 codelang。"
    echo
    echo "   请先把 codelang 图标拖进「应用程序」文件夹，再双击本脚本。"
    echo
    echo "   （如果你是从 DMG 窗口运行的，把左边的 codelang 拖到右边的"
    echo "    Applications 文件夹上即可。）"
    echo
    read -n 1 -s -r -p "按任意键关闭…"
    exit 1
fi

# ---- 1. 退出可能在跑的旧实例（含易位实例）----
echo "==> 退出正在运行的 codelang …"
osascript -e 'quit app "codelang"' >/dev/null 2>&1
pkill -f "codelang.app/Contents/MacOS/codelang" >/dev/null 2>&1
sleep 1

# ---- 2. 抹掉隔离属性（根治应用易位）----
echo "==> 抹掉隔离属性（com.apple.quarantine）…"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
if xattr -r "$APP" 2>/dev/null | grep -q com.apple.quarantine; then
    echo "    ⚠️ 仍残留隔离属性，尝试逐个清理…"
    find "$APP" -print0 2>/dev/null | xargs -0 xattr -d com.apple.quarantine 2>/dev/null
fi
echo "    ✅ 完成"

# ---- 3. 正经启动 ----
echo "==> 从 /Applications 启动 codelang …"
open "$APP"
sleep 2

# ---- 4. 打开权限设置面板（用户手动勾选）----
echo "==> 打开系统设置面板，请按提示勾选 codelang …"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

cat <<'EOF'

----------------------------------------
✅ 修复完成！最后还差你手动点一下授权：

在刚弹出的「系统设置 → 隐私与安全性」里，给 codelang 打开这三项
（左侧切换不同类别，点 + 号添加 /Applications/codelang.app）：

  • 辅助功能(Accessibility)   ← ⌥ 划词必需
  • 输入监控(Input Monitoring) ← ⌥ 划词必需
  • 屏幕录制(Screen Recording) ← OCR（⌥ + `）才需要，可选

勾选后系统若提示「需要退出并重新打开 codelang」，照做即可。

之后在任意 App 里按住 ⌥ Option 拖选英文单词，旁边就会弹出解释卡片。
----------------------------------------

EOF

read -n 1 -s -r -p "按任意键关闭本窗口…"
echo
