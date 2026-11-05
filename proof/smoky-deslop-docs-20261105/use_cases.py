"""Hermetic checks of manually applied skill examples, not an LLM benchmark.

Run from the repository root. No export/deploy handler or external service runs.
The before/after decisions are recorded in USE_CASES.md; negative controls show
that these checks distinguish a safe edit from a plausible unsafe one.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import re
import shlex

BEFORE = '''
def read_record(actor, record):
    # Independent plugin entry point: callers need not check permission.
    if actor != record["owner"]:
        raise PermissionError("denied")
    # Return the record.
    return record["value"]
'''
AFTER = BEFORE.replace("    # Return the record.\n", "")
UNSAFE = AFTER.replace('    if actor != record["owner"]:\n        raise PermissionError("denied")\n', "")

ORIGINAL_DOC = (
    "Export is implemented and tested locally, but not deployed. "
    "Automatic export is planned. After owner approval, run `tool export --preview` "
    "to inspect the plan."
)
REWRITE = (
    "Export is implemented and locally tested. It is not deployed. "
    "Automatic export remains planned. After owner approval, inspect the plan "
    "with `tool export --preview`."
)
UNSAFE_DOC = "Export is available. Inspect the plan with `tool export`."


def observe(source: str) -> tuple:
    namespace: dict = {}
    exec(compile(source, "<synthetic-handler>", "exec"), namespace)
    function = namespace["read_record"]
    outcomes = []
    for actor, record in (("reader", {"owner": "reader", "value": 7}),
                          ("other", {"owner": "reader", "value": 7}),
                          ("reader", {"value": 7})):
        try:
            outcomes.append(("value", function(actor, record)))
        except Exception as error:
            outcomes.append((type(error).__name__, str(error)))
    return tuple(outcomes)


def parse_documented_command(text: str) -> argparse.Namespace:
    # Synthetic owning parser: no execution handler is defined or invoked.
    parser = argparse.ArgumentParser(prog="tool")
    subcommands = parser.add_subparsers(dest="command", required=True)
    export = subcommands.add_parser("export")
    export.add_argument("--preview", action="store_true")
    help_output = io.StringIO()
    with contextlib.redirect_stdout(help_output):
        try:
            parser.parse_args(["export", "--help"])
        except SystemExit as error:
            assert error.code == 0
    assert "--preview" in help_output.getvalue()
    literal, = re.findall(r"`([^`]+)`", text)
    program, *args = shlex.split(literal)
    assert program == "tool"
    return parser.parse_args(args)


def main() -> None:
    assert observe(BEFORE) == observe(AFTER)
    assert observe(AFTER)[1] == ("PermissionError", "denied")
    assert observe(AFTER)[2][0] == "KeyError"
    assert observe(UNSAFE) != observe(BEFORE)
    print("PASS cleanup: allowed, denied and malformed direct calls preserved; guard-removal negative control detected")

    before = parse_documented_command(ORIGINAL_DOC)
    after = parse_documented_command(REWRITE)
    unsafe = parse_documented_command(UNSAFE_DOC)
    assert vars(before) == vars(after) == {"command": "export", "preview": True}
    assert vars(unsafe) != vars(before)
    print("PASS docs: literal resolves to same parser mode; dropped-preview negative control detected; no export executed")
    print("LIMIT: status, approval and alias meaning require the manual source comparison in USE_CASES.md")


if __name__ == "__main__":
    main()
