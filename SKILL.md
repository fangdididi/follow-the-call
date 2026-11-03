---
name: follow-the-call
description: Answer "what actually happens when X?" about a codebase by walking one path through the real code and writing it down as an anchored trail - numbered stops, each pinned to file:line with an exact quoted fragment, a plain-language explanation, the hop to the next stop, and teach-back questions. A helper script maps entry points and request doors, verifies every anchor and hop against the current code, repairs drifted line numbers, and flags stops that rotted. Use for onboarding, explaining a feature, debugging a flow, or reviewing what an agent built.
---

# follow-the-call

**Language:** English | [简体中文](SKILL.zh-CN.md)

## What this skill is

A codebase is understood one path at a time. Overview maps and diagrams tell you which boxes exist; they do not tell you what happens, in order, when someone presses Save. This skill produces the second thing: a **trail**.

A trail is a short Markdown file that answers one question by following one real execution path. Each **stop** is pinned to the code:

```
## 4. The handler cleans the title
at: server/routes.py:9
quote: title = clean_title(request["json"].get("title", ""))
says: The title is normalised before anything else; a missing key becomes an empty string.
next: calls clean_title
ask: A user pastes a 300-character title. What is stored?
```

Because every stop carries an exact quote and every hop names a symbol, a script can prove the trail is still true: the quote is on that line (or has moved, and where to), and the symbol the hop names really appears in the next stop's file. A trail that passes is something a newcomer can walk with their editor open, and something you can re-check in CI after the code changes.

## Problem it solves

- "Explain how checkout works" usually produces a confident essay with invented function names, or a tour of folders that never answers the question.
- Hand-written onboarding docs rot silently. Nobody notices that `services/billing.py:120` is now a comment.
- Diagrams show structure, not sequence; they skip the glue (middleware, a queue, a config-driven route) where people actually get lost.
- After an agent writes a feature, the human often cannot say what path a request takes through it.

## When to use

- "What happens when a user ...", "How does X get from A to B", "Where does this value come from".
- Onboarding a person (or a fresh agent session) onto one feature of an unfamiliar repo.
- Writing or refreshing a walkthrough in `docs/` that must stay correct.
- Debugging: tracing the real path before guessing where a bug lives.
- Reviewing agent-written code: make the agent walk its own feature and prove each hop.

Not for: a whole-system architecture picture (draw a diagram), reading one function (just read it), or questions about behaviour that only exists at runtime and cannot be pinned to code (logs, traces and profilers answer those).

## Step by step

### 1. Pin the question and the reader

Write the header before reading any code.

```
# Trail: Refund to card
question: After support clicks "Refund", what code runs until the payment provider is told?
reader: support-tools developer, knows Django, never touched billing
rev: <current commit>
start: support agent clicks Refund on an order page
```

- **One question, one path.** "How does billing work" is a curriculum, not a trail. Narrow it to a trigger and an outcome.
- **Name the reader** and what they already know; that sets how much each `says` explains.
- **Record `rev`** (`git rev-parse --short HEAD`) so later checks can tell which stops sit in changed files.

### 2. Find the door

Every path starts where something enters the program: an HTTP route, a CLI command, a scheduled job, a queue consumer, a UI event.

```bash
python3 scripts/trail.py scan path/to/repo
```

The scan lists entry points, doors (routes, commands, jobs, event listeners) with `file:line`, the most-imported hub files, and a dependencies-first reading order. It is static and partial; use it to choose where to start, then confirm with search (`rg "refund"`, the route path, the button label, the event name).

If the trigger is in another repo or service, the first stop is the boundary on this side (the handler that receives it) and `says` names where it came from.

### 3. Walk, one hop at a time

From the door, follow what actually executes. At each place that matters to the question:

1. Open the file and read the surrounding function, not just the line.
2. Copy an exact fragment (8+ characters) from **one** line into `quote`. Prefer the line that does the work: the call, the write, the branch.
3. Write `says` in plain language for the named reader: what happens here and why it matters to the question. State facts you saw. If you are inferring, prefix with `unverified:`.
4. Write `next: <verb> <symbol>` - how control or data reaches the next stop. Verbs: calls, imports, reads, writes, sends, receives, handles, returns, renders, emits, listens, configures, triggers, queries, loads, dispatches, throws. The symbol (function, method, route, table, event, key) must be visible in the next stop's file.
5. Every two or three stops, add an `ask:` that can only be answered by reading that stop - and optionally `answer:`.

What makes a stop worth having:

- **Decisions**: branches, guards, early returns, permission checks.
- **Boundaries**: network calls, queue publish/consume, DB writes, file I/O, process spawns.
- **Indirection**: anything that cannot be found by "go to definition" - dependency injection, a string-keyed route table, a signal/event, a config file that wires a class name, a decorator that registers a handler. These are the stops people need most; give each one its own stop.
- **Transformations** that change the answer (validation, truncation, currency conversion, defaults).

Skip pass-through glue: a wrapper that only forwards arguments becomes one clause of the previous `says`.

Keep it to **3-12 stops**. Longer means the question is two questions.

### 4. Verify

```bash
python3 scripts/trail.py check docs/trails/refund.trail.md --root .
```

Findings come in four levels:

| Level | Codes | Meaning |
|---|---|---|
| BREAK | FILE_GONE, QUOTE_GONE, LINE_OUT, BAD_AT, OUTSIDE_ROOT, MISSING_AT, MISSING_QUOTE, NO_STOPS | The stop no longer points at real code. Re-walk it. |
| CHECK | HOP_UNSEEN, MOVED_AMBIGUOUS, BAD_HOP, MISSING_NEXT, HEDGED, WEAK_QUOTE, REV_UNKNOWN, NO_QUESTION | Needs a look: a hop that cannot be seen, a vague claim, an anchor that could be one of several lines. |
| FIX | MOVED | The quote is intact but on another line. `--fix` rewrites the line number. |
| NOTE | REV_MOVED, FILE_CHANGED, REVISIT, QUOTE_REPEATS, LONG_TRAIL, SHORT_TRAIL, FEW_ASKS, NO_READER, NO_GIT | Information for the author. |

Verdict: **WALKABLE**, **WALKABLE_AFTER_FIX**, **NEEDS_EYES**, or **BROKEN**.

How to resolve the common ones:

- **HOP_UNSEEN**: the symbol named in `next` is not in the next file. Either a stop is missing (the call goes through a module you skipped), the wrong file is anchored, or the link is indirect. For indirection, add the wiring stop (the registry, the config line, the DI binding) rather than weakening the hop.
- **MOVED_AMBIGUOUS**: the quote now appears on several lines. Lengthen the quote until it is unique, then re-run.
- **HEDGED**: "probably", "seems to", "可能". Go and check, or label the claim `unverified:` so the reader knows.
- **FILE_CHANGED** (after `rev` moved): the quote still matches, but the file changed since the trail was walked. Reread that stop's `says`; logic can change around an unchanged line.

Do not hand a trail over until it is WALKABLE (or NEEDS_EYES with every remaining CHECK explained in the trail).

### 5. Hand it over

- Present the trail itself, not a summary of it. The reader walks it with their editor open.
- Offer the teach-back questions separately: `python3 scripts/trail.py quiz trail.md` (add `--answers` for the key). If the reader can answer them, the trail worked.
- If you discovered something surprising while walking (dead code, a missing check, an unbounded field), list it after the trail under "Found on the way" with its anchor. Do not fix it unasked.
- Suggest where to keep it (`docs/trails/`) and adding `trail.py check --strict` to CI so the trail fails loudly when the code moves.

### 6. Keep it alive

When code changes, run `check --fix`. Moved lines are repaired automatically and `rev` is bumped only if nothing is broken. BROKEN stops are re-walked from the stop before them.

## Example

Question: *What happens between pressing Save in the editor and the note row existing in SQLite?* (full file in `examples/save-a-note.trail.md`, code in `examples/tiny-notes/`)

| # | at | says (short) | next |
|---|---|---|---|
| 1 | web/editor.js:4 | submit handler builds `{title, body}`; no client validation | calls postNote |
| 2 | web/api.js:2 | POST JSON to /api/notes | sends /api/notes |
| 3 | server/routes.py:15 | route table maps it to `save_note` | calls save_note |
| 4 | server/routes.py:9 | title cleaned first; empty -> 422 | calls clean_title |
| 5 | server/validate.py:5 | whitespace collapsed, cut to 120 chars silently | returns title |
| 6 | server/routes.py:12 | body passed through uncleaned | calls insert_note |
| 7 | server/store.py:10 | parameterised INSERT, id returned as 201 | - |

Found on the way: titles over 120 characters are truncated without telling the user (stop 5); the body has no length limit (stop 6).

When someone later adds an import at the top of `store.py`, `check` reports `MOVED` for stop 7 and `--fix` moves the anchor from line 10 to 11. If someone renames `insert_note` in `store.py`, stop 6's hop becomes `HOP_UNSEEN`; if someone rewrites the validation line, stop 5 becomes `QUOTE_GONE`. The trail fails instead of quietly lying.

## Tips

- Quote the most specific part of the line. `return res.json()` is everywhere; `fetch("/api/notes"` is not.
- One stop per decision, not per file. A file may host three stops; a ten-file chain of thin wrappers may be one.
- For async flows (queues, events, webhooks), the hop verb is `emits`/`sends` on one side and the next stop is the consumer, with `next: emits order.paid` and the consumer file containing `order.paid`. If the name is built dynamically, add a stop at the place where it is built.
- Generated code and vendored libraries: stop at the boundary of your code and say what the library does in one line.
- Monorepos: run `check` with `--root` at the repo root so paths across packages resolve.
- Writing for a non-developer reader: keep the anchors, simplify `says`. The anchors are what make the plain-language version trustworthy.
- If you could not find a hop at all, say so in the trail (`next: calls unverified: whatever reads RETRY_QUEUE`) instead of inventing one; `check` skips symbols marked `unverified:`.

## Files

- `scripts/trail.py` - `scan`, `check` (`--fix`, `--strict`, `--json`), `quiz`, `new`. Python 3.8+, standard library only.
- `examples/` - a tiny two-sided app and a complete trail through it.
- `tests/` - unit tests (`python3 -m unittest discover -s tests`).
