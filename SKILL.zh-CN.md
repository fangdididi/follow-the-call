---
name: follow-the-call
description: 回答"X 发生时代码里到底走了哪条路"——沿真实代码走一条执行路径，写成带锚点的路线（trail）：编号站点，每站钉在 file:行号 并附原样引用片段、通俗解释、通往下一站的跳转和回讲提问。配套脚本可列出入口与请求入口、逐站核对锚点和跳转是否仍然成立、自动修正漂移的行号，并标出已经失效的站点。适用于新人上手、讲解某个功能、排查一条流程，或审阅 Agent 写出的代码。
---

# follow-the-call

**语言：** [English](SKILL.md) | 简体中文

## 这是什么

理解一个代码库，是一条路径一条路径地理解。全景图和架构图告诉你有哪些方框，却不告诉你"用户点下保存之后，按顺序发生了什么"。这个技能产出的就是后者：一条**路线（trail）**。

路线是一份简短的 Markdown 文件，只回答一个问题，只沿一条真实的执行路径走。每一**站**都钉在代码上：

```
## 4. 处理函数先清洗标题
at: server/routes.py:9
quote: title = clean_title(request["json"].get("title", ""))
says: 标题在任何操作之前先被规整；缺失的字段会变成空字符串。
next: calls clean_title
ask: 用户粘贴了 300 个字符的标题，最终存进去的是什么？
```

每一站都带原样引用，每次跳转都点名一个符号，所以脚本可以证明这条路线现在依然成立：引用确实在那一行（或者已经挪到了哪一行）；跳转点名的符号确实出现在下一站的文件里。通过检查的路线，新人可以开着编辑器一站站走；代码改动后，也能在 CI 里重新验证。

## 解决的问题

- 让 AI"讲讲结账流程"，常得到一篇自信满满、函数名却是编的文章，或者一场逛目录的导览，始终没回答问题。
- 手写的上手文档会悄悄腐烂，没人发现 `services/billing.py:120` 早就变成了一行注释。
- 架构图展示结构而不是顺序，恰好略过了人最容易迷路的"胶水"：中间件、消息队列、由配置驱动的路由。
- Agent 写完一个功能后，人往往说不清一个请求究竟穿过了哪些代码。

## 什么时候用

- "用户……之后发生了什么""X 是怎么从 A 到 B 的""这个值是从哪来的"。
- 让新人（或一个全新的 Agent 会话）快速上手陌生仓库里的某个功能。
- 在 `docs/` 里撰写或更新一份必须保持正确的走读文档。
- 排查问题：先摸清真实路径，再猜 bug 在哪。
- 审阅 Agent 写的代码：让它走一遍自己写的功能，并证明每一跳。

不适用：整个系统的架构总览（画图更合适）、只读一个函数（直接读就行）、只在运行时才存在且无法钉到代码上的行为（交给日志、链路追踪和性能分析工具）。

## 操作步骤

### 1. 先定问题和读者

读代码之前，先写好文件头。

```
# 路线：退款到银行卡
question: 客服点击"退款"后，到通知支付服务商为止，运行了哪些代码？
reader: 客服工具组开发者，熟悉 Django，没碰过计费模块
rev: <当前提交>
start: 客服在订单页点击退款
```

- **一个问题，一条路径。** "计费是怎么工作的"是一门课，不是一条路线。把它收窄成"一个触发点 + 一个结果"。
- **写明读者**以及他已经懂什么，这决定每站 `says` 要解释到多细。
- **记录 `rev`**（`git rev-parse --short HEAD`），之后检查时就能知道哪些站点所在的文件改过。

### 2. 找到入口"门"

每条路径都从某个东西进入程序的地方开始：HTTP 路由、命令行子命令、定时任务、队列消费者、界面事件。

```bash
python3 scripts/trail.py scan path/to/repo
```

扫描会列出入口文件、各类"门"（路由、命令、任务、事件监听，附 `file:行号`）、被引用最多的枢纽文件，以及"先依赖、后使用者"的阅读顺序。它是静态的、不完整的；用它决定从哪开始，再用搜索确认（`rg "refund"`、路由路径、按钮文案、事件名）。

如果触发点在另一个仓库或服务里，第一站就是本仓库这一侧的边界（接收它的处理函数），并在 `says` 里说明它从哪来。

### 3. 一跳一跳地走

从门开始，跟着实际执行的代码走。在每个与问题相关的位置：

1. 打开文件，读完整个所在函数，而不只是那一行。
2. 从**同一行**里复制一段原样片段（至少 8 个非空白字符）填进 `quote`。优先选真正干活的那行：调用、写入、分支。
3. 用通俗语言为指定读者写 `says`：这里发生了什么、为什么跟问题有关。只写你亲眼看到的事实；如果是推断，以 `unverified:` 开头。
4. 写 `next: <动词> <符号>`，说明控制流或数据如何到达下一站。可用动词：calls、imports、reads、writes、sends、receives、handles、returns、renders、emits、listens、configures、triggers、queries、loads、dispatches、throws。符号（函数、方法、路由、表名、事件、配置键）必须出现在下一站的文件里。
5. 每两三站加一个 `ask:`，问题必须只有读过这一站才答得出；可选加 `answer:`。

值得设站的地方：

- **判断**：分支、守卫条件、提前返回、权限检查。
- **边界**：网络调用、队列发布/消费、数据库写入、文件读写、启动进程。
- **间接跳转**："跳转到定义"找不到的东西——依赖注入、字符串为键的路由表、信号/事件、用类名做装配的配置文件、负责注册处理函数的装饰器。这些恰恰是人最需要的站，每个单独设一站。
- **会改变答案的变换**：校验、截断、币种换算、默认值。

只转发参数的包装层不设站，在上一站的 `says` 里一句带过。

控制在 **3–12 站**。更长说明这其实是两个问题。

### 4. 校验

```bash
python3 scripts/trail.py check docs/trails/refund.trail.md --root .
```

发现分四级：

| 级别 | 代码 | 含义 |
|---|---|---|
| BREAK | FILE_GONE、QUOTE_GONE、LINE_OUT、BAD_AT、OUTSIDE_ROOT、MISSING_AT、MISSING_QUOTE、NO_STOPS | 这一站已经指不到真实代码，需要重走。 |
| CHECK | HOP_UNSEEN、MOVED_AMBIGUOUS、BAD_HOP、MISSING_NEXT、HEDGED、WEAK_QUOTE、REV_UNKNOWN、NO_QUESTION | 需要人看：看不见的跳转、含糊的说法、可能对应多行的锚点。 |
| FIX | MOVED | 引用还在，只是换了行。`--fix` 会改写行号。 |
| NOTE | REV_MOVED、FILE_CHANGED、REVISIT、QUOTE_REPEATS、LONG_TRAIL、SHORT_TRAIL、FEW_ASKS、NO_READER、NO_GIT | 给作者的提示。 |

结论：**WALKABLE**（可走）、**WALKABLE_AFTER_FIX**（修正后可走）、**NEEDS_EYES**（需要人看）、**BROKEN**（已断）。

常见问题的处理：

- **HOP_UNSEEN**：`next` 点名的符号不在下一站文件里。要么漏了一站（调用经过了你跳过的模块），要么锚错了文件，要么是间接跳转。遇到间接跳转，就把装配处（注册表、配置行、依赖注入绑定）补成一站，而不是把跳转写得含糊。
- **MOVED_AMBIGUOUS**：引用如今出现在多行。把引用加长到唯一，再跑一次。
- **HEDGED**："probably""seems to""可能""大概"。去核实，或者把这句标成 `unverified:`，让读者知情。
- **FILE_CHANGED**（`rev` 之后）：引用仍然匹配，但文件自路线写成后改过。重读这一站的 `says`——同一行代码周围的逻辑也可能变了。

路线达到 WALKABLE 之前不要交付（或者是 NEEDS_EYES，但每条剩余的 CHECK 都已在路线里说明）。

### 5. 交付

- 交付路线本身，而不是它的摘要。读者要开着编辑器一站站走。
- 单独提供回讲题：`python3 scripts/trail.py quiz trail.md`（加 `--answers` 输出答案）。读者答得出，就说明路线起作用了。
- 走的过程中如果发现了意外（死代码、缺失的检查、没有上限的字段），在路线后面以"沿途发现"列出，附锚点。没被要求就不要顺手修。
- 建议存放在 `docs/trails/`，并把 `trail.py check --strict` 加进 CI，代码一动路线就会明确报错。

### 6. 让路线保持鲜活

代码改动后运行 `check --fix`。挪动的行号会被自动修好；只有在没有断点时才会更新 `rev`。BROKEN 的站点从它前一站开始重走。

## 示例

问题：*在编辑器里点保存，到 SQLite 里出现这条笔记记录，中间发生了什么？*（完整文件见 `examples/save-a-note.trail.md`，代码在 `examples/tiny-notes/`）

| # | at | says（简） | next |
|---|---|---|---|
| 1 | web/editor.js:4 | 提交处理函数组装 `{title, body}`，前端不做校验 | calls postNote |
| 2 | web/api.js:2 | 以 JSON POST 到 /api/notes | sends /api/notes |
| 3 | server/routes.py:15 | 路由表把它映射到 `save_note` | calls save_note |
| 4 | server/routes.py:9 | 先清洗标题，空标题返回 422 | calls clean_title |
| 5 | server/validate.py:5 | 合并空白，静默截断到 120 字符 | returns title |
| 6 | server/routes.py:12 | 正文原样传下去，未清洗 | calls insert_note |
| 7 | server/store.py:10 | 参数化 INSERT，id 作为 201 返回 | - |

沿途发现：超过 120 字符的标题被截断却不告知用户（第 5 站）；正文没有长度上限（第 6 站）。

之后如果有人在 `store.py` 顶部加了一行 import，`check` 会对第 7 站报 `MOVED`，`--fix` 把锚点从第 10 行改到第 11 行。如果有人把 `store.py` 里的 `insert_note` 改了名，第 6 站的跳转变成 `HOP_UNSEEN`；如果有人改写了校验那一行，第 5 站变成 `QUOTE_GONE`。路线会明确失败，而不是悄悄说谎。

## 小贴士

- 引用这一行里最有辨识度的部分。`return res.json()` 到处都是，`fetch("/api/notes"` 则不是。
- 一个判断一站，而不是一个文件一站。一个文件可以有三站；十个薄包装串起来的链条也可以只算一站。
- 异步流程（队列、事件、Webhook）：发送端用 `emits`/`sends`，下一站是消费者，例如 `next: emits order.paid`，消费者文件里要出现 `order.paid`。如果名字是动态拼出来的，在拼名字的地方加一站。
- 生成代码和第三方库：停在你自己代码的边界，用一句话说明库做了什么。
- Monorepo：`check` 时把 `--root` 设为仓库根目录，跨包路径才能解析。
- 读者不是开发者时：保留锚点，简化 `says`。正是锚点让通俗版本值得信任。
- 实在找不到某一跳时，就在路线里如实写（`next: calls unverified: 读取 RETRY_QUEUE 的某处`），不要编造；`check` 会跳过标了 `unverified:` 的符号。

## 文件

- `scripts/trail.py`：`scan`、`check`（`--fix`、`--strict`、`--json`）、`quiz`、`new`。Python 3.8+，仅用标准库。
- `examples/`：一个前后端都有的小应用，以及一条贯穿它的完整路线。
- `tests/`：单元测试（`python3 -m unittest discover -s tests`）。
