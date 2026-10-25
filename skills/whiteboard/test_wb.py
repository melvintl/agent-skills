"""Focused whiteboard regressions; run by make check (Python + Node)."""

import argparse
import contextlib
import html.parser
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
MODULE = importlib.util.spec_from_file_location("wb", HERE / "wb.py")
wb = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(wb)


class CopyButtonParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.command = None

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self.command = dict(attrs).get("data-copy", self.command)


class EditorCommandTests(unittest.TestCase):
    def test_copied_command_preserves_literal_paths(self):
        template = (HERE / "template.html").read_text()
        helpers = "\n".join(line for line in template.splitlines()
                            if line.startswith(("const shellQuote =", "const editorCommand =")))
        card = re.search(r"function hunkCard\(id, note\) \{.*?^\}", template, re.M | re.S).group()
        # Exercise the real card, including HTML escaping and attribute decoding.
        script = """
const input = JSON.parse(process.argv[1]);
const M = {repo: input.repo};
const H = {test: {file: input.file, symbols: [], added: 1, removed: 0, new_start: 7, index: 1}};
const hunkChapter = {}, hid = s => s;
let hunkInstance = 0;
const esc = s => String(s).replace(/[&<>"']/g,
    c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
""" + helpers + "\n" + card + '\nconsole.log(hunkCard("test"));'
        filenames = [
            "normal.txt", "space in name.txt", "quote's.txt", '-leading.txt',
            "$(touch WB_COPY_EXECUTED).txt", "`touch WB_COPY_EXECUTED`.txt",
            "semi;touch WB_COPY_EXECUTED;.txt", "line\nbreak.txt", 'double"&<name>.txt',
            "back\\slash.txt", "日本語.txt",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            repo = str(Path(tmp) / "repo's directory")
            for filename in filenames:
                with self.subTest(filename=filename):
                    page = subprocess.run(
                        ["node", "-e", script, json.dumps({"repo": repo, "file": filename})],
                        check=True, capture_output=True, text=True,
                    ).stdout
                    parser = CopyButtonParser()
                    parser.feed(page)
                    self.assertIsNotNone(parser.command)
                    # Replace the editor with an argv recorder in a disposable directory.
                    result = subprocess.run(
                        ["bash", "-c", 'nvim() { printf "%s\\0" "$@"; }\n' + parser.command],
                        cwd=tmp, check=True, capture_output=True,
                    )
                    expected = ["+7", "--", f"{repo}/{filename}"]
                    self.assertEqual(result.stdout.decode().split("\0")[:-1], expected)
                    self.assertFalse((Path(tmp) / "WB_COPY_EXECUTED").exists())


class EmbeddedDataTests(unittest.TestCase):
    def test_script_tokens_are_escaped_and_round_trip(self):
        attack = '<!-- <script> </script><script>alert("bad")</script> & 日本語'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            data = {
                "meta": {"repo": tmp, "repo_name": "fixture", "base": "main", "head": "WORKTREE"},
                "files": [],
                "hunks": [{"id": "file#1", "file": "file", "noise": False, "patch": attack}],
            }
            spec = {"title": "Regression", "summary": attack,
                    "chapters": [{"id": "fixture", "hunks": ["file#1"]}]}
            (out / "hunks.json").write_text(json.dumps(data))
            (out / "spec.json").write_text(json.dumps(spec))
            with contextlib.redirect_stdout(io.StringIO()):
                wb.cmd_render(argparse.Namespace(out=tmp, check=False, shot=False, no_open=True))
            page = (out / "index.html").read_text()
            blob = page.split("const D = ", 1)[1].split(";\nconst S =", 1)[0]
            self.assertNotIn("<", blob)
            restored = json.loads(blob)
            self.assertEqual(restored["hunks"]["file#1"]["patch"], attack)
            self.assertEqual(restored["spec"]["summary"], attack)
            self.assertEqual(page.count("</script>"), 5)


def review_fixture():
    return {
        "verdict": "ready to merge",
        "rationale": "The inspected path and focused checks support this change.",
        "findings": [],
        "validation": [{"command": "make test", "status": "passed", "result": "Focused checks passed."}],
        "challenge": "Checked whether the old entry point bypasses the new guard; it does not.",
        "limits": "External integration behavior was not exercised.",
    }


class ReviewTests(unittest.TestCase):
    def render_spec(self, spec):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            data = {"meta": {"repo": tmp, "repo_name": "fixture", "base": "main", "head": "HEAD"},
                    "files": [], "hunks": [{"id": "file#1", "file": "file", "noise": False}]}
            (out / "hunks.json").write_text(json.dumps(data))
            (out / "spec.json").write_text(json.dumps(spec))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                wb.cmd_render(argparse.Namespace(out=tmp, check=False, shot=False, no_open=True))
            return (out / "index.html").read_text()

    def test_legacy_specs_remain_supported_without_an_assessment(self):
        self.assertEqual(wb.review_errors({}, ["file#1"]), [])
        self.assertIn("Not assessed", self.render_spec({"chapters": []}))

    def test_verdict_requires_consistent_evidence(self):
        review = review_fixture()
        self.assertEqual(wb.review_errors({"review": review}, []), [])
        self.assertTrue(wb.review_errors({"review": review}, ["file#1"]))
        review["findings"] = [{"kind": "blocker", "text": "The old path bypasses the guard."}]
        self.assertTrue(wb.review_errors({"review": review}, []))
        review["verdict"] = "changes needed"
        self.assertEqual(wb.review_errors({"review": review}, []), [])
        review["findings"] = []
        self.assertTrue(wb.review_errors({"review": review}, []))
        review["verdict"] = "insufficient evidence"
        self.assertEqual(wb.review_errors({"review": review}, ["file#1"]), [])

    def test_malformed_review_is_reported(self):
        for value in (None, [], {}, {"verdict": "approved"}):
            with self.subTest(value=value):
                self.assertTrue(wb.review_errors({"review": value}, []))
        for status in ("passed", "failed", "blocked", "skipped", "invented"):
            review = review_fixture()
            review["validation"][0]["status"] = status
            self.assertEqual(bool(wb.review_errors({"review": review}, [])), status == "invented")
        for key in ("challenge", "limits", "rationale"):
            review = review_fixture()
            review[key] = ""
            self.assertTrue(wb.review_errors({"review": review}, []))
        self.assertTrue(wb.review_errors({"briefing": {"before": "Before"}}, []))

    def test_new_evidence_links_are_validated_and_expanded(self):
        spec = {"chapters": [{"hunks": ["file"]}], "review": review_fixture()}
        spec["review"]["findings"] = [{"kind": "suggestion", "text": "Consider documenting this.", "hunks": ["file"]}]
        page = self.render_spec(spec)
        blob = page.split("const D = ", 1)[1].split(";\nconst S =", 1)[0]
        self.assertEqual(json.loads(blob)["spec"]["review"]["findings"][0]["hunks"], ["file#1"])
        for field in ("rationale", "challenge", "limits"):
            with self.subTest(field=field):
                bad = json.loads(json.dumps(spec))
                bad["review"][field] = "See [missing evidence](#hunk:missing#1)."
                with self.assertRaises(SystemExit) as result:
                    self.render_spec(bad)
                self.assertEqual(result.exception.code, 1)
        spec["review"]["findings"][0]["hunks"] = ["missing#1"]
        with self.assertRaises(SystemExit):
            self.render_spec(spec)

    def test_malformed_finding_refs_are_spec_errors_not_crashes(self):
        for refs in (None, "file", [None], [1], [{}], [["file"]]):
            with self.subTest(refs=refs):
                review = review_fixture()
                review["findings"] = [{"kind": "suggestion", "text": "Consider documenting this.", "hunks": refs}]
                self.assertIn("review finding hunks must be a list of strings", wb.review_errors({"review": review}, []))
                with self.assertRaises(SystemExit) as result:
                    self.render_spec({"chapters": [{"hunks": ["file"]}], "review": review})
                self.assertEqual(result.exception.code, 1)

    def test_render_rejects_ready_with_unexplained_changes(self):
        with self.assertRaises(SystemExit) as result:
            self.render_spec({"chapters": [], "review": review_fixture()})
        self.assertEqual(result.exception.code, 1)

    def test_decision_plain_language_handles_null_alternatives_and_non_string_text(self):
        for value in (None, 42, False, {"note": "example"}):
            for alternatives in (None, []):
                with self.subTest(value=value, alternatives=alternatives):
                    decision = {"choice": value, "why": value, "alternatives": alternatives}
                    self.assertEqual(list(wb.plain_language_report({"decisions": [decision]})), [])
                    page = self.render_spec({"decisions": [decision]})
                    self.assertIn("Not assessed", page)
        self.assertEqual(list(wb.plain_language_report({"decisions": [{"alternatives": [None, 42]}]})), [])

    def test_decision_basis_is_optional_but_constrained_when_present(self):
        for basis in ("documented", "inferred", "unknown"):
            with self.subTest(basis=basis):
                spec = {"decisions": [{"basis": basis}]}
                self.assertEqual(wb.review_errors(spec, []), [])
                self.render_spec(spec)
        self.assertEqual(wb.review_errors({"decisions": [{}]}, []), [])
        self.render_spec({"decisions": [{}]})
        for basis in (None, "confirmed", "", 42, [], {}):
            for with_review in (False, True):
                with self.subTest(basis=basis, with_review=with_review):
                    spec = {"chapters": [{"hunks": ["file"]}], "decisions": [{"basis": basis}]}
                    if with_review:
                        spec["review"] = review_fixture()
                    self.assertIn("decision basis must be documented, inferred, or unknown when present",
                                  wb.review_errors(spec, []))
                    with self.assertRaises(SystemExit) as result:
                        self.render_spec(spec)
                    self.assertEqual(result.exception.code, 1)

    def test_plain_language_checks_new_fields(self):
        jargon = " ".join(["someInternalCall() anotherInternalCall() thirdInternalCall()"] * 15)
        spec = {"briefing": {"before": jargon}, "review": {"limits": jargon},
                "decisions": [{"why": jargon}]}
        fields = [where for where, _, _ in wb.plain_language_report(spec)]
        self.assertIn("briefing before", fields)
        self.assertIn("review limits", fields)
        self.assertIn("decision 1", fields)

    def test_page_script_syntax_and_review_layout(self):
        template = (HERE / "template.html").read_text()
        script = template.split("<script>\n", 1)[1].split("</script>", 1)[0]
        subprocess.run(["node", "--check"], input=script, text=True, check=True, capture_output=True)
        names = ("verdictBlock", "briefingBlock", "assessmentBlock", "renderMain", "refs")
        functions = "\n".join(re.search(r"function " + name + r"\([^\n]*\) \{.*?^\}", template, re.M | re.S).group()
                              if name != "refs" else next(line for line in template.splitlines() if line.startswith("function refs("))
                              for name in names)
        harness = """
const S = JSON.parse(process.argv[1]);
const M = {repo_name: 'fixture', base: 'main', head: 'HEAD'};
const D = {files: [], noise: [], unexplained: []}, H = {}, chapters = [];
const totalA = 0, totalR = 0;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const md = esc, mdInline = esc, tx = esc, RISK = () => null;
const main = {};
const $ = () => main, $$ = () => [], linkInline = () => {};
"""
        spec = {"summary": "A small change.", "briefing": {"before": "Old behavior", "after": "New behavior",
                "unchanged": "Existing guarantees", "consequences": ["A new responsibility"]}, "review": review_fixture()}
        for with_review in (True, False):
            with self.subTest(with_review=with_review):
                current = spec if with_review else {}
                result = subprocess.run(["node", "-e", harness + functions + "\nrenderMain(); console.log(main.innerHTML);", json.dumps(current)],
                                        capture_output=True, text=True, check=True).stdout
                self.assertIn('id="decisions"', result)
                self.assertIn('id="check"', result)
                self.assertIn('id="assessment"', result)
                self.assertLess(result.index('id="decisions"'), result.index('id="check"'))
                self.assertLess(result.index('id="check"'), result.index('id="assessment"'))
                self.assertIn('<details class="uth"><summary><b>Change map', result)
                self.assertNotIn('<details class="uth" open', result)
                if with_review:
                    self.assertLess(result.index("Old behavior"), result.index("Change accounting"))
                    self.assertIn("Validation actually attempted", result)
                    self.assertIn("External integration behavior was not exercised.", result)
                else:
                    self.assertIn("Not assessed", result)


if __name__ == "__main__":
    unittest.main()
