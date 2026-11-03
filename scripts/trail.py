#!/usr/bin/env python3
"""follow-the-call helper: map a repo, check an anchored code trail, pull out its questions.

Commands
  scan  ROOT                 entry points, request doors, hubs, reading order hint
  check TRAIL --root ROOT    verify every stop of a trail against the code
  quiz  TRAIL                print the trail's teach-back questions
  new                        print an empty trail to fill in

Standard library only. Python 3.8+.
"""
import argparse
import json
import os
import re
import subprocess
import sys

SKIP_DIRS = {".git", "node_modules", "dist", "build", "out", ".next", ".nuxt", "vendor",
             "__pycache__", ".venv", "venv", "env", ".tox", "target", "coverage", ".cache",
             ".idea", ".vscode", "site-packages", ".turbo", ".svelte-kit"}
PY_EXT = (".py",)
JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
GO_EXT = (".go",)
CODE_EXT = PY_EXT + JS_EXT + GO_EXT
MAX_FILE_BYTES = 1_500_000

HOP_VERBS = ("calls", "imports", "reads", "writes", "sends", "receives", "handles",
             "returns", "renders", "emits", "listens", "configures", "triggers",
             "queries", "loads", "dispatches", "throws")
HEDGES = ("probably", "maybe", "i think", "i guess", "seems to", "might be", "presumably",
          "可能", "大概", "应该是", "似乎", "好像")
LEVELS = ("BREAK", "CHECK", "FIX", "NOTE")


# ---------------------------------------------------------------- utilities
def read_text(path):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def norm(s):
    return " ".join(s.split())


def walk_code(root):
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") or d == ".github")
        for f in sorted(files):
            if f.endswith(CODE_EXT) and not f.endswith(".d.ts"):
                full = os.path.join(base, f)
                yield os.path.relpath(full, root).replace(os.sep, "/")


# ---------------------------------------------------------------- scan
PY_IMPORT = re.compile(r"^[ \t]*(?:from[ \t]+(\.*[\w\.]*)[ \t]+import[ \t]+(\([^)]*\)|[\w \t,\*]+)|import[ \t]+([\w\., \t]+))", re.M)
JS_IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|require\s*\(\s*|export\s[^'"]*?from\s*|import\s+)['"]([^'"]+)['"]""")
DOOR_PATTERNS = [
    ("http", re.compile(r"""@(?:\w+\.)?(?:route|get|post|put|patch|delete|api_view|websocket)\s*\(\s*['"]([^'"]+)""")),
    ("http", re.compile(r"""\b[A-Za-z_]\w*\.(?:get|post|put|patch|delete|all|route|use|handle|Handle|HandleFunc|GET|POST|PUT|DELETE|PATCH|Get|Post|Put|Delete)\s*\(\s*['"`](/[^'"`]*)""")),
    ("http", re.compile(r"""\bpath\s*\(\s*['"]([^'"]*)['"]""")),
    ("cli", re.compile(r"""\b(?:add_parser|command|add_command)\s*\(\s*['"]([\w\-:]+)""")),
    ("job", re.compile(r"""@(?:\w+\.)?(?:task|shared_task|scheduled_job|cron|job)\b(?:\s*\(\s*['"]?([^'")]*))?""")),
    ("event", re.compile(r"""\.(?:on|subscribe|addEventListener|consume)\s*\(\s*['"`]([\w\.\-:/]+)""")),
]
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)(/|$)|(_test|\.test|\.spec)\.|(^|/)test_[^/]*$")
ENTRY_NAMES = {"main", "index", "app", "server", "cli", "manage", "wsgi", "asgi", "__main__", "cmd", "run", "start"}


def _py_module_index(files):
    idx = {}
    for f in files:
        if not f.endswith(".py"):
            continue
        parts = f[:-3].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        for cut in range(len(parts)):  # allow src/ or other prefix layouts
            mod = ".".join(parts[cut:])
            if mod and mod not in idx:
                idx[mod] = f
    return idx


def _resolve_py(src, mod, names, modidx, fileset):
    out = []
    if mod.startswith("."):
        dots = len(mod) - len(mod.lstrip("."))
        base = src.split("/")[:-1]
        if dots > 1:
            base = base[: len(base) - (dots - 1)] if len(base) >= dots - 1 else []
        rest = mod.lstrip(".")
        cands = []
        stem = "/".join(base + (rest.split(".") if rest else []))
        cands.append(stem)
        for n in names:
            cands.append((stem + "/" if stem else "") + n)
        for c in cands:
            for p in (c + ".py", c + "/__init__.py"):
                if p.lstrip("/") in fileset:
                    out.append(p.lstrip("/"))
                    break
        return out
    for n in names:
        if mod + "." + n in modidx:
            out.append(modidx[mod + "." + n])
    if mod in modidx:
        out.append(modidx[mod])
    return out


def _resolve_js(src, spec, fileset):
    if not spec.startswith("."):
        return []
    base = os.path.normpath(os.path.join(os.path.dirname(src), spec)).replace(os.sep, "/")
    stem = re.sub(r"\.(js|jsx|mjs|cjs)$", "", base)
    for cand in [base] + [stem + e for e in JS_EXT] + [base + "/index" + e for e in JS_EXT]:
        if cand in fileset:
            return [cand]
    return []


def scan(root, top=12):
    root = os.path.abspath(root)
    files = list(walk_code(root))
    fileset = set(files)
    modidx = _py_module_index(files)
    out_edges = {f: set() for f in files}
    lang = {"python": 0, "js/ts": 0, "go": 0}
    entries, doors = [], []
    for f in files:
        text = read_text(os.path.join(root, f)) or ""
        if f.endswith(PY_EXT):
            lang["python"] += 1
            for m in PY_IMPORT.finditer(text):
                if m.group(1) is not None:
                    names = [n.strip().split(" as ")[0].strip("() \n\t") for n in m.group(2).strip("()").split(",")]
                    targets = _resolve_py(f, m.group(1), [n for n in names if n and n != "*"], modidx, fileset)
                else:
                    targets = []
                    for mod in m.group(3).split(","):
                        mod = mod.strip().split(" as ")[0].strip()
                        if mod in modidx:
                            targets.append(modidx[mod])
                out_edges[f].update(t for t in targets if t != f)
            if re.search(r"""if\s+__name__\s*==\s*['"]__main__['"]""", text):
                entries.append((f, "has a __main__ block"))
        elif f.endswith(JS_EXT):
            lang["js/ts"] += 1
            for m in JS_IMPORT.finditer(text):
                out_edges[f].update(t for t in _resolve_js(f, m.group(1), fileset) if t != f)
        else:
            lang["go"] += 1
            if re.search(r"^package\s+main\b", text, re.M) and re.search(r"^func\s+main\s*\(", text, re.M):
                entries.append((f, "Go package main with func main"))
        if TEST_PATH.search(f):
            continue
        door_seen = set()
        for kind, rx in DOOR_PATTERNS:
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                if line in door_seen:
                    continue
                door_seen.add(line)
                name = (m.group(1) or "").strip()
                if kind == "job":
                    d = re.compile(r"(?:def|function)\s+(\w+)").search(text, m.end())
                    name = d.group(1) if d else "(unnamed)"
                doors.append({"kind": kind, "name": name or "(unnamed)", "at": "%s:%d" % (f, line)})
    # package.json entry points
    pj = os.path.join(root, "package.json")
    if os.path.isfile(pj):
        try:
            with open(pj, encoding="utf-8") as fh:
                data = json.load(fh)
            cands = []
            if isinstance(data.get("main"), str):
                cands.append(("main", data["main"]))
            b = data.get("bin")
            if isinstance(b, str):
                cands.append(("bin", b))
            elif isinstance(b, dict):
                cands += [("bin " + k, v) for k, v in b.items() if isinstance(v, str)]
            for why, p in cands:
                p = os.path.normpath(p).replace(os.sep, "/")
                hit = _resolve_js("x", "./" + p, fileset) or ([p] if p in fileset else [])
                if hit:
                    entries.append((hit[0], "package.json " + why))
        except (OSError, ValueError):
            pass
    fan_in = {f: 0 for f in files}
    for f, ts in out_edges.items():
        for t in ts:
            fan_in[t] += 1
    seen_entries = {e[0] for e in entries}
    for f in files:
        name = f.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if name in ENTRY_NAMES and f.count("/") <= 2 and f not in seen_entries and out_edges[f]:
            entries.append((f, "conventional entry name, imports %d local file(s)" % len(out_edges[f])))
            seen_entries.add(f)
    hubs = sorted((f for f in files if fan_in[f] > 0), key=lambda f: (-fan_in[f], f))[:top]
    # reading order: from the first entry, depth-first, dependencies before dependents
    order = []
    if entries:
        visited = set()

        def visit(n, depth):
            if n in visited or depth > 40:
                return
            visited.add(n)
            for t in sorted(out_edges[n], key=lambda x: (-fan_in[x], x)):
                visit(t, depth + 1)
            order.append(n)
        for e in entries[:3]:
            visit(e[0], 0)
    orphans = [f for f in files if fan_in[f] == 0 and not out_edges[f] and f not in seen_entries
               and not TEST_PATH.search(f)]
    return {
        "root": root,
        "files": len(files),
        "languages": {k: v for k, v in lang.items() if v},
        "entries": [{"file": f, "why": w} for f, w in entries],
        "doors": doors[:200],
        "hubs": [{"file": f, "imported_by": fan_in[f], "imports": len(out_edges[f])} for f in hubs],
        "reading_order": order[:top * 2],
        "loose_files": orphans[:top],
        "edges": sum(len(v) for v in out_edges.values()),
    }


def scan_markdown(r):
    L = ["# Map of `%s`" % r["root"], "",
         "%d code files, %d local import edges. Languages: %s." % (
             r["files"], r["edges"], ", ".join("%s %d" % kv for kv in r["languages"].items()) or "none"), ""]
    L.append("## Entry points (where execution starts)")
    L += ["- `%s` - %s" % (e["file"], e["why"]) for e in r["entries"]] or ["- none found; ask the user how the program is started"]
    L += ["", "## Doors (where requests, commands, jobs or events come in)"]
    L += ["- %s `%s` at `%s`" % (d["kind"], d["name"], d["at"]) for d in r["doors"][:40]] or ["- none found by pattern; search for the framework's routing call"]
    if len(r["doors"]) > 40:
        L.append("- ... %d more (use --json)" % (len(r["doors"]) - 40))
    L += ["", "## Hubs (most imported; read these early, change them carefully)"]
    L += ["- `%s` - imported by %d, imports %d" % (h["file"], h["imported_by"], h["imports"]) for h in r["hubs"]] or ["- no local imports resolved"]
    L += ["", "## Reading order hint (dependencies first, from the first entry points)"]
    L += ["%d. `%s`" % (i, f) for i, f in enumerate(r["reading_order"], 1)] or ["- no entry point to start from"]
    if r["loose_files"]:
        L += ["", "## Loose files (nothing imports them, they import nothing local)"]
        L += ["- `%s`" % f for f in r["loose_files"]]
    L += ["", "_Static import resolution only: dynamic imports, dependency injection, reflection and config-driven wiring are invisible here. Treat this as a starting map, not as the trail._"]
    return "\n".join(L)


# ---------------------------------------------------------------- trail parsing
HEADER_KEYS = ("question", "reader", "rev", "start", "repo")
STOP_KEYS = ("at", "quote", "says", "next", "ask", "answer")
STOP_HEAD = re.compile(r"^##\s+(?:(\d+)[\.\)]\s*)?(.*)$")
FIELD = re.compile(r"^([A-Za-z_]+)\s*:\s?(.*)$")


def parse_trail(text):
    trail = {"title": "", "header": {}, "stops": [], "problems": []}
    cur = None
    in_fence = False
    lines = text.splitlines()
    for i, raw in enumerate(lines, 1):
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if raw.startswith("# ") and not trail["title"]:
            trail["title"] = re.sub(r"^(?:trail|路线)\s*[:：]\s*", "", raw[2:].strip(), flags=re.I)
            continue
        m = STOP_HEAD.match(raw)
        if m and raw.startswith("## "):
            cur = {"n": len(trail["stops"]) + 1, "name": m.group(2).strip(), "line": i, "fields": {}, "field_lines": {}}
            trail["stops"].append(cur)
            continue
        fm = FIELD.match(raw.strip())
        if fm:
            key, val = fm.group(1).lower(), fm.group(2).strip()
            if cur is None:
                if key in HEADER_KEYS:
                    trail["header"][key] = val
            elif key in STOP_KEYS:
                if key == "quote":
                    val = val.strip()
                    if len(val) >= 2 and val[0] == val[-1] == "`":
                        val = val[1:-1]
                cur["fields"][key] = val
                cur["field_lines"][key] = i
            continue
        if cur is not None and raw.strip() and cur["fields"]:
            # continuation lines extend the last prose field
            last = list(cur["fields"].keys())[-1]
            if last in ("says", "ask", "answer"):
                cur["fields"][last] += " " + raw.strip()
    return trail


AT_RX = re.compile(r"^(.+?):(\d+)(?:-(\d+))?$")


def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def check_trail(text, root, max_stops=12):
    root = os.path.abspath(root)
    t = parse_trail(text)
    findings = []

    def add(level, code, stop, msg, fix=None):
        findings.append({"level": level, "code": code, "stop": stop, "msg": msg, "fix": fix})

    h = t["header"]
    if not h.get("question"):
        add("CHECK", "NO_QUESTION", 0, "Header has no `question:`. A trail answers one question; write it down.")
    if not h.get("reader"):
        add("NOTE", "NO_READER", 0, "Header has no `reader:`. Say who the trail is for so the prose can be pitched right.")
    stops = t["stops"]
    if not stops:
        add("BREAK", "NO_STOPS", 0, "No `## ` stops found.")
    if len(stops) > max_stops:
        add("NOTE", "LONG_TRAIL", 0, "%d stops (limit %d). Split into two trails or fold glue stops into `says`." % (len(stops), max_stops))
    elif 0 < len(stops) < 3:
        add("NOTE", "SHORT_TRAIL", 0, "Only %d stop(s). Fine for a tiny question; otherwise the trail probably skips hops." % len(stops))

    # revision drift
    rev = h.get("rev", "").strip()
    changed = None
    if rev:
        head = _git(root, "rev-parse", "HEAD")
        full = _git(root, "rev-parse", "--verify", "--quiet", rev + "^{commit}")
        if head is None:
            add("NOTE", "NO_GIT", 0, "`rev: %s` given but ROOT is not a git checkout; drift between revisions not checked." % rev)
        elif full is None:
            add("CHECK", "REV_UNKNOWN", 0, "`rev: %s` is not a commit in this checkout (shallow clone or rewritten history?)." % rev)
        elif full != head:
            diff = _git(root, "diff", "--name-only", full, "HEAD")
            changed = set(diff.splitlines()) if diff else set()
            add("NOTE", "REV_MOVED", 0, "Trail written at %s, checkout is at %s; %d file(s) changed since." % (rev[:12], head[:12], len(changed)),
                fix={"rev": head[:12]})

    seen_at = {}
    resolved = []
    for s in stops:
        f = s["fields"]
        n = s["n"]
        for k in ("at", "quote", "says"):
            if not f.get(k):
                add("BREAK" if k in ("at", "quote") else "CHECK", "MISSING_" + k.upper(), n,
                    "Stop %d has no `%s:`." % (n, k))
        if n < len(stops) and not f.get("next"):
            add("CHECK", "MISSING_NEXT", n, "Stop %d does not say how control or data reaches stop %d (`next: <verb> <symbol>`)." % (n, n + 1))
        says = f.get("says", "").lower()
        hedge = [w for w in HEDGES if w in says]
        if hedge and "unverified" not in says:
            add("CHECK", "HEDGED", n, "`says` hedges (%s). Verify it in the code, or prefix the claim with `unverified:`." % ", ".join(hedge))
        file_text = None
        rel = None
        at = f.get("at", "")
        m = AT_RX.match(at) if at else None
        if at and not m:
            add("BREAK", "BAD_AT", n, "`at: %s` is not `path:line`." % at)
        if m:
            rel = m.group(1).strip().replace("\\", "/")
            line_no = int(m.group(2))
            full = os.path.abspath(os.path.join(root, rel))
            if os.path.isabs(rel) or not (full == root or full.startswith(root + os.sep)):
                add("BREAK", "OUTSIDE_ROOT", n, "`%s` points outside the repo root." % rel)
                rel = None
            elif not os.path.isfile(full):
                add("BREAK", "FILE_GONE", n, "`%s` does not exist." % rel)
                rel = None
            else:
                file_text = read_text(full)
                if file_text is None:
                    add("BREAK", "UNREADABLE", n, "`%s` could not be read (too large or not text)." % rel)
                    rel = None
            if rel and changed is not None and rel in changed:
                add("NOTE", "FILE_CHANGED", n, "`%s` changed since rev; reread the stop even if the quote still matches." % rel)
            key = (rel, f.get("quote", ""))
            if rel and key in seen_at:
                add("NOTE", "REVISIT", n, "Same anchor as stop %d. Intentional (a return trip) or a duplicate?" % seen_at[key])
            elif rel:
                seen_at[key] = n
            q = f.get("quote", "")
            if rel and file_text is not None and q:
                lines = file_text.splitlines()
                nq = norm(q)
                if len(re.sub(r"\s", "", q)) < 8:
                    add("CHECK", "WEAK_QUOTE", n, "Quote `%s` is too short to pin a line; quote at least 8 non-space characters." % q)
                hits = [i for i, l in enumerate(lines, 1) if nq and nq in norm(l)]
                if 1 <= line_no <= len(lines) and nq and nq in norm(lines[line_no - 1]):
                    if len(hits) > 1:
                        add("NOTE", "QUOTE_REPEATS", n, "Quote also appears on line(s) %s; the line number is doing the pinning." % ", ".join(str(x) for x in hits if x != line_no)[:80])
                elif not hits:
                    if line_no > len(lines):
                        add("BREAK", "LINE_OUT", n, "`%s` has %d lines, anchor says %d, and the quote is nowhere in the file." % (rel, len(lines), line_no))
                    else:
                        add("BREAK", "QUOTE_GONE", n, "Quote not found anywhere in `%s`. The code changed; re-walk this stop." % rel)
                elif len(hits) == 1:
                    add("FIX", "MOVED", n, "Quote moved from line %d to %d." % (line_no, hits[0]), fix={"at": "%s:%d" % (rel, hits[0])})
                else:
                    best = min(hits, key=lambda x: abs(x - line_no))
                    add("CHECK", "MOVED_AMBIGUOUS", n, "Quote not on line %d; found on lines %s. Nearest is %d; confirm it is the right one." % (
                        line_no, ", ".join(map(str, hits[:8])), best), fix={"at": "%s:%d" % (rel, best)})
        resolved.append((s, rel, file_text))

    # hops: the named symbol must be visible in the next stop's file
    for i, (s, rel, txt) in enumerate(resolved[:-1]):
        nxt = s["fields"].get("next", "")
        if not nxt:
            continue
        parts = nxt.split(None, 1)
        verb = parts[0].lower()
        if verb not in HOP_VERBS:
            add("CHECK", "BAD_HOP", s["n"], "`next: %s` - start with one of: %s." % (nxt, ", ".join(HOP_VERBS)))
            continue
        if len(parts) < 2:
            add("CHECK", "BAD_HOP", s["n"], "`next: %s` names no symbol, route, table or event." % nxt)
            continue
        sym = parts[1].strip().strip("`'\"")
        sym = re.split(r"\s+(?:in|on|via|from|to|at)\s+", sym)[0].strip("`'\"() ")
        _, nrel, ntxt = resolved[i + 1]
        if not ntxt or not sym:
            continue
        if sym.startswith("unverified:"):
            continue
        rx = re.compile(r"(?<![\w$])" + re.escape(sym) + r"(?![\w$])") if re.match(r"^[\w$.]+$", sym) else None
        tail = sym.split(".")[-1]
        found = (rx.search(ntxt) if rx else sym in ntxt) or (tail != sym and re.search(r"(?<![\w$])" + re.escape(tail) + r"(?![\w$])", ntxt))
        if not found:
            add("CHECK", "HOP_UNSEEN", s["n"], "Stop %d says `%s %s`, but `%s` does not appear in `%s` (stop %d). Missing stop, wrong file, or indirection (DI, config, string route) that needs its own stop." % (
                s["n"], verb, sym, sym, nrel, s["n"] + 1))

    asks = sum(1 for s in stops if s["fields"].get("ask"))
    if stops and asks * 3 < len(stops):
        add("NOTE", "FEW_ASKS", 0, "%d teach-back question(s) for %d stops; aim for one per two or three stops." % (asks, len(stops)))

    levels = {x["level"] for x in findings}
    if "BREAK" in levels:
        verdict = "BROKEN"
    elif "CHECK" in levels:
        verdict = "NEEDS_EYES"
    elif "FIX" in levels:
        verdict = "WALKABLE_AFTER_FIX"
    else:
        verdict = "WALKABLE"
    order = {l: i for i, l in enumerate(LEVELS)}
    findings.sort(key=lambda x: (order[x["level"]], x["stop"]))
    return {"title": t["title"], "question": h.get("question", ""), "stops": len(stops),
            "verdict": verdict, "findings": findings,
            "counts": {l: sum(1 for x in findings if x["level"] == l) for l in LEVELS}}


def apply_fixes(text, report, include_ambiguous=False):
    """Rewrite `at:` lines (and `rev:`) for fixable findings. Returns new text."""
    t = parse_trail(text)
    lines = text.splitlines(True)
    blocking = any(x["level"] in ("BREAK", "CHECK") for x in report["findings"])
    for fnd in report["findings"]:
        fx = fnd.get("fix")
        if not fx:
            continue
        if fnd["code"] == "MOVED_AMBIGUOUS" and not include_ambiguous:
            continue
        if "at" in fx and fnd["stop"]:
            s = t["stops"][fnd["stop"] - 1]
            ln = s["field_lines"].get("at")
            if ln:
                old = lines[ln - 1]
                lead = old[: len(old) - len(old.lstrip())]
                end = "\n" if old.endswith("\n") else ""
                lines[ln - 1] = "%sat: %s%s" % (lead, fx["at"], end)
        if "rev" in fx and not blocking:
            for i, l in enumerate(lines):
                if re.match(r"^\s*rev\s*:", l):
                    lines[i] = re.sub(r"(rev\s*:\s*).*", lambda m: m.group(1) + fx["rev"], l.rstrip("\n")) + ("\n" if l.endswith("\n") else "")
                    break
    return "".join(lines)


def check_markdown(r):
    L = ["# Trail check: %s" % (r["title"] or "(untitled)"), "",
         "**Verdict: %s** - %d stop(s); %s" % (r["verdict"], r["stops"],
                                              ", ".join("%s %d" % (k, v) for k, v in r["counts"].items() if v) or "no findings"), ""]
    if r["question"]:
        L += ["Question: %s" % r["question"], ""]
    if r["findings"]:
        L += ["| Level | Code | Stop | What to do |", "|---|---|---|---|"]
        for x in r["findings"]:
            L.append("| %s | %s | %s | %s |" % (x["level"], x["code"], x["stop"] or "-", x["msg"].replace("|", "\\|")))
    L += ["", {"WALKABLE": "Every anchor resolves, every hop is visible. Safe to hand to the reader.",
               "WALKABLE_AFTER_FIX": "Only line numbers drifted. Run again with --fix, then hand it over.",
               "NEEDS_EYES": "Anchors resolve but some hops or claims need a human/agent look before handing over.",
               "BROKEN": "At least one stop no longer points at real code. Re-walk the broken stops first."}[r["verdict"]]]
    return "\n".join(L)


# ---------------------------------------------------------------- quiz
def quiz(text, answers=False):
    t = parse_trail(text)
    L = ["# Teach-back: %s" % (t["title"] or "(untitled)"), ""]
    if t["header"].get("question"):
        L += ["After walking this trail you should be able to answer: _%s_" % t["header"]["question"], ""]
    k = 0
    for s in t["stops"]:
        q = s["fields"].get("ask")
        if not q:
            continue
        k += 1
        L.append("%d. %s  _(stop %d, `%s`)_" % (k, q, s["n"], s["fields"].get("at", "?")))
        if answers:
            L.append("   - answer: %s" % (s["fields"].get("answer") or "(no `answer:` written - derive it from the stop)"))
    if k == 0:
        L.append("_This trail has no `ask:` lines._")
    return "\n".join(L)


TEMPLATE = """# Trail: <short title>
question: <the one question this trail answers, in the reader's words>
reader: <who will walk it and what they already know>
rev: <git commit the trail was walked at>
start: <the outside event that begins it: a click, a request, a cron tick, a CLI call>

## 1. <where it enters>
at: path/to/file.ext:LINE
quote: <one exact line fragment from that line, 8+ characters>
says: <what happens here, and why it matters to the question>
next: calls <symbolVisibleInNextFile>
ask: <a question the reader can answer only by reading this stop>

## 2. <next place>
at: path/to/other.ext:LINE
quote: <exact fragment>
says: <...>
next: writes <table_or_symbol>

## 3. <where it ends>
at: path/to/last.ext:LINE
quote: <exact fragment>
says: <the outcome the question was about>
ask: <...>
answer: <optional, for the answer key>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(prog="trail.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan", help="map entry points, doors, hubs")
    p.add_argument("root")
    p.add_argument("--json", action="store_true")
    p.add_argument("--top", type=int, default=12)
    p = sub.add_parser("check", help="verify a trail against the code")
    p.add_argument("trail")
    p.add_argument("--root", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--fix", action="store_true", help="rewrite drifted line numbers (and rev) in the trail file")
    p.add_argument("--fix-ambiguous", action="store_true", help="with --fix, also take the nearest match for ambiguous moves")
    p.add_argument("--max-stops", type=int, default=12)
    p.add_argument("--strict", action="store_true", help="exit 1 on NEEDS_EYES/WALKABLE_AFTER_FIX, 2 on BROKEN")
    p = sub.add_parser("quiz", help="print the teach-back questions")
    p.add_argument("trail")
    p.add_argument("--answers", action="store_true")
    sub.add_parser("new", help="print an empty trail")
    a = ap.parse_args(argv)

    if a.cmd == "new":
        print(TEMPLATE, end="")
        return 0
    if a.cmd == "scan":
        if not os.path.isdir(a.root):
            print("not a directory: %s" % a.root, file=sys.stderr)
            return 2
        r = scan(a.root, a.top)
        print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else scan_markdown(r))
        return 0
    try:
        text = open(a.trail, encoding="utf-8").read()
    except OSError as e:
        print("cannot read trail: %s" % e, file=sys.stderr)
        return 2
    if a.cmd == "quiz":
        print(quiz(text, a.answers))
        return 0
    r = check_trail(text, a.root, a.max_stops)
    if a.fix:
        new = apply_fixes(text, r, a.fix_ambiguous)
        if new != text:
            with open(a.trail, "w", encoding="utf-8") as fh:
                fh.write(new)
            r = check_trail(new, a.root, a.max_stops)
            r["fixed"] = True
    print(json.dumps(r, indent=1, ensure_ascii=False) if a.json else check_markdown(r))
    if a.strict:
        return {"WALKABLE": 0, "WALKABLE_AFTER_FIX": 1, "NEEDS_EYES": 1, "BROKEN": 2}[r["verdict"]]
    return 0


if __name__ == "__main__":
    sys.exit(main())
