#!/usr/bin/env python3
"""
GF-1 QA harness.

Tests a generated command-line to-do app against the GF-1 specification
(see references/prompts.md). Acts like a QA engineer: it verifies the file
structure, statically reviews the code, then drives the CLI through positive
and negative scenarios in an isolated working directory and reports a
PASS/FAIL checklist with an overall verdict.

It never modifies the app under test. Each candidate is copied into a fresh
temp directory so its tasks.json never leaks between runs or pollutes the repo.

Usage (run inside a virtual environment, since `python` may not be on PATH):
    # one-time setup
    python3 -m venv .venv
    source .venv/bin/activate        # macOS/Linux
    # .venv\\Scripts\\activate       # Windows

    # then run the harness
    python tools/gf1_qa.py <path-to-todo-app> [<path-to-todo-app> ...]

Or invoke the venv interpreter directly without activating:
    .venv/bin/python tools/gf1_qa.py <path-to-todo-app>

Examples:
    python tools/gf1_qa.py evaluations/2026-05-31/claude-code/todo-app
    python tools/gf1_qa.py evaluations/2026-05-31/*/todo-app

The harness has no third-party dependencies, so the venv needs no pip installs.
It runs each app under test with the same interpreter it was launched with
(sys.executable), so the venv's Python is used end to end.

Exit code: 0 if every candidate passes (PASS or PASS WITH MINOR ISSUES),
1 if any candidate fails or no candidate is found.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

PASS = "PASS"   # status label, not a password
FAIL = "FAIL"
WARN = "WARN"   # minor issue, does not fail the spec bullet outright
INFO = "INFO"   # informational only, never affects verdict

REQUIRED_FILES = ["todo.py", "storage.py", "task.py", "README.md"]
# Files we tolerate alongside the source without flagging as "extra".
IGNORED_NAMES = {"__pycache__", "tasks.json", ".DS_Store", ".gitignore"}

# Third-party imports are anything not in this allow-list of stdlib modules
# that a spec-compliant app might reasonably touch.
STDLIB_ALLOW = {
    "argparse", "json", "os", "sys", "pathlib", "dataclasses", "typing",
    "__future__", "collections", "io", "re",
}


class Check:
    def __init__(self, name, status, detail=""):
        self.name = name
        self.status = status
        self.detail = detail


class CandidateReport:
    def __init__(self, path):
        self.path = path
        self.checks = []

    def add(self, name, status, detail=""):
        self.checks.append(Check(name, status, detail))

    @property
    def failed(self):
        return [c for c in self.checks if c.status == FAIL]

    @property
    def warned(self):
        return [c for c in self.checks if c.status == WARN]

    def verdict(self):
        if self.failed:
            return FAIL
        if self.warned:
            return "PASS WITH MINOR ISSUES"
        return PASS


# ---------------------------------------------------------------------------
# Process runner
# ---------------------------------------------------------------------------

class App:
    """Runs the to-do app inside an isolated working directory."""

    def __init__(self, src_dir):
        self.src_dir = os.path.abspath(src_dir)
        self.work = tempfile.mkdtemp(prefix="gf1_qa_")
        # Copy only the source modules; run in a clean dir so tasks.json
        # starts absent and never touches the original folder.
        for name in ("todo.py", "storage.py", "task.py"):
            srcf = os.path.join(self.src_dir, name)
            if os.path.exists(srcf):
                shutil.copy2(srcf, os.path.join(self.work, name))

    def run(self, *cli_args):
        # Command is fully controlled by this harness: a fixed interpreter
        # (sys.executable) and a fixed script ("todo.py"); cli_args are
        # supplied by the test suite, never by external input. shell=False
        # (the default) so each list element is passed verbatim as its own
        # argv entry with no shell interpretation, so command injection is
        # not possible here and shlex.quote() does not apply.
        #
        # Defense in depth: reject any argument that is not a plain string,
        # so the argv list can never be coerced into something unexpected.
        for arg in cli_args:
            if not isinstance(arg, str):
                raise TypeError(f"cli arg must be str, got {type(arg).__name__}")
        # Build argv from a static literal base plus the validated string
        # args. Passing a list with shell=False means each element is an
        # exact argv entry with no shell interpretation, so there is no
        # command-injection surface and shlex.quote() does not apply.
        proc = subprocess.run(  # nosec B603 # nosemgrep
            [sys.executable, "todo.py", *cli_args],
            cwd=self.work,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def tasks_json_exists(self):
        return os.path.exists(os.path.join(self.work, "tasks.json"))

    def cleanup(self):
        shutil.rmtree(self.work, ignore_errors=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def norm_lines(text):
    return [ln.rstrip("\r") for ln in text.strip("\n").split("\n")] if text.strip("\n") else []


def fmt(code, out, err):
    return f"exit={code} stdout={out.strip()!r} stderr={err.strip()!r}"


# ---------------------------------------------------------------------------
# Check groups
# ---------------------------------------------------------------------------

def check_files(report, src_dir):
    present = set(os.listdir(src_dir))

    for required in REQUIRED_FILES:
        if required in present:
            report.add(f"file present: {required}", PASS)
        else:
            report.add(f"file present: {required}", FAIL, "missing")

    extras = [
        n for n in present
        if n not in REQUIRED_FILES and n not in IGNORED_NAMES
    ]
    if extras:
        report.add("no extra files", WARN, f"extra: {', '.join(sorted(extras))}")
    else:
        report.add("no extra files", PASS)


def check_stdlib_only(report, src_dir):
    import_re = re.compile(r"^\s*(?:import|from)\s+([a-zA-Z_][\w]*)")
    offenders = {}
    for name in ("todo.py", "storage.py", "task.py"):
        fp = os.path.join(src_dir, name)
        if not os.path.exists(fp):
            continue
        with open(fp, encoding="utf-8") as f:
            for line in f:
                m = import_re.match(line)
                if not m:
                    continue
                mod = m.group(1)
                # local module imports are fine
                if mod in ("task", "storage", "todo"):
                    continue
                if mod not in STDLIB_ALLOW:
                    offenders.setdefault(name, set()).add(mod)
    if offenders:
        detail = "; ".join(f"{f}: {', '.join(sorted(m))}" for f, m in offenders.items())
        report.add("stdlib-only imports", FAIL, f"non-stdlib/unknown: {detail}")
    else:
        report.add("stdlib-only imports", PASS)


def check_positive_flow(report, app):
    # add "Buy milk" -> "Added task 1", tasks.json created
    code, out, err = app.run("add", "Buy milk")
    ok = code == 0 and norm_lines(out) == ["Added task 1"]
    report.add('add "Buy milk" -> "Added task 1"',
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))

    if app.tasks_json_exists():
        report.add("tasks.json created after first add", PASS)
    else:
        report.add("tasks.json created after first add", FAIL, "tasks.json not found")

    # add "Walk dog" -> "Added task 2"
    code, out, err = app.run("add", "Walk dog")
    ok = code == 0 and norm_lines(out) == ["Added task 2"]
    report.add('add "Walk dog" -> "Added task 2"',
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))

    # list -> both rows, unchecked
    code, out, err = app.run("list")
    lines = norm_lines(out)
    ok = code == 0 and "1. [ ] Buy milk" in lines and "2. [ ] Walk dog" in lines
    report.add('list shows "1. [ ] Buy milk" and "2. [ ] Walk dog"',
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))

    # done 1 -> "Completed task 1"
    code, out, err = app.run("done", "1")
    ok = code == 0 and norm_lines(out) == ["Completed task 1"]
    report.add('done 1 -> "Completed task 1"',
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))

    # list -> task 1 marked [x]
    code, out, err = app.run("list")
    lines = norm_lines(out)
    ok = code == 0 and "1. [x] Buy milk" in lines
    report.add('list shows "1. [x] Buy milk" after done',
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))

    # delete 2 -> "Deleted task 2"
    code, out, err = app.run("delete", "2")
    ok = code == 0 and norm_lines(out) == ["Deleted task 2"]
    report.add('delete 2 -> "Deleted task 2"',
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))

    # list -> task 2 gone, task 1 remains
    code, out, err = app.run("list")
    lines = norm_lines(out)
    has1 = any(ln.startswith("1.") for ln in lines)
    has2 = any(ln.startswith("2.") for ln in lines)
    ok = code == 0 and has1 and not has2
    report.add("list shows task 1 only after delete 2",
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))


def is_error_response(code, out, err):
    """Spec: clear error to stderr, exit code 1."""
    return code == 1 and err.strip() != ""


def check_negative_paths(report, app):
    # add with no title
    code, out, err = app.run("add")
    ok = is_error_response(code, out, err)
    report.add("add with no title -> stderr + exit 1",
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))

    # done unknown id
    code, out, err = app.run("done", "999")
    ok = is_error_response(code, out, err)
    report.add("done <unknown id> -> stderr + exit 1",
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))

    # delete unknown id
    code, out, err = app.run("delete", "999")
    ok = is_error_response(code, out, err)
    report.add("delete <unknown id> -> stderr + exit 1",
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))

    # unrecognized command
    code, out, err = app.run("frobnicate")
    ok = is_error_response(code, out, err)
    report.add("unrecognized command -> stderr + exit 1",
               PASS if ok else FAIL, "" if ok else fmt(code, out, err))


def check_autoincrement(report, app):
    # Fresh app instance state already has task 1 ("Buy milk") from positive flow.
    # Add a third task: ids should keep climbing (next is 3, since 2 was deleted).
    code, out, err = app.run("add", "Third task")
    m = re.match(r"Added task (\d+)", out.strip())
    if code == 0 and m:
        new_id = int(m.group(1))
        if new_id == 3:
            report.add("id keeps auto-incrementing (does not reuse deleted id 2)",
                       PASS, f"new id = {new_id}")
        else:
            report.add("id keeps auto-incrementing (does not reuse deleted id 2)",
                       WARN, f"expected 3, got {new_id}")
    else:
        report.add("id keeps auto-incrementing (does not reuse deleted id 2)",
                   FAIL, fmt(code, out, err))

    # Behavior when all tasks deleted then a new one added (informational).
    code, out, err = app.run("list")
    ids = [int(m.group(1)) for ln in norm_lines(out)
           if (m := re.match(r"(\d+)\.", ln))]
    for tid in ids:
        app.run("delete", str(tid))
    code, out, err = app.run("add", "After wipe")
    m = re.match(r"Added task (\d+)", out.strip())
    if m:
        report.add("id after deleting all tasks (behavior note)",
                   INFO, f"new id = {m.group(1)} (spec leaves this open)")
    else:
        report.add("id after deleting all tasks (behavior note)",
                   FAIL, fmt(code, out, err))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

SYMBOLS = {PASS: "PASS", FAIL: "FAIL", WARN: "WARN", INFO: "INFO"}


def print_report(report):
    print("=" * 72)
    print(f"Candidate: {report.path}")
    print("=" * 72)
    width = max(len(c.name) for c in report.checks)
    for c in report.checks:
        line = f"  [{SYMBOLS[c.status]}] {c.name.ljust(width)}"
        if c.detail:
            line += f"   -> {c.detail}"
        print(line)
    n_pass = sum(1 for c in report.checks if c.status == PASS)
    n_fail = len(report.failed)
    n_warn = len(report.warned)
    print("-" * 72)
    print(f"  {n_pass} passed, {n_fail} failed, {n_warn} minor issue(s)")
    print(f"  OVERALL VERDICT: {report.verdict()}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def evaluate(src_dir):
    report = CandidateReport(src_dir)

    if not os.path.isdir(src_dir):
        report.add("folder exists", FAIL, "not a directory")
        return report

    check_files(report, src_dir)

    if not os.path.exists(os.path.join(src_dir, "todo.py")):
        report.add("runnable", FAIL, "todo.py missing, cannot run app")
        return report

    check_stdlib_only(report, src_dir)

    app = App(src_dir)
    try:
        check_positive_flow(report, app)
        check_negative_paths(report, app)
        check_autoincrement(report, app)
    except subprocess.TimeoutExpired:
        report.add("runtime", FAIL, "app timed out (possible hang/prompt)")
    except Exception as e:  # noqa: BLE001 - QA harness should never crash
        report.add("runtime", FAIL, f"harness error: {e!r}")
    finally:
        app.cleanup()

    return report


def main():
    parser = argparse.ArgumentParser(
        description="QA harness for GF-1 to-do app spec compliance."
    )
    parser.add_argument(
        "paths", nargs="+",
        help="Path(s) to a todo-app folder to test.",
    )
    args = parser.parse_args()

    reports = [evaluate(p) for p in args.paths]

    any_fail = False
    for r in reports:
        print_report(r)
        if r.verdict() == FAIL:
            any_fail = True

    if len(reports) > 1:
        print("=" * 72)
        print("SUMMARY")
        print("=" * 72)
        for r in reports:
            print(f"  {r.verdict():<26} {r.path}")
        print()

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
