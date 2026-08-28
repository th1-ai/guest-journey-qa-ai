#!/usr/bin/env python3
"""tools/doctor.py - is Guest Journey QA AI configured and ready to run?

    make doctor
    python3 tools/doctor.py

Runs the generic core.doctor checks (python, deps, config, .env, hotel
identity, mode, llm provider, every adapter, the store, knowledge) plus
checks specific to this agent: the portfolio is configured, the score
categories and owner map resolve, the prompt files are present, and whether
this week's signal imports exist. Exits 0 when everything passed, 1 when a
FAIL line needs fixing. Never a traceback: a config error is shown as a FAIL
row like any other.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import ConfigError, Settings, load_settings  # noqa: E402
from core.doctor import Check, FAIL, PASS, WARN, print_table, run_checks  # noqa: E402

import store_ext  # noqa: E402


def check_properties(settings: Settings) -> Check:
    properties = settings.agent_get("properties", [])
    if not properties:
        return Check("portfolio", FAIL, "no properties configured in config/agent.yaml",
                     "Copy config/agent.example.yaml to config/agent.yaml - it ships "
                     "with four sample properties.")
    ids = [p.get("id") for p in properties]
    if len(set(ids)) != len(ids):
        return Check("portfolio", FAIL, "two properties share the same id",
                     "Every properties[].id must be unique - it is half of the "
                     "idempotency key for a week's scorecard.")
    flagship = settings.agent_get("flagship")
    if flagship and flagship not in ids:
        return Check("portfolio", WARN,
                     f"flagship '{flagship}' is not one of the configured property ids",
                     "Fix agent.yaml: flagship, or the ordering rule cannot find it.")
    group_name = settings.agent_get("group_name")
    if not group_name:
        return Check("portfolio", WARN,
                     f"{len(properties)} propert{'y' if len(properties)==1 else 'ies'} "
                     f"configured, flagship={flagship or '(none)'}, but group_name is not "
                     f"set - every digest header falls back to hotel.yaml's flagship name",
                     "Set config/agent.yaml: group_name to your portfolio's own name - see "
                     "docs/how-it-works.md 'Design decisions where the spec was silent' #3.")
    return Check("portfolio", PASS, f"{len(properties)} propert{'y' if len(properties)==1 else 'ies'} "
                                    f"configured, flagship={flagship or '(none)'}, "
                                    f"group_name={group_name!r}")


def check_prompts() -> Check:
    missing = [p for p in ("prompts/portfolio-note.md", "prompts/schemas/portfolio-note.json")
              if not (REPO_ROOT / p).is_file()]
    if missing:
        return Check("prompts", FAIL, f"missing {', '.join(missing)}",
                     "These ship with the repo - restore them from git.")
    return Check("prompts", PASS, "portfolio-note.md + schema present")


def check_imports(settings: Settings) -> Check:
    """Row counts, not just presence - via `store_ext.preview_import_counts`,
    the same `_read_csv` reader `import_signals_csv` uses at run time, so this
    number is never a guess. See README.md "Connect your systems"."""
    imports_dir = REPO_ROOT / "data" / "imports"
    counts = store_ext.preview_import_counts(imports_dir)
    present = {f: n for f, n in counts.items() if (imports_dir / f).is_file()}
    if not present:
        return Check("this week's signal imports", WARN,
                     "no CSVs in data/imports/ yet - `make run` will use whatever was "
                     "imported last time, or nothing",
                     "See docs/integrations.md for the five file formats. `make demo` "
                     "does not need these - it uses fixtures/inbound/signals/ instead.")
    unreadable = [f for f, n in present.items() if n < 0]
    if unreadable:
        return Check("this week's signal imports", FAIL,
                     f"could not read {', '.join(unreadable)}",
                     "Open the file and check it is valid UTF-8 CSV - compare its header "
                     "row against docs/integrations.md.")
    empty = [f for f, n in present.items() if n == 0]
    detail = ", ".join(f"{f}={n} row{'s' if n != 1 else ''}" for f, n in present.items())
    if empty:
        return Check("this week's signal imports", WARN,
                     f"{len(present)}/5 signal file(s) present in data/imports/ but "
                     f"{', '.join(empty)} {'is' if len(empty) == 1 else 'are'} empty "
                     f"(0 rows): {detail}",
                     "An empty file is a real 0 rows, not 'not connected yet' - check the "
                     "export that wrote it.")
    return Check("this week's signal imports", PASS,
                f"{len(present)}/5 signal file(s) present in data/imports/: {detail}")


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        checks = run_checks(None) + [Check("config", FAIL, str(exc),
                                           "Fix config/hotel.yaml or config/agent.yaml.")]
        return print_table(checks, title="Guest Journey QA AI - doctor")

    checks = run_checks(settings, extra=[check_properties])
    checks.append(check_prompts())
    checks.append(check_imports(settings))
    return print_table(checks, title="Guest Journey QA AI - doctor")


if __name__ == "__main__":
    raise SystemExit(main())
