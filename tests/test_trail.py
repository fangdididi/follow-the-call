import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import trail  # noqa: E402

EXAMPLE_REPO = os.path.join(ROOT, "examples", "tiny-notes")
EXAMPLE_TRAIL = os.path.join(ROOT, "examples", "save-a-note.trail.md")


def codes(report):
    return [f["code"] for f in report["findings"]]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "repo")
        shutil.copytree(EXAMPLE_REPO, self.repo)
        self.trail_text = open(EXAMPLE_TRAIL, encoding="utf-8").read()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, rel, old, new):
        p = os.path.join(self.repo, rel)
        s = open(p, encoding="utf-8").read()
        self.assertIn(old, s)
        open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))

    def check(self, text=None):
        return trail.check_trail(text if text is not None else self.trail_text, self.repo)


class ParseTests(unittest.TestCase):
    def test_header_and_stops(self):
        t = trail.parse_trail(open(EXAMPLE_TRAIL, encoding="utf-8").read())
        self.assertEqual(t["title"], "Saving a note")
        self.assertIn("SQLite", t["header"]["question"])
        self.assertEqual(len(t["stops"]), 7)
        self.assertEqual(t["stops"][0]["fields"]["at"], "web/editor.js:4")

    def test_backticked_quote_is_unwrapped(self):
        t = trail.parse_trail("# x\n## 1. a\nat: a.py:1\nquote: `x = compute()`\nsays: s\n")
        self.assertEqual(t["stops"][0]["fields"]["quote"], "x = compute()")

    def test_fenced_blocks_ignored(self):
        t = trail.parse_trail("# x\n```\n## not a stop\nat: z:1\n```\n## 1. real\nat: a.py:1\n")
        self.assertEqual(len(t["stops"]), 1)

    def test_continuation_lines_join_says(self):
        t = trail.parse_trail("# x\n## 1. a\nat: a.py:1\nsays: first part\n  second part\n")
        self.assertEqual(t["stops"][0]["fields"]["says"], "first part second part")

    def test_chinese_title_prefix(self):
        t = trail.parse_trail("# 路线：保存笔记\n")
        self.assertEqual(t["title"], "保存笔记")


class CheckTests(Base):
    def test_example_is_walkable(self):
        r = self.check()
        self.assertEqual(r["verdict"], "WALKABLE", r["findings"])

    def test_moved_line_is_fixable(self):
        self.edit("server/store.py", "import sqlite3\n", "import sqlite3\nimport logging\n\n")
        r = self.check()
        self.assertEqual(r["verdict"], "WALKABLE_AFTER_FIX")
        mv = [f for f in r["findings"] if f["code"] == "MOVED"][0]
        self.assertEqual(mv["fix"]["at"], "server/store.py:12")

    def test_apply_fixes_rewrites_at(self):
        self.edit("server/store.py", "import sqlite3\n", "import sqlite3\nimport logging\n\n")
        r = self.check()
        new = trail.apply_fixes(self.trail_text, r)
        self.assertIn("at: server/store.py:12", new)
        self.assertEqual(self.check(new)["verdict"], "WALKABLE")

    def test_quote_gone_breaks(self):
        self.edit("server/validate.py", 'title = " ".join(str(raw).split())', "title = str(raw).strip()")
        r = self.check()
        self.assertEqual(r["verdict"], "BROKEN")
        self.assertIn("QUOTE_GONE", codes(r))

    def test_whitespace_changes_do_not_break(self):
        self.edit("server/validate.py", 'title = " ".join(str(raw).split())', 'title  =  " ".join(str(raw).split())')
        self.assertEqual(self.check()["verdict"], "WALKABLE")

    def test_file_gone_breaks(self):
        os.remove(os.path.join(self.repo, "web", "api.js"))
        r = self.check()
        self.assertIn("FILE_GONE", codes(r))
        self.assertEqual(r["verdict"], "BROKEN")

    def test_outside_root(self):
        text = self.trail_text.replace("at: web/api.js:2", "at: ../../etc/passwd:1")
        self.assertIn("OUTSIDE_ROOT", codes(self.check(text)))

    def test_bad_at(self):
        text = self.trail_text.replace("at: web/api.js:2", "at: web/api.js")
        self.assertIn("BAD_AT", codes(self.check(text)))

    def test_line_out_of_range(self):
        text = self.trail_text.replace("at: web/api.js:2", "at: web/api.js:900").replace(
            'quote: const res = await fetch("/api/notes", {', "quote: something that is not there")
        self.assertIn("LINE_OUT", codes(self.check(text)))

    def test_ambiguous_move_needs_eyes(self):
        self.edit("server/store.py", "import sqlite3\n",
                  'import sqlite3\n# cur = self.db.execute("INSERT INTO notes (title, body) VALUES (?, ?)", (title, body))\n\n')
        r = self.check()
        self.assertIn("MOVED_AMBIGUOUS", codes(r))
        self.assertEqual(r["verdict"], "NEEDS_EYES")
        # not applied without the flag
        self.assertEqual(trail.apply_fixes(self.trail_text, r), self.trail_text)
        self.assertNotEqual(trail.apply_fixes(self.trail_text, r, include_ambiguous=True), self.trail_text)

    def test_hop_unseen_when_symbol_renamed(self):
        self.edit("server/store.py", "def insert_note", "def add_note")
        r = self.check()
        self.assertIn("HOP_UNSEEN", codes(r))

    def test_hop_with_route_string(self):
        self.edit("server/routes.py", '("POST", "/api/notes")', '("POST", "/api/v2/notes")')
        r = self.check()
        # the anchor quote also changed, so stop 3 breaks; hop from stop 2 must be unseen too
        self.assertIn("HOP_UNSEEN", codes(r))

    def test_dotted_symbol_tail_matches(self):
        text = self.trail_text.replace("next: calls insert_note", "next: calls store.insert_note")
        self.assertEqual(self.check(text)["verdict"], "WALKABLE")

    def test_bad_hop_verb(self):
        text = self.trail_text.replace("next: calls postNote", "next: goes to postNote")
        self.assertIn("BAD_HOP", codes(self.check(text)))

    def test_hop_without_symbol(self):
        text = self.trail_text.replace("next: calls postNote", "next: calls")
        self.assertIn("BAD_HOP", codes(self.check(text)))

    def test_missing_next(self):
        text = self.trail_text.replace("next: calls postNote\n", "")
        self.assertIn("MISSING_NEXT", codes(self.check(text)))

    def test_missing_quote_breaks(self):
        text = self.trail_text.replace('quote: const res = await fetch("/api/notes", {\n', "")
        r = self.check(text)
        self.assertIn("MISSING_QUOTE", codes(r))
        self.assertEqual(r["verdict"], "BROKEN")

    def test_hedge_flagged_and_unverified_allowed(self):
        text = self.trail_text.replace("A parameterised INSERT", "Probably a parameterised INSERT")
        self.assertIn("HEDGED", codes(self.check(text)))
        text2 = self.trail_text.replace("A parameterised INSERT", "unverified: probably a parameterised INSERT")
        self.assertNotIn("HEDGED", codes(self.check(text2)))

    def test_weak_quote(self):
        text = self.trail_text.replace('quote: const res = await fetch("/api/notes", {', "quote: fetch")
        self.assertIn("WEAK_QUOTE", codes(self.check(text)))

    def test_no_question(self):
        text = self.trail_text.replace("question:", "q:")
        self.assertIn("NO_QUESTION", codes(self.check(text)))

    def test_long_trail_note(self):
        r = trail.check_trail(self.trail_text, self.repo, max_stops=5)
        self.assertIn("LONG_TRAIL", codes(r))
        self.assertEqual(r["verdict"], "WALKABLE")

    def test_few_asks(self):
        text = "\n".join(l for l in self.trail_text.splitlines() if not l.startswith("ask:"))
        self.assertIn("FEW_ASKS", codes(self.check(text)))

    def test_no_stops(self):
        r = self.check("# empty\nquestion: q\n")
        self.assertEqual(r["verdict"], "BROKEN")

    def test_findings_sorted_by_level(self):
        os.remove(os.path.join(self.repo, "web", "api.js"))
        text = self.trail_text.replace("A parameterised INSERT", "Maybe a parameterised INSERT")
        r = self.check(text)
        order = [trail.LEVELS.index(f["level"]) for f in r["findings"]]
        self.assertEqual(order, sorted(order))


def git(repo, *args):
    subprocess.run(["git", "-C", repo] + list(args), check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))


@unittest.skipUnless(shutil.which("git"), "git not installed")
class RevTests(Base):
    def setUp(self):
        super().setUp()
        git(self.repo, "init", "-q")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "one")
        self.rev = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def test_same_rev_clean(self):
        text = self.trail_text.replace("start:", "rev: %s\nstart:" % self.rev[:10])
        self.assertEqual(self.check(text)["verdict"], "WALKABLE")

    def test_rev_moved_flags_changed_files(self):
        text = self.trail_text.replace("start:", "rev: %s\nstart:" % self.rev[:10])
        self.edit("server/validate.py", "MAX_TITLE = 120", "MAX_TITLE = 80")
        git(self.repo, "commit", "-qam", "two")
        r = self.check(text)
        self.assertIn("REV_MOVED", codes(r))
        changed = [f for f in r["findings"] if f["code"] == "FILE_CHANGED"]
        self.assertEqual([f["stop"] for f in changed], [5])
        new = trail.apply_fixes(text, r)
        self.assertNotIn("rev: %s\n" % self.rev[:10], new)

    def test_unknown_rev(self):
        text = self.trail_text.replace("start:", "rev: deadbeefdeadbeef\nstart:")
        self.assertIn("REV_UNKNOWN", codes(self.check(text)))

    def test_rev_not_bumped_when_broken(self):
        text = self.trail_text.replace("start:", "rev: %s\nstart:" % self.rev[:10])
        self.edit("server/validate.py", 'title = " ".join(str(raw).split())', "title = str(raw)")
        git(self.repo, "commit", "-qam", "two")
        r = self.check(text)
        self.assertEqual(trail.apply_fixes(text, r), text)


class NoGitTests(Base):
    def test_rev_without_git_is_note(self):
        text = self.trail_text.replace("start:", "rev: abc1234\nstart:")
        r = self.check(text)
        self.assertIn("NO_GIT", codes(r))


class ScanTests(Base):
    def test_entries_hubs_order(self):
        r = trail.scan(self.repo)
        entries = [e["file"] for e in r["entries"]]
        self.assertIn("server/app.py", entries)
        self.assertIn("web/index.js", entries)
        self.assertEqual(r["hubs"][0]["file"], "server/store.py")
        order = r["reading_order"]
        self.assertLess(order.index("server/store.py"), order.index("server/routes.py"))
        self.assertLess(order.index("server/routes.py"), order.index("server/app.py"))
        self.assertLess(order.index("web/api.js"), order.index("web/editor.js"))

    def test_doors(self):
        p = os.path.join(self.repo, "server", "flaskish.py")
        open(p, "w").write("@app.post('/api/login')\ndef login():\n    pass\n\n@app.route(\"/health\")\ndef h():\n    pass\n")
        r = trail.scan(self.repo)
        names = {(d["kind"], d["name"]) for d in r["doors"]}
        self.assertIn(("http", "/api/login"), names)
        self.assertIn(("http", "/health"), names)
        self.assertIn(("event", "submit"), names)

    def test_express_and_go(self):
        os.makedirs(os.path.join(self.repo, "svc"))
        open(os.path.join(self.repo, "svc", "routes.js"), "w").write("router.get('/users/:id', show)\n")
        open(os.path.join(self.repo, "svc", "main.go"), "w").write("package main\n\nfunc main() {\n\thttp.HandleFunc(\"/ping\", ping)\n}\n")
        r = trail.scan(self.repo)
        names = {d["name"] for d in r["doors"]}
        self.assertIn("/users/:id", names)
        self.assertIn("/ping", names)
        self.assertIn("svc/main.go", [e["file"] for e in r["entries"]])

    def test_skips_vendor_dirs(self):
        os.makedirs(os.path.join(self.repo, "node_modules", "x"))
        open(os.path.join(self.repo, "node_modules", "x", "index.js"), "w").write("x")
        self.assertNotIn("node_modules/x/index.js", trail.scan(self.repo)["loose_files"])

    def test_package_json_main(self):
        open(os.path.join(self.repo, "package.json"), "w").write(json.dumps({"main": "web/index.js"}))
        r = trail.scan(self.repo)
        self.assertEqual(r["entries"][1]["why"], "package.json main")

    def test_multiline_python_import(self):
        open(os.path.join(self.repo, "server", "multi.py"), "w").write("from .store import (\n    NoteStore,\n)\nfrom .validate import clean_title\n")
        r = trail.scan(self.repo)
        hub = {h["file"]: h["imported_by"] for h in r["hubs"]}
        self.assertEqual(hub["server/store.py"], 3)
        self.assertEqual(hub["server/validate.py"], 2)


class QuizAndCliTests(Base):
    def test_quiz(self):
        q = trail.quiz(self.trail_text)
        self.assertEqual(q.count("\n1. "), 1)
        self.assertNotIn("   - answer:", q)
        self.assertIn("answer:", trail.quiz(self.trail_text, answers=True))

    def test_cli_check_fix_and_strict(self):
        self.edit("server/store.py", "import sqlite3\n", "import sqlite3\n\n")
        tp = os.path.join(self.tmp, "t.trail.md")
        open(tp, "w").write(self.trail_text)
        script = os.path.join(ROOT, "scripts", "trail.py")
        r = subprocess.run([sys.executable, script, "check", tp, "--root", self.repo, "--strict"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("WALKABLE_AFTER_FIX", r.stdout)
        r = subprocess.run([sys.executable, script, "check", tp, "--root", self.repo, "--fix", "--strict", "--json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(json.loads(r.stdout)["verdict"], "WALKABLE")
        self.assertIn("at: server/store.py:11", open(tp).read())

    def test_cli_new_template_parses(self):
        script = os.path.join(ROOT, "scripts", "trail.py")
        out = subprocess.run([sys.executable, script, "new"], capture_output=True, text=True).stdout
        t = trail.parse_trail(out)
        self.assertEqual(len(t["stops"]), 3)

    def test_cli_broken_exit_code(self):
        os.remove(os.path.join(self.repo, "web", "api.js"))
        script = os.path.join(ROOT, "scripts", "trail.py")
        r = subprocess.run([sys.executable, script, "check", EXAMPLE_TRAIL, "--root", self.repo, "--strict"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
