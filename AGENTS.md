# AGENTS.md — 给 AI Agent / 自动化工具看的指引

> 这是 [Agents.md 标准](https://agents.md/) 格式的项目说明文档，用于让 Claude Code、Cursor、Windsurf、Codex CLI、通义灵码等 agentic AI 工具理解本项目，并能帮助用户完成"装 / 跑 / 改 / 卸载"的全流程。

## 项目身份

- **名称**：codelang（中文别名：懂网 / dongwang）
- **类型**：Windows 桌面工具（Python + Win32 + 浏览器扩展）
- **作用**：按住 Alt + 鼠标划词，在鼠标旁弹出大白话术语解释卡片
- **平台**：Windows 10 / 11
- **协议**：MIT
- **仓库**：https://github.com/XiaoChu-1208/codelang

## 你被叫来干嘛（典型用户请求）

如果用户对你说类似下面的话，你应该按本文档操作：

1. **"帮我装这个工具：https://github.com/XiaoChu-1208/codelang"**  
   → 见下方 [安装流程](#安装流程给-agent-自动跑)

2. **"帮我把 codelang 跑起来"**  
   → 见下方 [启动流程](#启动流程)

3. **"帮我加一条词到 codelang 词库"**  
   → 见下方 [增改词条](#增改词条)

4. **"卸载 codelang"**  
   → 见下方 [卸载流程](#卸载流程)

5. **"codelang 没反应 / 划词不弹卡片"**  
   → 见下方 [故障排查](#故障排查)

---

## 安装流程（给 agent 自动跑）

**前置条件**：用户电脑上有 Python 3.10+。如果没有，先引导用户从 https://www.python.org/downloads/ 装（勾选 "Add to PATH"）。

**自动化步骤**（你应该一步步在用户终端里跑）：

```powershell
# 1. 确认 Python 可用
py --version
# 期望输出 Python 3.10.x 或以上

# 2. 克隆仓库到用户主目录
cd $HOME
git clone https://github.com/XiaoChu-1208/codelang.git
cd codelang

# 3. 安装 Python 依赖
py -m pip install -r requirements.txt
# 关键依赖：mouse, pyperclip, pystray, Pillow, requests, pyyaml

# 4. 一键安装（加用户 PATH + 桌面快捷方式）
.\install.bat

# 5. 启动
codelang
# 或：双击桌面 codelang.lnk
# 或：cmd 里敲 dongwang（同一程序的中文别名）
```

**启动成功的判断**：Windows 系统托盘右下角出现蓝色 "codelang" 图标。

**如果失败**：
- `mouse` / `pystray` 装不上 → 用 `py -m pip install --upgrade pip setuptools` 再试
- 启动报错 → `py -m desktop.app` 在终端里直接跑看错误日志
- 卡片不出来 → 让用户按住 Alt 在任意网页词上双击；如还不行，查 `~/.codelang/codelang.log`

## 启动流程

三种方式都可以，挑一个用：

| 方式 | 命令 |
|---|---|
| 命令行 | `codelang` 或 `dongwang` |
| 桌面快捷方式 | 双击 `~/Desktop/codelang.lnk` |
| 开机自启 | 把 `codelang.lnk` 拖进 `shell:startup` |
| 调试模式（带控制台） | 双击 `desktop\run_console.bat` |

## 增改词条

词库源文件在 `dict/*.yaml`（共 9 个文件，按类别分）：

| 文件 | 类别 |
|---|---|
| `devterm.yaml` | 开发/工程概念 |
| `ai.yaml` | AI / LLM / 大模型 |
| `platforms.yaml` | 平台 / 框架 / 数据库 / 云 |
| `system.yaml` | 操作系统 / 硬件 / 办公 |
| `basics.yaml` | 基础英文词 |
| `jargon.yaml` | 互联网黑话 |
| `abbr.yaml` | 缩写 |
| `slang.yaml` | 流行语 / 职场俚语 |
| `product.yaml` | 产品 / 运营 / 增长 |
| `user.yaml` | 用户运行时录入（不要手改这个） |

**新加一条**：

```yaml
- term: 术语
  aliases: [别名 1, 别名 2]
  category: jargon         # devterm / jargon / abbr / slang / ai / 等
  literal: 字面意思
  meaning: 想象 XXXX —— 这就是 YYYY ...
  example: 真实场景例句。
```

**风格要求（很重要）**：
- 开头用一个生活化比喻或具体场景
- 把比喻映射回这个词的实际含义
- 给一个真实可见的使用场景例句
- **禁用** "在某种意义上"、"可以理解为" 这种端着的废话
- 不懂代码的人也要能秒懂

**改完后**：
```powershell
# 在托盘菜单点"重新加载词典"，或：
py tools\build_dict.py   # 重建浏览器扩展用的 dict.json（可选）
```

## 卸载流程

```powershell
# 1. 一键反向卸载（去 PATH + 删快捷方式）
cd path\to\codelang
.\uninstall.bat

# 2. 也删用户配置（含 LLM 缓存、用户词、日志）
py tools\uninstall_shortcuts.py --purge-config

# 3. 彻底删项目代码
cd ..
Remove-Item -Recurse codelang
```

## 故障排查

| 症状 | 检查 |
|---|---|
| 划词没反应 | 1) 托盘有图标吗？没有 → 重启；2) 在浏览器里测试（先简单环境）；3) 看 `~/.codelang/codelang.log` |
| Alt 键卡住 | 托盘菜单 → "释放卡住的 Alt"；不行就重启 codelang |
| 多显示器卡片位置错 | 0.1+ 版本应已修复，否则报 issue |
| 高 DPI 字太小 | 同上 |
| LLM 兜底不工作 | `~/.codelang/config.json` 里 `api_key` 填对了吗？`llm_fallback_enabled: true` 了吗？ |

**实时日志**：托盘菜单点"查看日志" → 自动用记事本打开 `~/.codelang/codelang.log`。

## 项目结构（关键文件给你定位用）

```
codelang/
├── dict/*.yaml                 词库源（改这里加词）
├── desktop/
│   ├── app.py                  主入口（py -m desktop.app）
│   ├── ui.py                   tooltip 卡片渲染
│   ├── lookup.py               查询逻辑 + LLM 兜底
│   ├── win.py                  Win32 API 封装
│   └── config.py               配置加载
├── bin/
│   ├── codelang.cmd            CLI 启动器
│   └── dongwang.cmd            CLI 启动器（中文别名）
├── tools/
│   ├── build_dict.py           YAML → 浏览器扩展 dict.json
│   ├── install_shortcuts.py    install.bat 调用的实际逻辑
│   └── uninstall_shortcuts.py  反向卸载
├── extension-browser/          Chromium 扩展（备用方案）
├── install.bat                 双击一键装
├── uninstall.bat               双击一键卸
└── requirements.txt            Python 依赖
```

## 配置文件位置

- **运行时配置**：`%USERPROFILE%\.codelang\config.json`
- **用户字典**：`%USERPROFILE%\.codelang\user.yaml`
- **LLM 缓存**：`%USERPROFILE%\.codelang\llm_cache.json`
- **运行日志**：`%USERPROFILE%\.codelang\codelang.log`

## 开 LLM 兜底（默认关）

编辑 `~/.codelang/config.json`：

```json
{
  "provider": "anthropic",
  "api_key": "用户的 Anthropic API key",
  "model": "claude-haiku-4-5-20251001",
  "llm_fallback_enabled": true
}
```

OpenAI 也行：
```json
{
  "provider": "openai",
  "api_key": "用户的 OpenAI API key",
  "model": "gpt-4o-mini",
  "llm_fallback_enabled": true
}
```

## 重要：不要做的事

- ❌ 不要改 `dict/user.yaml` 的格式（运行时维护，会被改）
- ❌ 不要把用户的 API key commit 进任何文件
- ❌ 不要无脑装到系统 Python；如有 venv 优先用 venv
- ❌ 不要绕过 install.bat 自己改注册表（PATH）—— install.bat 已经处理了

## 你可以放心做的事

- ✅ 帮用户跑 install.bat、修依赖、看日志
- ✅ 帮用户改 `dict/*.yaml` 加新词
- ✅ 帮用户改 `~/.codelang/config.json` 配置 LLM
- ✅ 帮用户排查"划词没反应"——按"故障排查"那张表逐项查
- ✅ 帮用户把 `codelang.lnk` 拖进 `shell:startup` 实现开机自启

## 一句话总结

**装：clone → pip install → install.bat → 跑 codelang。改词：编辑 dict/*.yaml → 托盘"重新加载词典"。卸：uninstall.bat。**
