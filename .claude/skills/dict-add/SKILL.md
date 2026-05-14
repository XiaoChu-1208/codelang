---
name: dict-add
description: Add new entries to the codelang dictionary. Use when the user wants to add words/terms ("加几个词", "把 X 收录", "把 inbox 里的词都加上"). Handles collision checking, YAML format gotchas, building dict.json, and updating README counts.
---

# dict-add — 词典扩词工作流

codelang 的词典源在 `dict/*.yaml`，构建产物 `extension-browser/dict.json` 才是用户端拉取的——**改完 yaml 必须重建**，否则用户拉不到更新。

## 触发方式

- `/dict-add <主题>` — 例：`/dict-add 数据库锁` / `/dict-add k8s 网络`
- `/dict-add <词列表>` — 例：`/dict-add 间隙锁,行锁,表锁`
- `/dict-add inbox` — 处理 `dict/_inbox.md` 攒下的词
- 无参数 — 反问用户：今天想加什么主题？或者建议看一眼 inbox。

## 文件结构速查

| 分类 | 文件 | 用途 |
|------|------|------|
| 基础/通用 | `dict/basics.yaml` | 程序员日常的通用英文（system, server, data, list...） |
| 开发术语 | `dict/devterm.yaml` | 编程概念、协议、工具、文件后缀（最大的桶，~600 条） |
| 黑话/方法论 | `dict/jargon.yaml` | 闭环、抓手、颗粒度、视觉规范类 |
| 流行语 | `dict/slang.yaml` | 拽姐、偷感、情绪价值、网络梗 |
| 缩写 | `dict/abbr.yaml` | API/MVC/QPS/RPC 类大写缩写 |
| AI/LLM | `dict/ai.yaml` | embedding/RAG/agent/prompt 类 |
| MLOps/数据 | `dict/mlops.yaml` | 模型训练、数据库内核（MVCC/binlog/redo log 都在这） |
| 产品/运营 | `dict/product.yaml` | LTV/留存/拉新/激活 |
| 项目管理 | `dict/pm.yaml` | OKR/KPI/PMO/AIPM |
| 网安 | `dict/security.yaml` | XSS/SQL 注入/0day |
| 金融/创投 | `dict/finance.yaml` | LP/GP/估值/PE/VC |
| 游戏开发 | `dict/gamedev.yaml` | tick rate/ECS/lootbox |
| 平台/SaaS | `dict/platforms.yaml` | 阿里云/AWS/SaaS 厂商 |
| 系统/语言 | `dict/system.yaml` | macOS/Linux/Go/Rust/Kotlin 这些"专有名词" |
| AI 名人 | `dict/people.yaml` | Sam Altman/Ilya 等 |

**选文件原则**：先 grep 这个主题已有的词在哪个文件，跟着放。新主题倾向 `devterm.yaml`（兜底桶）。

## 工作流

### Step 1 — 候选词收集

- 来源：用户给的主题/词列表，或 `dict/_inbox.md`。
- 如果用户只给主题，**主动扩展**到 30-60 个相关词（同概念的英文/中文/缩写/同义、子概念、对立概念）。词典价值在覆盖面，不在一词一条。

### Step 2 — 碰撞检测（必做）

对每个候选词，grep 全部 yaml 查 `term:` 和 `aliases:`：

```bash
grep -niE "^- term: (词1|词2|...)" dict/*.yaml
grep -niE "aliases:.*(词1|词2)" dict/*.yaml
```

规范化规则（来自 `tools/build_dict.py`）：`lower().replace(" ","").replace("-","").replace("_","")`。所以 `WebAssembly`/`web assembly`/`web-assembly` 全部 = `webassembly`，一冲突就构建失败。

**冲突处理**：
- 词已存在 → 跳过，不要重复添加。
- 词只作为别名存在 → 跳过或把别名升级成独立条目（删原别名再建新条目）。
- 别名冲突（不同含义同缩写，如 `BP` = 反向传播 vs 缓冲池） → 缩写让给更通用的那个，另一个用全名。

### Step 3 — 起草条目

**三段式风格是这个词典的灵魂**，每条 `meaning` 必须包含：

1. **比喻**——用生活场景/熟悉事物类比（"想象 XX——……"）
2. **场景**——这个词在工程里实际指什么、什么时候出现、和别的概念什么区别
3. **隐含背景**——典型坑、面试角度、行业惯例

示例对比：

❌ 烂：「策略模式是一种把算法封装成独立类的设计模式。」
✅ 好：「想象付款台支持微信/支付宝/银行卡——前台流程一样（"扫码—确认—成功"），但"具体怎么扣钱"是不同算法的实现。策略模式就是把"可替换的算法"封装成独立类，运行时按需挑一个用。新增支付方式不用动主流程，加新策略类即可。日常代码里出场率最高的模式之一。」

`example` 一句话，给真实场景对话/吐槽，不是教科书。

### Step 4 — YAML 格式与避坑

**Schema**：

```yaml
- term: 词条主名
  aliases: [别名 1, 别名 2, 英文, 缩写]   # 可选
  category: devterm                       # 一般跟文件名一致
  literal: 字面意思                        # 可选，外文词建议有
  meaning: 主解释，三段式
  example: 一句话场景例句
```

**YAML 雷区**（每次都踩，写之前看一遍）：

1. **值以反引号开头** → 整个 value 用 `'...'` 单引号包：
   ```yaml
   example: '`<.*>` 在 `<a><b>` 上匹到整个串——典型贪婪坑。'
   ```
2. **值以 ASCII `"` 开头** → 改用中文「」或全角""，或单引号包整个值：
   ```yaml
   meaning: 「虚拟的表」——本身不存数据……
   ```
3. **值里含 `: `（冒号+空格）** → 整个值用双引号包，否则 YAML 把它当成嵌套映射切断：
   ```yaml
   example: "函数签名 `fn longest<'a>(x: &'a str) -> &'a str` 显式标 lifetime。"
   ```
4. **反斜杠** → 单引号里反斜杠是字面字面字符（安全），双引号里是转义起点（危险）。正则带 `\d` 这类的优先用单引号包。
5. **term 内部已有的别名不要重复**：自己的 term 和 aliases 之间也算冲突（虽然指向同一条），保持 aliases 不重复 term 本身。

### Step 5 — 落盘

- **追加到文件末尾**或主题相关的 batch 段落。
- 文件顶部通常有 `# --- batch X: 主题 ---` 风格的小节注释，新批次延续这个风格起个标题。
- 别动 `dict/user.yaml`（用户私人覆盖层，不能进发行包）。

### Step 6 — 构建 + 验证

```bash
py tools/build_dict.py   # 必跑，否则用户拉不到
py tools/count_dict.py   # 看新计数
```

- 构建报错 → 99% 是 YAML 格式问题（见 Step 4 雷区），按行号去修。
- 构建报 `Key collision` → 有别名重复，调整 aliases。
- `count_dict.py` 给出 `total: N`，记下来。

### Step 7 — 同步 README

README 里硬编码了好几处词条数和查询键数（旧值散布在 description / badges / 卖点列表 / 简介 / 表格 / SEO 区）。一次性全替换：

```python
py -c "import sys; p='README.md'; s=open(p,encoding='utf-8').read(); s=s.replace('旧词条数','新词条数').replace('旧查询键','新查询键'); open(p,'w',encoding='utf-8').write(s); print('replaced')"
```

跑完用 `grep -cE "旧词条数|旧查询键" README.md` 确认归零。

### Step 8 — 汇报

给用户一份简报，包含：
- 主题与新增条数
- 跳过的词（已存在的）
- 涉及到的别名冲突调整
- 新的总计数（词条 / 查询键）

## inbox 机制（可选）

如果用户在 `dict/_inbox.md` 里随手记词，本 skill 处理时按这个格式读：

```markdown
# 词典 inbox

下面随手记的词，跑 /dict-add inbox 时会处理。已处理的删掉即可。

- 间隙锁
- replication lag
- 主题：k8s 网络（建议扩展 10 条）
```

处理完后**不要自动删除**这些行，让用户手动确认并删——避免误判。改成在词后加 `✓ 已收录 (devterm.yaml)` 标记即可。

## 不该做的事

- 不要为了凑数加边缘词。词典的价值是高频/高困惑度的词，不是百科全书。
- 不要给已有词条加新的别名"丰富"它——除非用户明确要求或别名是真高频遗漏。改动现有条目风险比新增高。
- 不要在 `dict/_inbox.md` 之外创建笔记/计划文档。
- 不要 commit；做完报告完让用户决定何时提交。

## 参考

- 已经在 `MEMORY.md` 里记录：「改词库后必须重建 dict.json」`[[feedback_dict_build_workflow]]`
- 构建脚本：`tools/build_dict.py`
- 计数脚本：`tools/count_dict.py`
- 碰撞扫描：`tools/find_collisions.py`
