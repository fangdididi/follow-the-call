# follow-the-call

[English](README.md) | **简体中文**

一个 Agent 技能，用来回答关于代码库的那类问题：*"……的时候，代码里到底发生了什么？"* 它沿一条真实路径走过代码，并写成一条**路线（trail）**：编号站点，每站钉在 `file:行号`，附原样引用片段、通俗解释、通往下一站的跳转和回讲提问。配套的小脚本能证明路线对今天的代码依然成立，自动修正漂移的行号，并在某一站失效时明确报错。

```
## 6. 处理函数写入笔记
at: server/routes.py:12
quote: note_id = store.insert_note(title, request["json"].get("body", ""))
says: 清洗过的标题和原始正文一起交给存储层，正文没有长度限制。
next: calls insert_note
```

## 为什么需要它

全景图和架构图告诉你有哪些部件。而人卡住的往往是另一个问题：*这件事发生时，代码按什么顺序运行？我关心的那一步在哪里？* 用文字讲清这件事很容易，但很难让人放心——函数名可能是编的，胶水层被跳过，三月写的走读文档到六月已经悄悄指错了行。

路线是可以校验的。每一站引用代码，每一跳点名一个必须出现在下一站文件里的符号，于是"这份讲解现在还对吗？"变成了一条有退出码的命令。

## 功能

- **一个问题，一条路径**：文件头写 `question`、`reader`、`rev`、`start`，之后 3–12 站。
- **带锚点的站点**：`at: file:行号` + `quote:`（原样片段，忽略空白差异）+ `says:` + `next: <动词> <符号>` + 可选的 `ask:` / `answer:`。
- **仓库地图**（`scan`）：入口（`__main__`、Go 的 `main`、`package.json` 的 main/bin、约定俗成的文件名）、各类"门"（Flask/FastAPI/Django/Express/Go 风格的 HTTP 路由、命令行子命令、后台任务、事件监听）、被引用最多的枢纽文件、"先依赖后使用者"的阅读顺序，以及孤立文件。解析 Python 与 JS/TS 的本地 import；测试文件不计入"门"。
- **路线校验**（`check`）：文件存在且不越出仓库；引用在所写行上，否则判断为挪动（`MOVED`，可自动修）、多处出现（`MOVED_AMBIGUOUS`）或已消失（`QUOTE_GONE`）；跳转符号在下一站文件中可见（`HOP_UNSEEN`）；含糊说法（"probably""可能"）除非标注 `unverified:`；过短的引用；缺失字段；路线长度；提问数量。
- **感知版本**：在 git 仓库中写了 `rev:` 时，即使引用仍然匹配，只要所在文件在该提交之后改过，也会被标出。
- **四级发现，一个结论**：BREAK / CHECK / FIX / NOTE → WALKABLE、WALKABLE_AFTER_FIX、NEEDS_EYES、BROKEN。
- **自我修复**：`--fix` 改写漂移的行号，只有在没有断点时才更新 `rev`。
- **回讲题**（`quiz`）：按顺序抽出所有提问，可附答案。
- **适合 CI**：`--strict` 在 NEEDS_EYES / WALKABLE_AFTER_FIX 时退出码 1，BROKEN 时为 2；`--json` 便于接入工具。
- **零依赖**：Python 3.8+ 标准库，可离线使用，44 个测试。
- **双语**：完整的中英文说明；中文写的路线同样能解析。

## 安装

把整个文件夹复制到你的 Agent 加载技能的位置。

| Agent | 放置位置 |
|---|---|
| Claude Code | `~/.claude/skills/follow-the-call/`（所有项目）或 `.claude/skills/follow-the-call/`（单个项目） |
| Codex CLI | `~/.codex/skills/follow-the-call/`，或在 `AGENTS.md` 中引用 `SKILL.md` |
| Cursor | `.cursor/skills/follow-the-call/`，或用一条项目规则指向 `SKILL.md` |
| Gemini CLI、OpenCode、Copilot 等 | 把 `SKILL.zh-CN.md`（或 `SKILL.md`）作为指令加载，并确保能调用 `scripts/trail.py` |

```bash
git clone https://github.com/fangdididi/follow-the-call ~/.claude/skills/follow-the-call
```

## 使用

直接用自然语言说：

> 从点击"退款"到调用 Stripe，中间发生了什么？写成一条路线。

> 我刚接手这个仓库，带我走一遍登录请求是怎么处理的。

> 你刚做完导出功能，给我看一个导出任务经过的路径，并证明每一跳。

> 我们 docs/trails 里的路线都一年了，查查哪些还成立。

也可以直接运行脚本：

```bash
python3 scripts/trail.py scan .                                  # 从哪开始
python3 scripts/trail.py new > docs/trails/refund.trail.md       # 空白路线
python3 scripts/trail.py check docs/trails/refund.trail.md --root .
python3 scripts/trail.py check docs/trails/refund.trail.md --root . --fix
python3 scripts/trail.py quiz docs/trails/refund.trail.md --answers
```

在 CI 中（路线失效就让构建失败）：

```bash
for t in docs/trails/*.trail.md; do python3 scripts/trail.py check "$t" --root . --strict || exit 1; done
```

## 示例

`examples/tiny-notes/` 是一个前后端都有的小玩具应用；`examples/save-a-note.trail.md` 用七站把一条笔记从浏览器表单一路跟到 SQLite 里的那一行。

```text
$ python3 scripts/trail.py check examples/save-a-note.trail.md --root examples/tiny-notes
# Trail check: Saving a note

**Verdict: WALKABLE** - 7 stop(s); no findings

Question: What happens between pressing "Save" in the editor and the note row existing in SQLite?

Every anchor resolves, every hop is visible. Safe to hand to the reader.
```

有人在 `store.py` 顶部加了一行 import 之后：

```text
**Verdict: WALKABLE_AFTER_FIX** - 7 stop(s); FIX 1

| Level | Code | Stop | What to do |
|---|---|---|---|
| FIX | MOVED | 7 | Quote moved from line 10 to 11. |
```

有人把 `insert_note` 改名为 `add_note` 之后：

```text
**Verdict: NEEDS_EYES** - 7 stop(s); CHECK 1

| CHECK | HOP_UNSEEN | 6 | Stop 6 says `calls insert_note`, but `insert_note` does not appear in `server/store.py` (stop 7). ... |
```

## 文件结构

```
follow-the-call/
├── SKILL.md              # Agent 指令（英文）
├── SKILL.zh-CN.md        # Agent 指令（中文）
├── README.md
├── README.zh-CN.md
├── LICENSE
├── scripts/
│   └── trail.py          # scan / check / quiz / new
├── examples/
│   ├── save-a-note.trail.md
│   └── tiny-notes/       # 示例路线所走的玩具应用
└── tests/
    └── test_trail.py
```

## 局限

- `scan` 是静态分析：依赖注入、反射、插件加载器、字符串拼出来的名字它都看不见。正因如此，交付物是路线本身，而不是扫描结果。
- `check` 能证明锚点和跳转存在，却无法证明 `says` 那句话是对代码的正确解读。`HEDGED`、`FILE_CHANGED` 和回讲题就是为了让这一部分也保持诚实。

## 许可证

MIT
