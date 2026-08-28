#!/usr/bin/env python3
"""tools/demo.py - the whole loop on the bundled fixtures, zero credentials.

    make demo
    python3 tools/demo.py

Forces `llm.provider=mock` and `mode=shadow` regardless of config/hotel.yaml
(ARCHITECTURE.md section 1, "works in 5 minutes with zero credentials"). It
runs against its own database (data/demo/demo.db) so running it twice always
shows the same four properties, and never touches data/agent.db (that is
`make run`'s file).

Immune to whatever the hotel has already put in data/imports/*.csv: the demo
seeds its five signal tables from fixtures/inbound/signals/ only, and calls
tools/run.py:one_pass(..., import_signals=False) so the real CSV importer
never runs here - a decoy CSV in data/imports/ changes nothing about what
this prints.

Prints one line every check reads for the pass/fail signal:

    DEMO OK — 4 items processed, 4 drafted, 0 sent (shadow)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import ConfigError, load_settings, sub_data_dir  # noqa: E402
from core.log import summary_line  # noqa: E402
from core.store import Store  # noqa: E402

import scorecard  # noqa: E402
import store_ext  # noqa: E402
from run import one_pass  # noqa: E402


def main() -> int:
    try:
        settings = load_settings(demo=True)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    demo_db = sub_data_dir("demo") / "demo.db"
    if demo_db.exists():
        demo_db.unlink()  # every `make demo` is a clean, repeatable run
    store = Store(settings, path=demo_db)
    store_ext.migrate(store)

    loaded = store_ext.seed_fixtures(store, REPO_ROOT / "fixtures" / "inbound" / "signals")
    if not any(loaded.values()):
        print("no fixtures found in fixtures/inbound/signals/ - nothing to demo", file=sys.stderr)
        return 1

    properties = settings.agent_get("properties", []) or []
    flagship = settings.agent_get("flagship")
    print(f"Guest Journey QA AI demo - {len(properties)} propert"
         f"{'y' if len(properties) == 1 else 'ies'} in the portfolio, "
         f"flagship first then weakest overall\n")

    code, stats = one_pass(settings, store, only_property=None, force=True,
                           dry_run=False, import_signals=False)
    if code != 0:
        print("demo run did not complete cleanly", file=sys.stderr)
        store.close()
        return 1

    from core.review import list_queue
    items = list_queue(store, kind="qa_audit", limit=50)
    ordered = sorted(items, key=lambda i: (0 if (i.payload or {}).get("property_id") == flagship
                                           else 1, (i.draft or {}).get("overall", 0)))
    for item in ordered:
        payload, draft = item.payload or {}, item.draft or {}
        band = scorecard.band_for(draft.get("overall", 0))
        n_actions = len(draft.get("action_list", []))
        print(f"  {payload.get('property_name', '?'):<22} overall={draft.get('overall', '?'):>3}"
             f"/100 ({band})  {n_actions} action(s)  status={item.review_status}")

    print(f"\n{stats['needs_human']} of {stats['processed']} property digest(s) need a person "
         f"to look first (no GM contact configured, or no signal data - see docs/safety.md).")
    print("Nothing was sent: mode is shadow, and demo never calls send() at all.")
    print("Next: `make review` to see a digest, or read workflows/10-qa-audit.md.\n")

    print(f"DEMO OK — {summary_line(stats, settings.mode)}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
