#!/usr/bin/env python3
"""tools/report.py - what the agent found, and what it cost.

    make report
    python3 tools/report.py
    python3 tools/report.py --export

The roster's numbers are about consistency and coverage, not volume: "every
property scored on the same yardstick weekly". This prints the numbers that
let you check that promise against what actually happened: how many
properties have a scorecard this week, the average overall score, how many
are stuck needing a human, the edit rate on the digests you have reviewed,
and the LLM spend (near-zero - see docs/how-it-works.md "The one LLM call").

`--export` also writes the same rows to `systems.sheets.adapter` (csv by
default: `data/exports/qa_report.csv`), so you can hand a GM or an owner a
file instead of a terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.adapters import get_sheets  # noqa: E402
from core.adapters.base import AdapterError  # noqa: E402
from core.config import ConfigError, load_settings  # noqa: E402
from core.store import Store  # noqa: E402

import store_ext  # noqa: E402


def gather(store: Store) -> dict:
    rows = store.db.execute(
        "SELECT id, payload_json, draft_json, review_status FROM items WHERE kind='qa_audit'"
    ).fetchall()
    total = len(rows)
    overalls, actionable, needs_human, sent = [], 0, 0, 0
    by_property: dict[str, dict] = {}
    for r in rows:
        payload = json.loads(r["payload_json"] or "{}")
        draft = json.loads(r["draft_json"] or "{}")
        overall = draft.get("overall")
        if isinstance(overall, (int, float)):
            overalls.append(overall)
        actionable += len(draft.get("action_list") or [])
        if r["review_status"] == "needs_human":
            needs_human += 1
        if r["review_status"] in ("sent", "auto_sent"):
            sent += 1
        name = payload.get("property_name", payload.get("property_id", "?"))
        by_property[name] = {"overall": overall, "period": payload.get("period"),
                             "status": r["review_status"]}

    edited_ids = {r["item_id"] for r in store.db.execute(
        "SELECT DISTINCT item_id FROM events WHERE action='status:edited'").fetchall()
        if r["item_id"]}
    reviewed = sum(1 for r in rows if r["review_status"] not in ("new", "dispatched"))

    cost_usd = 0.0
    for row in store.db.execute(
        "SELECT detail_json FROM events WHERE action='llm_call'").fetchall():
        try:
            cost_usd += float((json.loads(row["detail_json"]) or {}).get("cost_usd") or 0.0)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    return {
        "total_scorecards": total,
        "average_overall": round(sum(overalls) / len(overalls), 1) if overalls else None,
        "total_actions": actionable,
        "needs_human": needs_human,
        "sent": sent,
        "edit_rate_pct": round(100 * len(edited_ids) / reviewed, 1) if reviewed else 0.0,
        "llm_cost_usd": round(cost_usd, 4),
        "by_property": by_property,
    }


def print_report(stats: dict, mode: str) -> None:
    print("Guest Journey QA AI - report\n")
    print(f"  Scorecards on record:    {stats['total_scorecards']}")
    avg = stats["average_overall"]
    print(f"  Portfolio average:       {avg}/100" if avg is not None
         else "  Portfolio average:       no scorecards yet")
    print(f"  Total actions raised:    {stats['total_actions']}")
    print(f"  Needing a human first:   {stats['needs_human']} "
         f"(no GM contact configured, or no signal data)")
    print(f"  Sent to a GM:            {stats['sent']}")
    print(f"  Edit rate:               {stats['edit_rate_pct']}% of reviewed digests were "
         f"rewritten before sending")
    print(f"  LLM spend so far:        ${stats['llm_cost_usd']} "
         f"(scoring is deterministic - this is only the optional portfolio note)")
    print("\n  By property:")
    for name, row in sorted(stats["by_property"].items(),
                            key=lambda kv: (kv[1]["overall"] is None, kv[1]["overall"] or 0)):
        print(f"    {name:<22} overall={row['overall']}  period={row['period']}  "
             f"status={row['status']}")
    print(f"\n  Mode: {mode}. In shadow, nothing above was actually sent - "
         f"see docs/safety.md.")


def export_csv(settings, stats: dict) -> str:
    sheets = get_sheets(settings)
    rows = [["property", "overall", "period", "status"]]
    for name, row in stats["by_property"].items():
        rows.append([name, row["overall"], row["period"], row["status"]])
    try:
        sheets.append("qa_report", rows)
    except AdapterError as exc:
        print(f"export skipped: {exc}", file=sys.stderr)
        return ""
    return "data/exports/qa_report.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", action="store_true",
                        help="also write the same rows to systems.sheets.adapter")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    store = Store(settings)
    store_ext.migrate(store)
    try:
        stats = gather(store)
        print_report(stats, settings.mode)
        if args.export:
            path = export_csv(settings, stats)
            if path:
                print(f"\nExported to {path}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
