# follow-the-call

**English** | [简体中文](README.zh-CN.md)

An agent skill that answers *"what actually happens when ...?"* about a codebase by walking one real path through the code and writing it down as a **trail**: numbered stops, each pinned to `file:line` with an exact quoted fragment, a plain-language explanation, the hop to the next stop, and teach-back questions. A small script proves the trail is still true against today's code, repairs drifted line numbers, and fails loudly when a stop rots.

```
## 6. The handler stores the note
at: server/routes.py:12
quote: note_id = store.insert_note(title, request["json"].get("body", ""))
says: The cleaned title and the raw body go to the store. The body is not length-limited.
next: calls insert_note
```

## Why

Maps and diagrams show which parts exist. People get stuck on a different question: *in what order does the code run when this happens, and where is the step I care about?* Prose explanations of that are easy to write and hard to trust - function names get invented, glue gets skipped, and a walkthrough written in March quietly points at the wrong lines by June.

A trail is checkable. Every stop quotes the code, every hop names a symbol that must be visible in the next file, so "is this explanation still correct?" becomes a command with an exit code.

## Features

- **One question, one path**: a header with `question`, `reader`, `rev`, `start`, then 3-12 stops.
- **Anchored stops**: `at: file:line` + `quote:` (exact fragment, whitespace-insensitive) + `says:` + `next: <verb> <symbol>` + optional `ask:` / `answer:`.
- **Repo map** (`scan`): entry points (`__main__`, Go `main`, `package.json` main/bin, conventional names), doors (HTTP routes in Flask/FastAPI/Django/Express/Go styles, CLI subcommands, background jobs, event listeners), most-imported hub files, a dependencies-first reading order, and loose files. Python and JS/TS import resolution; tests are excluded from doors.
- **Trail check** (`check`): file exists and stays inside the repo, quote on the stated line, otherwise found elsewhere (`MOVED`, fixable), on several lines (`MOVED_AMBIGUOUS`), or gone (`QUOTE_GONE`); hop symbol visible in the next stop's file (`HOP_UNSEEN`); hedged claims ("probably", "可能") unless marked `unverified:`; weak quotes; missing fields; trail length; question count.
- **Revision awareness**: with `rev:` in a git checkout, stops in files changed since that commit are flagged even when their quote still matches.
- **Four levels, one verdict**: BREAK / CHECK / FIX / NOTE -> WALKABLE, WALKABLE_AFTER_FIX, NEEDS_EYES, BROKEN.
- **Self-repair**: `--fix` rewrites drifted line numbers and bumps `rev` only when nothing is broken.
- **Teach-back** (`quiz`): pulls the questions out in order, with an optional answer key.
- **CI-ready**: `--strict` exits 1 on NEEDS_EYES / WALKABLE_AFTER_FIX, 2 on BROKEN; `--json` for tooling.
- **No dependencies**: Python 3.8+ standard library; works offline; 44 tests.
- **Bilingual**: full English and Chinese instructions; Chinese trails parse the same way.

## Installation

Copy the folder to wherever your agent loads skills from.

| Agent | Where to put it |
|---|---|
| Claude Code | `~/.claude/skills/follow-the-call/` (all projects) or `.claude/skills/follow-the-call/` (one project) |
| Codex CLI | `~/.codex/skills/follow-the-call/`, or reference `SKILL.md` from `AGENTS.md` |
| Cursor | `.cursor/skills/follow-the-call/`, or a project rule that points at `SKILL.md` |
| Gemini CLI, OpenCode, Copilot, others | Load `SKILL.md` (or `SKILL.zh-CN.md`) as instructions and keep `scripts/trail.py` reachable |

```bash
git clone https://github.com/fangdididi/follow-the-call ~/.claude/skills/follow-the-call
```

## Usage

Ask in plain words:

> What happens between clicking "Refund" and Stripe being called? Write it as a trail.

> I'm new to this repo. Walk me through how a login request is handled.

> You just built the export feature. Show me the path an export job takes, and prove each hop.

> Our docs/trails are a year old. Check which ones still hold.

Or run the helper directly:

```bash
python3 scripts/trail.py scan .                                  # where to start
python3 scripts/trail.py new > docs/trails/refund.trail.md       # empty trail
python3 scripts/trail.py check docs/trails/refund.trail.md --root .
python3 scripts/trail.py check docs/trails/refund.trail.md --root . --fix
python3 scripts/trail.py quiz docs/trails/refund.trail.md --answers
```

CI (fail the build when a trail rots):

```bash
for t in docs/trails/*.trail.md; do python3 scripts/trail.py check "$t" --root . --strict || exit 1; done
```

## Example

`examples/tiny-notes/` is a two-sided toy app; `examples/save-a-note.trail.md` follows a note from the browser form to the SQLite row in seven stops.

```text
$ python3 scripts/trail.py check examples/save-a-note.trail.md --root examples/tiny-notes
# Trail check: Saving a note

**Verdict: WALKABLE** - 7 stop(s); no findings

Question: What happens between pressing "Save" in the editor and the note row existing in SQLite?

Every anchor resolves, every hop is visible. Safe to hand to the reader.
```

After someone adds an import at the top of `store.py`:

```text
**Verdict: WALKABLE_AFTER_FIX** - 7 stop(s); FIX 1

| Level | Code | Stop | What to do |
|---|---|---|---|
| FIX | MOVED | 7 | Quote moved from line 10 to 11. |
```

After someone renames `insert_note` to `add_note`:

```text
**Verdict: NEEDS_EYES** - 7 stop(s); CHECK 1

| CHECK | HOP_UNSEEN | 6 | Stop 6 says `calls insert_note`, but `insert_note` does not appear in `server/store.py` (stop 7). ... |
```

## File structure

```
follow-the-call/
├── SKILL.md              # agent instructions (English)
├── SKILL.zh-CN.md        # agent instructions (Chinese)
├── README.md
├── README.zh-CN.md
├── LICENSE
├── scripts/
│   └── trail.py          # scan / check / quiz / new
├── examples/
│   ├── save-a-note.trail.md
│   └── tiny-notes/       # toy app the example trail walks through
└── tests/
    └── test_trail.py
```

## Limits

- `scan` is static: dependency injection, reflection, plugin loaders and string-built names are invisible to it. That is exactly why the trail itself, not the scan, is the deliverable.
- `check` proves anchors and hops exist; it cannot prove a `says` sentence is a correct reading of the code. `HEDGED`, `FILE_CHANGED` and teach-back questions are there to keep that part honest.

## License

MIT
