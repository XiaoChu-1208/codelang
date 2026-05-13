#!/usr/bin/env bash
# codelang — macOS uninstaller.
#
# Removes the codelang / dongwang symlinks from common bin directories.
# Leaves the cloned repo and ~/.codelang config intact unless you pass
# --purge-config (which deletes ~/.codelang and the log/cache inside).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PURGE=0
for arg in "$@"; do
    case "$arg" in
        --purge-config) PURGE=1 ;;
        -h|--help)
            cat <<EOF
用法：./uninstall_mac.sh [--purge-config]

  --purge-config   连 ~/.codelang/ 一起删（日志、LLM 缓存、用户词典都没了）
EOF
            exit 0
            ;;
    esac
done

removed_any=0
for d in /usr/local/bin /opt/homebrew/bin "$HOME/.local/bin"; do
    for name in codelang dongwang; do
        link="$d/$name"
        if [ -L "$link" ]; then
            rm -f "$link"
            echo "removed symlink: $link"
            removed_any=1
        fi
    done
done
if [ "$removed_any" -eq 0 ]; then
    echo "没找到 codelang / dongwang 软链，可能本来就没装。"
fi

if [ "$PURGE" -eq 1 ]; then
    if [ -d "$HOME/.codelang" ]; then
        rm -rf "$HOME/.codelang"
        echo "removed config dir: ~/.codelang"
    fi
fi

cat <<EOF

==> 卸载完成。

如果还想彻底删干净，直接把这个仓库目录删掉就行：
    rm -rf "$REPO_ROOT"
EOF
